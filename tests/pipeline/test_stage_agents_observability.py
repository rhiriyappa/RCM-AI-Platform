"""tests/pipeline/test_stage_agents_observability.py — Phases 4 and 5."""
import pytest

from contracts.pipeline import Disposition
from contracts.schemas import DocumentType
from pipeline import stage_agents, stage_extraction, stage_observability, stage_orchestration
from pipeline.stage_agents import flatten_extraction
from tests.pipeline.conftest import make_doc, make_record, webhook_text


def through_agents(ctx, doc_type, **over):
    rec = make_record(make_doc(webhook_text(**over)), doc_type)
    stage_extraction.run([rec], ctx)
    stage_orchestration.run([rec], ctx)
    stage_agents.run([rec], ctx)
    return rec


class TestAgents:
    def test_flatten_unwraps_field_values(self, ctx):
        rec = make_record(make_doc(webhook_text()), DocumentType.REFERRAL)
        stage_extraction.run([rec], ctx)
        flat = flatten_extraction(rec.extraction)
        assert flat["patient_name"] == "Jane Smith" and flat["diagnosis_codes"] == ["M54.5"]
        assert "payer_name" in flat and flat["mean_confidence"] > 0

    @pytest.mark.parametrize("doc_type,agent", [
        (DocumentType.REFERRAL, "referral_triage"), (DocumentType.PRIOR_AUTH, "prior_auth"),
        (DocumentType.DENIAL_EOB, "denial_appeal")])
    def test_dispatch_by_document_type(self, ctx, doc_type, agent):
        rec = through_agents(ctx, doc_type, denial={"reason_code": "CO-50"})
        assert rec.agent.audit_trail[0]["agent"] == agent and rec.disposition == Disposition.COMPLETED

    def test_types_without_an_agent_are_routed_to_their_queue(self, ctx):
        rec = through_agents(ctx, DocumentType.CLAIM_837)
        assert rec.disposition == Disposition.ROUTED and rec.governance["queue"] == "q"
        assert rec.agent is None

    def test_agent_pauses_for_human_when_confidence_is_low(self, ctx):
        rec = make_record(make_doc(webhook_text(), ocr_mean_confidence=20.0), DocumentType.PRIOR_AUTH)
        stage_extraction.run([rec], ctx)
        stage_agents.run([rec], ctx)
        assert rec.disposition == Disposition.HITL and rec.agent.hitl_required

    def test_agent_failure_is_a_disposition_not_a_crash(self, ctx):
        rec = make_record(make_doc(webhook_text(provider_npi="", diagnosis_codes=[], procedure_codes=[])),
                          DocumentType.PRIOR_AUTH)
        rec.extraction = None      # simulate a broken upstream hand-off
        stage_agents.run([rec], ctx)
        assert rec.disposition == Disposition.FAILED and rec.errors

    def test_denial_without_overturnable_code_completes_without_appeal(self, ctx):
        rec = through_agents(ctx, DocumentType.DENIAL_EOB, denial={"reason_code": "PR-1"})
        assert rec.agent.output["appeal_viable"] is False


class TestObservability:
    def test_instrument_records_success(self, fresh_ctx):
        f = stage_observability.instrument(lambda s, u: "out put", fresh_ctx, "d", "m", "p", "v1")
        assert f("a", "b") == "out put" and fresh_ctx.llm_calls[0].success

    def test_instrument_records_failure_and_reraises(self, fresh_ctx):
        def boom(s, u): raise RuntimeError("x")
        with pytest.raises(RuntimeError):
            stage_observability.instrument(boom, fresh_ctx, "d", "m", "p", "v1")("a", "b")
        assert not fresh_ctx.llm_calls[0].success and fresh_ctx.llm_calls[0].error == "x"

    def test_gold_eval_passes(self, ctx):
        report = stage_observability.run_gold_eval(ctx)
        assert report.total_records == 3 and report.passed

    def test_report_aggregates(self, fresh_ctx):
        rec = through_agents(fresh_ctx, DocumentType.REFERRAL)
        report = stage_observability.build_report([rec], fresh_ctx)
        assert report.total_records == 1 and report.llm_calls == 1 and report.llm_cost_usd > 0
        assert report.by_disposition == {"completed": 1} and report.by_agent == {"referral_triage": 1}
        assert report.eval_mean_f1 is None

    def test_report_handles_an_empty_run(self, fresh_ctx):
        report = stage_observability.build_report([], fresh_ctx)
        assert report.total_records == 0 and report.mean_extraction_confidence == 0.0
