"""tests/pipeline/test_stage_extraction_orchestration.py — Phases 2b and 3."""
import json

from contracts.pipeline import Disposition
from contracts.schemas import DocumentType, ExtractedField
from pipeline import stage_extraction, stage_orchestration
from pipeline.stage_orchestration import rules_extraction
from tests.pipeline.conftest import make_doc, make_record, webhook_text


def extract(ctx, text, doc_type=DocumentType.REFERRAL, **doc_kw):
    rec = make_record(make_doc(text, **doc_kw), doc_type)
    stage_extraction.run([rec], ctx)
    return rec


class TestExtraction:
    def test_fields_extracted(self, ctx):
        rec = extract(ctx, webhook_text())
        assert rec.extraction.patient_name.value == "Jane Smith" and rec.extraction.mean_confidence > 0.9

    def test_model_routing_and_prompt_recorded(self, ctx):
        g = extract(ctx, webhook_text(), DocumentType.DENIAL_EOB).governance
        assert g["model"] and g["model_tier"] and g["prompt"].startswith("extraction-denial_eob:")

    def test_completeness_scored(self, ctx):
        assert 0 < extract(ctx, webhook_text()).governance["completeness"] <= 1

    def test_pii_is_redacted_before_the_llm(self, ctx):
        seen = []
        engine = ctx.engine
        original = engine._call_llm
        engine._call_llm = lambda s, u: seen.append(u) or original(s, u)
        try:
            rec = extract(ctx, webhook_text(notes="SSN 123-45-6789"))
        finally:
            engine._call_llm = original
        assert rec.governance["pii_redacted"] and "123-45-6789" not in seen[0]

    def test_low_ocr_confidence_lowers_confidence(self, ctx):
        clean = extract(ctx, webhook_text())
        noisy = extract(ctx, webhook_text(), ocr_mean_confidence=65.0)
        assert noisy.extraction.mean_confidence < clean.extraction.mean_confidence

    def test_llm_calls_are_metered(self, fresh_ctx):
        extract(fresh_ctx, webhook_text())
        assert len(fresh_ctx.llm_calls) == 1 and fresh_ctx.llm_calls[0].cost_usd > 0

    def test_engine_llm_is_restored_after_the_stage(self, ctx):
        before = ctx.engine._call_llm
        extract(ctx, webhook_text())
        assert ctx.engine._call_llm is before

    def test_llm_failure_is_recorded_not_raised(self, fresh_ctx):
        def boom(s, u): raise TimeoutError("down")
        fresh_ctx.engine._call_llm = boom
        try:
            rec = extract(fresh_ctx, webhook_text())
        finally:
            from pipeline.offline_llm import offline_llm
            fresh_ctx.engine._call_llm = offline_llm
        assert rec.extraction.mean_confidence == 0.0 and not fresh_ctx.llm_calls[0].success


class TestOrchestration:
    def test_good_extraction_keeps_llm_result(self, ctx):
        rec = extract(ctx, webhook_text())
        stage_orchestration.run([rec], ctx)
        assert rec.governance["fallback_source"] == "llm" and rec.governance["schema_ok"]
        assert rec.in_flight

    def test_low_confidence_falls_back_to_ingestion_fields(self, ctx):
        rec = make_record(make_doc("garbage text no fields", patient_name="Jane Smith",
                                   diagnosis_codes=["M54.5"]), DocumentType.REFERRAL)
        stage_extraction.run([rec], ctx)
        assert rec.extraction.mean_confidence == 0.0
        stage_orchestration.run([rec], ctx)
        assert rec.governance["fallback_source"] == "rules" and rec.governance["used_fallback"]
        assert rec.extraction.patient_name.source == "rules" and rec.in_flight

    def test_nothing_to_fall_back_on_escalates_to_human(self, ctx):
        rec = extract(ctx, "garbage text no fields")
        stage_orchestration.run([rec], ctx)
        assert rec.disposition == Disposition.HUMAN_REVIEW and rec.governance["fallback_source"] == "human_queue"

    def test_rules_extraction_needs_something_to_work_with(self, ctx):
        import pytest
        rec = extract(ctx, "garbage")
        with pytest.raises(ValueError):
            rules_extraction(rec.document, rec.extraction)

    def test_guardrail_flags_missing_keys(self, ctx):
        rec = extract(ctx, webhook_text())
        stage_orchestration.REQUIRED_KEYS.append("no_such_key")
        try:
            stage_orchestration.run([rec], ctx)
        finally:
            stage_orchestration.REQUIRED_KEYS.remove("no_such_key")
        assert not rec.governance["schema_ok"] and rec.governance["guardrail_failures"]

    def test_rules_fields_are_marked_as_rules(self, ctx):
        rec = extract(ctx, webhook_text())
        out = rules_extraction(make_doc("x", patient_name="A B", payer_id="P1"), rec.extraction)
        assert isinstance(out.patient_name, ExtractedField) and out.patient_name.source == "rules"
        assert json.loads(out.model_dump_json())["extraction_warnings"][-1] == "rules_fallback_used"
