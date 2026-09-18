"""observability/metrics.py — inference metrics and cost tracking."""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from contracts.schemas import ModelCallRecord

logger = logging.getLogger(__name__)

# Approximate token costs in USD per 1K tokens (input + output combined estimate)
_COST_MAP: dict[str, float] = {
    "claude-haiku-4-5-20251001": 0.0003,
    "claude-sonnet-4-20250514":  0.003,
    "claude-opus-4-6":           0.015,
    "gpt-4o":                    0.005,
    "gpt-4o-mini":               0.0002,
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = _COST_MAP.get(model, 0.003)
    return round((input_tokens + output_tokens) / 1000 * rate, 6)


def record_call(
    document_id: str, model: str, prompt_name: str, prompt_version: str,
    input_tokens: int, output_tokens: int, latency_ms: float,
    success: bool = True, error: str | None = None,
) -> ModelCallRecord:
    record = ModelCallRecord(
        call_id=str(uuid.uuid4()), document_id=document_id,
        model=model, prompt_name=prompt_name, prompt_version=prompt_version,
        input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=round(latency_ms, 2),
        cost_usd=estimate_cost(model, input_tokens, output_tokens),
        success=success, error=error, called_at=datetime.now(UTC),
    )
    logger.info("LLM call recorded: %s model=%s tokens=%d+%d cost=$%.5f latency=%.0fms",
                record.call_id, model, input_tokens, output_tokens,
                record.cost_usd, latency_ms)
    return record


def instrumented_llm(call_fn: Callable, document_id: str, model: str,
                     prompt_name: str = "unknown", prompt_version: str = "unknown") -> Callable:
    """Wraps a call_llm function to emit timing + cost metrics."""
    def wrapper(system: str, user: str) -> str:
        t0 = time.perf_counter()
        try:
            result = call_fn(system=system, user=user)
            latency = (time.perf_counter() - t0) * 1000
            # Token estimation (production: read from API response headers)
            input_tok  = len((system + user).split()) * 4 // 3
            output_tok = len(result.split()) * 4 // 3
            record_call(document_id, model, prompt_name, prompt_version,
                        input_tok, output_tok, latency, success=True)
            return result
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            record_call(document_id, model, prompt_name, prompt_version,
                        0, 0, latency, success=False, error=str(exc))
            raise
    return wrapper
