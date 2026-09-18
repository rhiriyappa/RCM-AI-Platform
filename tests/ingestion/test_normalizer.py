"""tests/ingestion/test_normalizer.py"""
import pytest
from datetime import datetime, timezone
from contracts.schemas import DocumentType, SourceType
from ingestion.adapters import FHIRBundleAdapter, WebhookAdapter
from ingestion.normalizer import Normalizer
from ingestion.textract_ocr import OCRResult

@pytest.fixture
def bundle():
    return {"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient", "name": [{"family": "Smith", "given": ["Jane"]}],
                       "birthDate": "1978-04-12", "identifier": [{"value": "MRN-00042"}]}},
        {"resource": {"resourceType": "Coverage", "payor": [{"identifier": {"value": "BCBS-TX"}}]}},
        {"resource": {"resourceType": "Claim",
                       "diagnosis": [{"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}},
                                      {"diagnosisCodeableConcept": {"coding": [{"code": "J45.901"}]}}],
                       "item": [{"productOrService": {"coding": [{"code": "99213"}]}}]}}]}

N = Normalizer()

class TestFHIRNormalization:
    def test_patient_name(self, bundle):
        assert N.normalize(FHIRBundleAdapter().from_json(bundle, "s1")).patient_name == "Jane Smith"
    def test_patient_dob(self, bundle):
        assert N.normalize(FHIRBundleAdapter().from_json(bundle, "s1")).patient_dob == "1978-04-12"
    def test_payer_id(self, bundle):
        assert N.normalize(FHIRBundleAdapter().from_json(bundle, "s1")).payer_id == "BCBS-TX"
    def test_diagnosis_codes(self, bundle):
        doc = N.normalize(FHIRBundleAdapter().from_json(bundle, "s1"))
        assert "M54.5" in doc.diagnosis_codes and "J45.901" in doc.diagnosis_codes
    def test_procedure_codes(self, bundle):
        doc = N.normalize(FHIRBundleAdapter().from_json(bundle, "s1"))
        assert "99213" in doc.procedure_codes
    def test_document_id_is_uuid(self, bundle):
        doc = N.normalize(FHIRBundleAdapter().from_json(bundle, "s1"))
        assert len(doc.document_id) == 36
    def test_document_type_unknown(self, bundle):
        assert N.normalize(FHIRBundleAdapter().from_json(bundle, "s1")).document_type == DocumentType.UNKNOWN
    def test_deduplicate_codes(self):
        b = {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Claim",
            "diagnosis": [{"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}},
                           {"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}}],
            "item": []}}]}
        doc = N.normalize(FHIRBundleAdapter().from_json(b, "dup"))
        assert doc.diagnosis_codes.count("M54.5") == 1

class TestOCRNormalization:
    def test_uses_ocr_text(self, bundle):
        ocr = OCRResult(full_text="OCR text here", page_texts=["OCR text here"],
                        mean_confidence=91.5, job_id="j1")
        doc = N.normalize(FHIRBundleAdapter().from_json(bundle, "o1"), ocr_result=ocr)
        assert doc.full_text == "OCR text here"
        assert doc.ocr_mean_confidence == 91.5
    def test_no_ocr_decodes_raw(self):
        text = "Patient: John Doe. Diagnosis: Z00.00. Provider: Dr. Smith at City Medical."
        p = WebhookAdapter().from_request(text.encode(), {}, "w1")
        doc = N.normalize(p)
        assert "John Doe" in doc.full_text
        assert doc.ocr_mean_confidence is None
