"""orchestration/fallback.py — fallback chain: LLM → rules → human escalation."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class FallbackResult:
    value:       Any
    source:      str   # "llm" | "rules" | "human_queue"
    confidence:  float
    used_fallback: bool = False


def with_fallback(
    llm_fn:    Callable[[], Any],
    rules_fn:  Optional[Callable[[], Any]] = None,
    escalate_fn: Optional[Callable[[], Any]] = None,
    min_confidence: float = 0.55,
) -> FallbackResult:
    """
    Execute llm_fn. If it fails or returns low-confidence result,
    try rules_fn. If that also fails, call escalate_fn (human queue).
    """
    try:
        result = llm_fn()
        conf = result.mean_confidence if hasattr(result, "mean_confidence") else 1.0
        if conf >= min_confidence:
            return FallbackResult(value=result, source="llm", confidence=conf)
        logger.warning("LLM confidence %.2f below threshold %.2f, trying rules fallback", conf, min_confidence)
    except Exception as exc:
        logger.warning("LLM call failed: %s, trying rules fallback", exc)

    if rules_fn is not None:
        try:
            result = rules_fn()
            logger.info("Rules fallback succeeded")
            return FallbackResult(value=result, source="rules", confidence=0.70, used_fallback=True)
        except Exception as exc:
            logger.warning("Rules fallback failed: %s", exc)

    if escalate_fn is not None:
        result = escalate_fn()
        return FallbackResult(value=result, source="human_queue", confidence=0.0, used_fallback=True)

    raise RuntimeError("All fallback tiers exhausted")
