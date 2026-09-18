"""tests/ingestion/test_validator.py"""
import pytest
from datetime import datetime, timezone
from contracts.schemas import RawDocument, SourceType
from ingestion.validator import DocumentValidator, MIN_OCR_CONFIDENCE

def doc(**kw):
    defaults = dict(document_id="d1", source_id="s1", source_type=SourceType.FHIR_R4,
                    ingested_at=datetime.now(timezone.utc),
                    full_text="Patient Jane Smith. Diagnosis M54.5. Provider Dr. Jones.")
    defaults.update(kw)
    return RawDocument(**defaults)

V = DocumentValidator()

class TestValid:
    def test_valid_passes(self):                assert V.validate(doc()).is_valid
    def test_high_ocr_passes(self):             assert V.validate(doc(ocr_mean_confidence=95.0)).is_valid
    def test_valid_icd10_no_warnings(self):
        r = V.validate(doc(diagnosis_codes=["M54.5", "J45.901"]))
        assert r.is_valid and r.warnings == []
    def test_valid_cpt_no_warnings(self):
        r = V.validate(doc(procedure_codes=["99213"]))
        assert r.is_valid and r.warnings == []

class TestFailing:
    def test_low_ocr_fails(self):
        r = V.validate(doc(ocr_mean_confidence=MIN_OCR_CONFIDENCE - 1))
        assert not r.is_valid and any("confidence" in e for e in r.errors)
    def test_empty_text_fails(self):           assert not V.validate(doc(full_text="   ")).is_valid
    def test_short_text_fails(self):           assert not V.validate(doc(full_text="Hi")).is_valid
    def test_at_threshold_passes(self):        assert V.validate(doc(ocr_mean_confidence=MIN_OCR_CONFIDENCE)).is_valid

class TestWarnings:
    def test_bad_icd10_warns(self):
        r = V.validate(doc(diagnosis_codes=["BADCODE"]))
        assert r.is_valid and any("ICD-10" in w for w in r.warnings)
    def test_bad_cpt_warns(self):
        r = V.validate(doc(procedure_codes=["NOTACPT"]))
        assert r.is_valid and any("CPT" in w for w in r.warnings)
    def test_no_ocr_no_gate(self):             assert V.validate(doc(ocr_mean_confidence=None)).is_valid

class TestEnvelope:
    def test_envelope_errors(self):
        doc_ = doc(full_text="")
        r = V.validate(doc_)
        env = V.to_error_envelope(doc_, r)
        assert env.document_id == "d1" and env.errors == r.errors
