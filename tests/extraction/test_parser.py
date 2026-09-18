"""tests/extraction/test_parser.py"""
import json

from contracts.schemas import DocumentType
from extraction.parser import parse_llm_output

DENIAL = json.dumps({
    "patient_name":       {"value": "Jane Smith",  "confidence": 0.97},
    "payer_id":           {"value": "BCBS-TX",     "confidence": 0.99},
    "diagnosis_codes":    [{"value": "M54.5",      "confidence": 0.95}],
    "denial_reason_codes":[{"value": "CO-4",       "confidence": 0.99}],
    "appeal_deadline":    {"value": "2024-04-15",  "confidence": 0.88},
})

class TestDenialParsing:
    def test_patient_name(self):        assert parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).patient_name.value == "Jane Smith"
    def test_diagnosis_codes(self):     assert "M54.5" in [f.value for f in parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).diagnosis_codes]
    def test_denial_codes(self):        assert "CO-4" in [f.value for f in parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).denial_reason_codes]
    def test_appeal_deadline(self):     assert parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).appeal_deadline.value == "2024-04-15"
    def test_mean_confidence(self):     assert 0.0 < parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).mean_confidence <= 1.0
    def test_document_id(self):         assert parse_llm_output(DENIAL, "my-id", DocumentType.DENIAL_EOB).document_id == "my-id"
    def test_document_type(self):       assert parse_llm_output(DENIAL, "d1", DocumentType.DENIAL_EOB).document_type == DocumentType.DENIAL_EOB

class TestRobustness:
    def test_markdown_fenced(self):     assert parse_llm_output(f"```json\n{DENIAL}\n```", "d1", DocumentType.DENIAL_EOB).patient_name is not None
    def test_empty_response(self):
        r = parse_llm_output("", "d1", DocumentType.DENIAL_EOB)
        assert r.mean_confidence == 0.0 and r.extraction_warnings
    def test_invalid_json(self):        assert parse_llm_output("not json!", "d1", DocumentType.DENIAL_EOB) is not None
    def test_null_field(self):          assert parse_llm_output(json.dumps({"patient_name": None}), "d1", DocumentType.REFERRAL).patient_name is None
    def test_string_shorthand(self):    assert parse_llm_output(json.dumps({"patient_name": "John Doe"}), "d1", DocumentType.REFERRAL).patient_name.value == "John Doe"
    def test_confidence_clamped(self):  assert parse_llm_output(json.dumps({"patient_name": {"value": "X", "confidence": 1.5}}), "d1", DocumentType.REFERRAL).patient_name.confidence <= 1.0
    def test_low_conf_populated(self):
        r = parse_llm_output(json.dumps({"patient_name": {"value": "X", "confidence": 0.3}}), "d1", DocumentType.REFERRAL)
        assert "patient_name" in r.low_conf_fields
