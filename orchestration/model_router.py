"""orchestration/model_router.py — route to Claude, GPT-4o, or SLM by complexity."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ModelTier(StrEnum):
    FAST    = "fast"     # local SLM / Claude Haiku
    STANDARD = "standard" # Claude Sonnet / GPT-4o-mini
    PREMIUM  = "premium"  # Claude Opus / GPT-4o


@dataclass
class ModelChoice:
    model_id:     str
    tier:         ModelTier
    max_tokens:   int
    cost_per_1k:  float  # USD


_MODELS: dict[ModelTier, ModelChoice] = {
    ModelTier.FAST:     ModelChoice("claude-haiku-4-5-20251001", ModelTier.FAST, 1024, 0.0003),
    ModelTier.STANDARD: ModelChoice("claude-sonnet-4-20250514",  ModelTier.STANDARD, 4096, 0.003),
    ModelTier.PREMIUM:  ModelChoice("claude-opus-4-6",           ModelTier.PREMIUM, 8192, 0.015),
}


def route(task: str, text_length: int, require_reasoning: bool = False) -> ModelChoice:
    """
    Route a task to the appropriate model tier.
    - Short structured tasks → FAST
    - Complex extraction → STANDARD
    - Multi-step reasoning, appeal letter gen → PREMIUM
    """
    if require_reasoning or text_length > 5000:
        choice = _MODELS[ModelTier.PREMIUM]
    elif text_length > 1000 or task in ("extraction", "classification_llm"):
        choice = _MODELS[ModelTier.STANDARD]
    else:
        choice = _MODELS[ModelTier.FAST]
    logger.debug("Routed %s (len=%d) → %s", task, text_length, choice.model_id)
    return choice
