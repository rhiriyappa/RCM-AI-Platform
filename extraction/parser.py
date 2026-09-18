"""extraction/parser.py — parse LLM JSON output → ExtractionResult."""
from __future__ import annotations
import json, logging, re
from datetime import datetime, timezone
from typing import Any, Optional
from contracts.schemas import DocumentType, ExtractedField, ExtractionResult

logger = logging.getLogger(__name__)

_CODE_FIELDS = {"diagnosis_codes", "procedure_codes", "denial_reason_codes"}


def parse_llm_output(raw: str, document_id: str, document_type: DocumentType) -> ExtractionResult:
    warnings: list[str] = []
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        warnings.append("could not parse LLM JSON response")

    fields:      dict[str, Optional[ExtractedField]] = {}
    code_fields: dict[str, list[ExtractedField]] = {k: [] for k in _CODE_FIELDS}

    for key, raw_val in data.items():
        if key in _CODE_FIELDS:
            code_fields[key] = _parse_list(raw_val, key)
        else:
            fields[key] = _parse_field(key, raw_val)

    all_fields = [f for f in fields.values() if f is not None] + \
                 [f for lst in code_fields.values() for f in lst]
    mean_conf  = round(sum(f.confidence for f in all_fields) / len(all_fields), 4) if all_fields else 0.0
    low_conf   = [f.field_name for f in all_fields if f.confidence < 0.60]

    return ExtractionResult(
        document_id=document_id, document_type=document_type,
        extracted_at=datetime.now(timezone.utc),
        patient_name=fields.get("patient_name"), patient_dob=fields.get("patient_dob"),
        patient_id=fields.get("patient_id"), member_id=fields.get("member_id"),
        provider_name=fields.get("provider_name"), provider_npi=fields.get("provider_npi"),
        diagnosis_codes=code_fields["diagnosis_codes"],
        procedure_codes=code_fields["procedure_codes"],
        service_date=fields.get("service_date"), place_of_service=fields.get("place_of_service"),
        payer_id=fields.get("payer_id"), payer_name=fields.get("payer_name"),
        claim_number=fields.get("claim_number"), total_charge=fields.get("total_charge"),
        denial_reason_codes=code_fields["denial_reason_codes"],
        denial_date=fields.get("denial_date"), appeal_deadline=fields.get("appeal_deadline"),
        auth_number=fields.get("auth_number"), auth_status=fields.get("auth_status"),
        mean_confidence=mean_conf, low_conf_fields=low_conf, extraction_warnings=warnings,
    )


def _parse_field(key: str, raw: Any) -> Optional[ExtractedField]:
    if raw is None: return None
    if isinstance(raw, dict):
        value = raw.get("value"); conf = float(raw.get("confidence", 0.8)); src = str(raw.get("source", "llm"))
    else:
        value = raw; conf = 0.75; src = "llm"
    if value is None or value == "": return None
    return ExtractedField(field_name=key, value=value, confidence=min(1.0, max(0.0, conf)), source=src)


def _parse_list(raw: Any, field_name: str) -> list[ExtractedField]:
    if not raw or not isinstance(raw, list): return []
    return [f for item in raw if (f := _parse_field(field_name, item)) is not None]
