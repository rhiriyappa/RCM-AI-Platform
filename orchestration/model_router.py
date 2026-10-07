"""orchestration/model_router.py — route to Claude, GPT-4o, or a local SLM by complexity."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ModelTier(StrEnum):
    LOCAL_SLM = "local_slm"  # Ollama-hosted SLM (Mistral 7B, Llama) — zero marginal cost, on-box
    FAST      = "fast"       # Claude Haiku — hosted fallback for the same short/simple tasks
    STANDARD  = "standard"   # Claude Sonnet / GPT-4o-mini
    PREMIUM   = "premium"    # Claude Opus / GPT-4o


@dataclass
class ModelChoice:
    model_id:     str
    tier:         ModelTier
    max_tokens:   int
    cost_per_1k:  float  # USD


def _local_slm_choice() -> ModelChoice:
    # Read lazily (not at import time) so RCM_SLM_MODEL set after import still takes effect.
    model_id = os.environ.get("RCM_SLM_MODEL", "llama3.2")
    return ModelChoice(model_id, ModelTier.LOCAL_SLM, 2048, 0.0)


_MODELS: dict[ModelTier, ModelChoice] = {
    ModelTier.FAST:     ModelChoice("claude-haiku-4-5-20251001", ModelTier.FAST, 1024, 0.0003),
    ModelTier.STANDARD: ModelChoice("claude-sonnet-4-20250514",  ModelTier.STANDARD, 4096, 0.003),
    ModelTier.PREMIUM:  ModelChoice("claude-opus-4-6",           ModelTier.PREMIUM, 8192, 0.015),
}


def route(task: str, text_length: int, require_reasoning: bool = False, prefer_local: bool = False) -> ModelChoice:
    """
    Route a task to the appropriate model tier.
    - Short structured tasks → FAST (LOCAL_SLM instead, when prefer_local and reasoning is simple)
    - Complex extraction → STANDARD
    - Multi-step reasoning, appeal letter gen → PREMIUM

    prefer_local: true when the caller runs the pipeline against a local SLM (e.g. Ollama/Mistral 7B)
    rather than a hosted model. It only ever downgrades a short, non-reasoning call — checked before
    the task-name escalation below, so a short "extraction" call can still go local. Anything long or
    marked require_reasoning escalates to STANDARD/PREMIUM regardless of this flag.
    """
    if require_reasoning or text_length > 5000:
        choice = _MODELS[ModelTier.PREMIUM]
    elif prefer_local and text_length <= 1000:
        choice = _local_slm_choice()
    elif text_length > 1000 or task in ("extraction", "classification_llm"):
        choice = _MODELS[ModelTier.STANDARD]
    else:
        choice = _MODELS[ModelTier.FAST]
    logger.debug("Routed %s (len=%d) → %s", task, text_length, choice.model_id)
    return choice
