"""ingestion/validator.py — schema validation and DLQ routing."""
from __future__ import annotations
import logging, re
from dataclasses import dataclass, field
from contracts.schemas import ErrorEnvelope, RawDocument

logger = logging.getLogger(__name__)
MIN_OCR_CONFIDENCE = 60.0
MIN_TEXT_LENGTH    = 20
ICD10_RE = re.compile(r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$")
CPT_RE   = re.compile(r"^[0-9]{5}[A-Z0-9]?$")


@dataclass
class ValidationResult:
    is_valid: bool
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DocumentValidator:
    def validate(self, doc: RawDocument) -> ValidationResult:
        errors, warnings = [], []
        for f in ["full_text", "source_id", "source_type"]:
            if not getattr(doc, f, None):
                errors.append(f"Missing required field: {f}")
        if doc.ocr_mean_confidence is not None and doc.ocr_mean_confidence < MIN_OCR_CONFIDENCE:
            errors.append(f"OCR confidence {doc.ocr_mean_confidence:.1f} below threshold ({MIN_OCR_CONFIDENCE})")
        if len(doc.full_text.strip()) < MIN_TEXT_LENGTH:
            errors.append("full_text too short — likely empty or corrupt page")
        for code in doc.diagnosis_codes:
            if not ICD10_RE.match(code):
                warnings.append(f"Suspect ICD-10 format: {code!r}")
        for code in doc.procedure_codes:
            if not CPT_RE.match(code):
                warnings.append(f"Suspect CPT format: {code!r}")
        if errors:
            logger.warning("[%s] validation failed: %s", doc.document_id, errors)
        return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings)

    def to_error_envelope(self, doc: RawDocument, result: ValidationResult) -> ErrorEnvelope:
        return ErrorEnvelope(document_id=doc.document_id, source_id=doc.source_id,
                             errors=result.errors, warnings=result.warnings,
                             raw_snapshot={"source_type": doc.source_type,
                                           "ocr_confidence": doc.ocr_mean_confidence,
                                           "text_length": len(doc.full_text),
                                           "diagnosis_codes": doc.diagnosis_codes,
                                           "procedure_codes": doc.procedure_codes})
