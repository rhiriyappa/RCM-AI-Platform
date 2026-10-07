"""orchestration/langchain_chain.py — LangChain Runnable composition of the orchestration chain.

Phase 3 orchestration — "guardrail the result, then fall back if it's unusable" — used to be a
straight-line function call in pipeline/stage_orchestration.py. This module expresses the same two
steps as a LangChain `RunnableSequence` (`guardrails | fallback`) so orchestration is wired
declaratively rather than by hand-rolled control flow, and so a later step (model-level retries,
LangSmith tracing, a branching `RunnableBranch`) composes onto it instead of rewriting it.

The step implementations themselves are unchanged — this only changes how they're wired together.
orchestration/guardrails.py and orchestration/fallback.py remain the actual logic and are still
exercised directly by tests/orchestration/test_orchestration.py.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableLambda, RunnableSequence

from contracts.schemas import ExtractionResult
from orchestration.fallback import FallbackResult, with_fallback
from orchestration.guardrails import GuardrailResult, check_json_schema, validate_output


@dataclass
class OrchestrationInput:
    """One record's worth of input to the chain. `rules_fn` is bound by the caller per record."""
    extraction:     ExtractionResult
    rules_fn:       Callable[[], ExtractionResult]
    required_keys:  list[str]
    min_confidence: float


@dataclass
class OrchestrationOutput:
    schema:   GuardrailResult
    output:   GuardrailResult
    fallback: FallbackResult


def _run_guardrails(inp: OrchestrationInput) -> dict[str, Any]:
    payload = inp.extraction.model_dump_json()
    return {"inp": inp, "schema": check_json_schema(payload, inp.required_keys),
            "output": validate_output(payload)}


def _run_fallback(state: dict[str, Any]) -> OrchestrationOutput:
    inp: OrchestrationInput = state["inp"]
    fb = with_fallback(llm_fn=lambda: inp.extraction, rules_fn=inp.rules_fn,
                       escalate_fn=lambda: None, min_confidence=inp.min_confidence)
    return OrchestrationOutput(schema=state["schema"], output=state["output"], fallback=fb)


# guardrails first (does the LLM output even look sane?), then the LLM → rules → human-queue chain.
_CHAIN: RunnableSequence = (RunnableLambda(_run_guardrails, name="guardrails")
                            | RunnableLambda(_run_fallback, name="fallback"))


def run_orchestration(inp: OrchestrationInput) -> OrchestrationOutput:
    return _CHAIN.invoke(inp)
