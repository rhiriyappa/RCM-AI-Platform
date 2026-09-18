"""tests/extraction/test_engine.py"""
import json
from datetime import UTC, datetime

from contracts.schemas import ClassificationResult, DocumentType, RawDocument, SourceType
from extraction.engine import ExtractionEngine
from extraction.enrichment import CodeValidator, ExtractionEnricher, MockNPILookup


def doc(text="Claim denied CO-4.", doc_id="e1"):
    return RawDocument(document_id=doc_id, source_id="s1", source_type=SourceType.FHIR_R4,
                       ingested_at=datetime.now(UTC), full_text=text)


def clf(doc_id="e1", doc_type=DocumentType.DENIAL_EOB):
    return ClassificationResult(document_id=doc_id, document_type=doc_type,
                                confidence=0.95, method="rules", routing_queue="onecall-denial-agent.fifo")


def engine(resp: str):
    enricher = ExtractionEnricher(MockNPILookup(), CodeValidator())
    return ExtractionEngine(call_llm=lambda s, u: resp, enricher=enricher)


GOOD = json.dumps({"patient_name": {"value": "Jane Smith", "confidence": 0.97},
                   "payer_id":     {"value": "BCBS-TX",    "confidence": 0.99},
                   "diagnosis_codes": [{"value": "M54.5",  "confidence": 0.95}],
                   "procedure_codes": [{"value": "99213",  "confidence": 0.97}],
                   "denial_reason_codes": [{"value": "CO-4", "confidence": 0.99}]})


class TestSuccess:
    def test_patient_name(self):     assert engine(GOOD).extract(doc(), clf()).patient_name.value == "Jane Smith"
    def test_denial_codes(self):     assert "CO-4" in [f.value for f in engine(GOOD).extract(doc(), clf()).denial_reason_codes]
    def test_document_id(self):      assert engine(GOOD).extract(doc(doc_id="uid"), clf("uid")).document_id == "uid"
    def test_mean_conf_positive(self): assert engine(GOOD).extract(doc(), clf()).mean_confidence > 0.0
    def test_codes_validated(self):  assert engine(GOOD).extract(doc(), clf()).codes_validated is True


class TestFallback:
    def test_exception_returns_empty(self):
        e = ExtractionEngine(call_llm=lambda s, u: (_ for _ in ()).throw(ConnectionError("t/o")),
                             enricher=ExtractionEnricher(MockNPILookup(), CodeValidator()))
        r = e.extract(doc(), clf())
        assert r.mean_confidence == 0.0 and any("extraction_error" in w for w in r.extraction_warnings)

    def test_invalid_json_no_raise(self): assert engine("not json").extract(doc(), clf()) is not None

    def test_needs_review_low_conf(self):
        r = engine(json.dumps({"patient_name": {"value": "X", "confidence": 0.3}})).extract(doc(), clf(doc_type=DocumentType.UNKNOWN))
        assert ExtractionEngine(call_llm=lambda s,u: "", enricher=ExtractionEnricher(MockNPILookup(), CodeValidator())).needs_human_review(r)


class TestNPIEnrichment:
    def test_known_npi_validated(self):
        resp = json.dumps({"provider_npi": {"value": "1234567890", "confidence": 0.95}})
        assert engine(resp).extract(doc(), clf()).npi_validated is True

    def test_unknown_npi_warning(self):
        resp = json.dumps({"provider_npi": {"value": "0000000000", "confidence": 0.88}})
        r = engine(resp).extract(doc(), clf())
        assert r.npi_validated is False and any("NPI not found" in w for w in r.extraction_warnings)
