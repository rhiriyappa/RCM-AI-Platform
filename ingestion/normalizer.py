"""ingestion/normalizer.py — maps every source format to canonical RawDocument."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from contracts.schemas import DocumentType, RawDocument, SourceType
from ingestion.adapters import RawPayload
from ingestion.format_parsers import EDI837Parser, FHIRR4Parser, HL7V2Parser
from ingestion.textract_ocr import OCRResult


class Normalizer:
    _hl7  = HL7V2Parser()
    _fhir = FHIRR4Parser()
    _edi  = EDI837Parser()

    def normalize(self, payload: RawPayload, ocr_result: Optional[OCRResult] = None) -> RawDocument:
        extracted = self._extract_structured(payload)
        full_text = ocr_result.full_text if ocr_result else payload.raw_bytes.decode("utf-8", errors="replace")
        return RawDocument(
            document_id=str(uuid.uuid4()), source_id=payload.source_id,
            source_type=payload.source_type, document_type=DocumentType.UNKNOWN,
            ingested_at=datetime.now(timezone.utc), full_text=full_text,
            page_count=len(ocr_result.page_texts) if ocr_result else 1,
            ocr_mean_confidence=ocr_result.mean_confidence if ocr_result else None,
            patient_name=extracted.get("patient_name", ""),
            patient_dob=extracted.get("patient_dob", ""),
            patient_id=extracted.get("patient_id", ""),
            diagnosis_codes=extracted.get("diagnosis_codes", []),
            procedure_codes=extracted.get("procedure_codes", []),
            payer_id=extracted.get("payer_id", ""),
            raw_metadata={**payload.metadata, "content_type": payload.content_type},
        )

    def _extract_structured(self, payload: RawPayload) -> dict[str, Any]:
        if payload.source_type == SourceType.HL7_V2:
            return self._hl7.parse(payload.raw_bytes)
        if payload.source_type == SourceType.FHIR_R4:
            return self._fhir.parse(payload.raw_bytes)
        if payload.source_type == SourceType.EDI_837:
            return self._edi.parse(payload.raw_bytes)
        return {}
