"""tests/extraction/test_enrichment.py"""
import json
import pytest
from datetime import datetime
from contracts.schemas import DocumentType, ExtractionResult, ExtractedField
from extraction.enrichment import CodeValidator, ExtractionEnricher, MockNPILookup
from extraction.parser import parse_llm_output
from extraction.confidence import apply_ocr_penalty, score_completeness


def make_result(data: dict, doc_type=DocumentType.DENIAL_EOB) -> ExtractionResult:
    return parse_llm_output(json.dumps(data), "enr-001", doc_type)


class TestMockNPILookup:
    def test_known_npi_returns_info(self):
        lookup = MockNPILookup()
        info = lookup.lookup("1234567890")
        assert info is not None
        assert info["name"] == "Dr. Jane Smith"

    def test_unknown_npi_returns_none(self):
        lookup = MockNPILookup()
        assert lookup.lookup("0000000000") is None


class TestCodeValidator:
    def test_valid_icd10_passes(self):
        cv = CodeValidator()
        assert cv.validate_icd10("M54.5") is True

    def test_invalid_icd10_fails(self):
        cv = CodeValidator()
        assert cv.validate_icd10("BADCODE") is False

    def test_valid_cpt_passes(self):
        cv = CodeValidator()
        assert cv.validate_cpt("99213") is True

    def test_invalid_cpt_fails(self):
        cv = CodeValidator()
        assert cv.validate_cpt("99999") is False


class TestExtractionEnricher:
    def setup_method(self):
        self.enricher = ExtractionEnricher(
            npi_lookup=MockNPILookup(),
            code_validator=CodeValidator(),
        )

    def test_known_npi_sets_validated_true(self):
        data = {"provider_npi": {"value": "1234567890", "confidence": 0.95}}
        result = self.enricher.enrich(make_result(data))
        assert result.npi_validated is True

    def test_unknown_npi_adds_warning(self):
        data = {"provider_npi": {"value": "0000000000", "confidence": 0.88}}
        result = self.enricher.enrich(make_result(data))
        assert result.npi_validated is False
        assert any("NPI not found" in w for w in result.extraction_warnings)

    def test_invalid_code_adds_warning(self):
        data = {"diagnosis_codes": [{"value": "BADCODE", "confidence": 0.7}]}
        result = self.enricher.enrich(make_result(data))
        assert any("reference table" in w for w in result.extraction_warnings)
        assert result.codes_validated is False

    def test_all_valid_codes_sets_validated_true(self):
        data = {
            "diagnosis_codes": [{"value": "M54.5", "confidence": 0.95}],
            "procedure_codes": [{"value": "99213", "confidence": 0.97}],
        }
        result = self.enricher.enrich(make_result(data))
        assert result.codes_validated is True


class TestOCRPenalty:
    def test_no_penalty_above_85(self):
        data = {"patient_name": {"value": "Jane", "confidence": 0.9}}
        result = make_result(data)
        enriched = apply_ocr_penalty(result, ocr_mean_confidence=90.0)
        assert enriched.patient_name.confidence == result.patient_name.confidence

    def test_penalty_applied_below_85(self):
        data = {"patient_name": {"value": "Jane", "confidence": 0.9}}
        result = make_result(data)
        enriched = apply_ocr_penalty(result, ocr_mean_confidence=60.0)
        assert enriched.patient_name.confidence < result.patient_name.confidence

    def test_no_ocr_confidence_no_penalty(self):
        data = {"patient_name": {"value": "Jane", "confidence": 0.9}}
        result = make_result(data)
        enriched = apply_ocr_penalty(result, ocr_mean_confidence=None)
        assert enriched.patient_name.confidence == result.patient_name.confidence

    def test_confidence_never_negative(self):
        data = {"patient_name": {"value": "Jane", "confidence": 0.1}}
        result = make_result(data)
        enriched = apply_ocr_penalty(result, ocr_mean_confidence=0.0)
        assert enriched.patient_name.confidence >= 0.0


class TestCompleteness:
    def test_full_result_high_score(self):
        data = {
            "patient_name": {"value": "Jane", "confidence": 0.95},
            "patient_id":   {"value": "MRN-001", "confidence": 0.97},
            "payer_id":     {"value": "BCBS", "confidence": 0.99},
            "service_date": {"value": "2024-01-01", "confidence": 0.96},
            "diagnosis_codes": [{"value": "M54.5", "confidence": 0.95}],
        }
        result = make_result(data)
        score = score_completeness(result)
        assert score >= 0.8

    def test_empty_result_low_score(self):
        result = make_result({})
        score = score_completeness(result)
        assert score == 0.0
