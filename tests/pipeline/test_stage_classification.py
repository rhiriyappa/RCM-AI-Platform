"""tests/pipeline/test_stage_classification.py"""
import json

import pytest

from contracts.pipeline import Disposition
from contracts.schemas import DocumentType, SourceType
from pipeline import stage_classification
from tests.pipeline.conftest import make_doc, make_record, webhook_text


def classify(ctx, text, source=SourceType.WEBHOOK):
    rec = make_record(make_doc(text, source))
    stage_classification.run([rec], ctx)
    return rec


@pytest.mark.parametrize("event,expected", [
    ("referral.created", DocumentType.REFERRAL), ("prior_auth.submitted", DocumentType.PRIOR_AUTH),
    ("claim.denied", DocumentType.DENIAL_EOB), ("eligibility.checked", DocumentType.ELIGIBILITY),
    ("note.uploaded", DocumentType.CLINICAL_NOTE)])
def test_webhook_event_declares_type(ctx, event, expected):
    rec = classify(ctx, webhook_text(event=event))
    assert rec.classification.document_type == expected and rec.classification.method == "source_hint"


def test_edi_is_always_a_claim(ctx):
    rec = classify(ctx, "ISA*00~\nST*837*1~", SourceType.EDI_837)
    assert rec.classification.document_type == DocumentType.CLAIM_837


def test_fhir_claim_bundle_is_a_claim(ctx):
    bundle = json.dumps({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Claim"}}]})
    assert classify(ctx, bundle, SourceType.FHIR_R4).classification.document_type == DocumentType.CLAIM_837


def test_fhir_without_claim_is_not_guessed(ctx):
    bundle = json.dumps({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient"}}]})
    assert classify(ctx, bundle, SourceType.FHIR_R4).disposition == Disposition.HUMAN_REVIEW


def hl7_message(msg_type: str, trigger: str) -> str:
    return f"MSH|^~\\&|A|B|C|D|20240101||{msg_type}^{trigger}|1|P|2.5\nPID|1||X"


@pytest.mark.parametrize("msg_type,trigger,expected_type", [
    ("ORM", "O01", DocumentType.REFERRAL),   # order message → outbound specialist referral
    ("DFT", "P03", DocumentType.CLAIM_837),  # detail financial transaction → charge/claim post
])
def test_hl7_mapped_message_types_declare_their_document_type(ctx, msg_type, trigger, expected_type):
    rec = classify(ctx, hl7_message(msg_type, trigger), SourceType.HL7_V2)
    assert rec.classification.document_type == expected_type
    assert rec.classification.method == "source_hint"
    assert rec.in_flight  # a declared type never gets closed out as human review


def test_hl7_registration_message_has_no_document_type_mapping(ctx):
    """ADT (admission/registration) isn't an RCM workflow the platform models — no DocumentType
    fits it, so it is expected to fall through to human review rather than being guessed at."""
    rec = classify(ctx, hl7_message("ADT", "A08"), SourceType.HL7_V2)
    assert rec.classification.method == "no_signal"
    assert rec.classification.document_type == DocumentType.UNKNOWN
    assert rec.disposition == Disposition.HUMAN_REVIEW


def test_hl7_unmapped_message_type_also_falls_through(ctx):
    """Any message type besides ORM/DFT (not just ADT) is unmapped — e.g. ORU (results)."""
    rec = classify(ctx, hl7_message("ORU", "R01"), SourceType.HL7_V2)
    assert rec.disposition == Disposition.HUMAN_REVIEW


def test_malformed_webhook_falls_through_to_text_rules(ctx):
    rec = classify(ctx, '{"event": "claim.denied", "patient": {"na')
    assert rec.classification.method != "source_hint" and rec.classification.document_type == DocumentType.DENIAL_EOB


def test_fax_text_uses_rules(ctx):
    rec = classify(ctx, "Claim denied CO-4. Explanation of Benefits.", SourceType.FAX_S3)
    assert rec.classification.document_type == DocumentType.DENIAL_EOB


def test_result_updates_document_and_routes_queue(ctx):
    rec = classify(ctx, webhook_text(event="claim.denied"))
    assert rec.document.document_type == DocumentType.DENIAL_EOB
    assert rec.classification.routing_queue == "onecall-denial-agent.fifo"


def test_unknown_is_closed_out_for_human_review(ctx):
    rec = classify(ctx, "zzz qqq lorem", SourceType.FAX_S3)
    assert rec.disposition == Disposition.HUMAN_REVIEW and rec.errors


def test_terminal_records_are_skipped(ctx):
    rec = make_record(make_doc("x"))
    rec.disposition = Disposition.DLQ
    stage_classification.run([rec], ctx)
    assert rec.classification is None
