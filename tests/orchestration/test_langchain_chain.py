"""tests/orchestration/test_langchain_chain.py"""
from datetime import UTC, datetime

from contracts.schemas import DocumentType, ExtractionResult
from orchestration.langchain_chain import OrchestrationInput, run_orchestration

REQUIRED_KEYS = ["document_id", "document_type", "mean_confidence"]


def extraction(**over) -> ExtractionResult:
    base = {"document_id": "d1", "document_type": DocumentType.REFERRAL,
            "extracted_at": datetime.now(UTC), "mean_confidence": 0.9}
    return ExtractionResult(**{**base, **over})


def test_chain_is_a_langchain_runnable():
    from langchain_core.runnables import Runnable

    from orchestration.langchain_chain import _CHAIN
    assert isinstance(_CHAIN, Runnable)


def test_good_extraction_passes_guardrails_and_keeps_the_llm_result():
    ex = extraction()
    out = run_orchestration(OrchestrationInput(extraction=ex, rules_fn=lambda: ex,
                                               required_keys=REQUIRED_KEYS, min_confidence=0.55))
    assert out.schema.passed and out.output.passed
    assert out.fallback.source == "llm" and out.fallback.value is ex


def test_low_confidence_falls_back_to_rules():
    ex = extraction(mean_confidence=0.1)
    rules_result = extraction(mean_confidence=0.7)
    out = run_orchestration(OrchestrationInput(extraction=ex, rules_fn=lambda: rules_result,
                                               required_keys=REQUIRED_KEYS, min_confidence=0.55))
    assert out.fallback.source == "rules" and out.fallback.value is rules_result


def test_low_confidence_with_no_rules_fallback_escalates_to_human_queue():
    ex = extraction(mean_confidence=0.1)
    def broken(): raise ValueError("no structured fields")
    out = run_orchestration(OrchestrationInput(extraction=ex, rules_fn=broken,
                                               required_keys=REQUIRED_KEYS, min_confidence=0.55))
    assert out.fallback.source == "human_queue"


def test_missing_required_key_fails_the_schema_guardrail():
    ex = extraction()
    out = run_orchestration(OrchestrationInput(extraction=ex, rules_fn=lambda: ex,
                                               required_keys=[*REQUIRED_KEYS, "no_such_field"],
                                               min_confidence=0.55))
    assert not out.schema.passed
    assert any("no_such_field" in f for f in out.schema.failures)


def test_guardrails_run_before_fallback_is_evaluated():
    """The chain is guardrails | fallback — fallback still runs and still reports a source even
    when the schema guardrail fails, since a bad schema alone shouldn't block triage upstream."""
    ex = extraction()
    out = run_orchestration(OrchestrationInput(extraction=ex, rules_fn=lambda: ex,
                                               required_keys=["not_a_real_field"], min_confidence=0.55))
    assert not out.schema.passed and out.fallback.source == "llm"
