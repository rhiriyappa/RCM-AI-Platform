"""extraction/confidence.py — OCR penalty and completeness scoring."""
from __future__ import annotations
from typing import Optional
from contracts.schemas import ExtractedField, ExtractionResult


def apply_ocr_penalty(result: ExtractionResult, ocr_mean_confidence: Optional[float]) -> ExtractionResult:
    if ocr_mean_confidence is None or ocr_mean_confidence >= 85.0:
        return result
    penalty = max(0.0, (85.0 - ocr_mean_confidence) / 85.0) * 0.25

    def adj(f: Optional[ExtractedField]) -> Optional[ExtractedField]:
        if f is None: return None
        d = f.model_dump()
        d["confidence"] = round(max(0.0, d["confidence"] - penalty), 4)
        return ExtractedField(**d)

    kwargs = result.model_dump()
    scalars = ["patient_name","patient_dob","patient_id","member_id","provider_name",
               "provider_npi","service_date","place_of_service","payer_id","payer_name",
               "claim_number","total_charge","denial_date","appeal_deadline","auth_number","auth_status"]
    for k in scalars:
        kwargs[k] = adj(getattr(result, k))
    for lk in ["diagnosis_codes","procedure_codes","denial_reason_codes"]:
        kwargs[lk] = [adj(f) for f in getattr(result, lk)]
    all_fields = [kwargs[k] for k in scalars if kwargs.get(k)] + \
                 [f for lk in ["diagnosis_codes","procedure_codes"] for f in kwargs.get(lk, [])]
    kwargs["mean_confidence"] = round(sum(f.confidence for f in all_fields) / len(all_fields), 4) if all_fields else 0.0
    kwargs["low_conf_fields"] = [f.field_name for f in all_fields if f.confidence < 0.60]
    return ExtractionResult(**kwargs)


def score_completeness(result: ExtractionResult) -> float:
    key_fields = [result.patient_name, result.patient_id, result.payer_id, result.service_date]
    populated  = sum(1 for f in key_fields if f is not None)
    code_pop   = min(1, len(result.diagnosis_codes + result.procedure_codes))
    return round((populated + code_pop) / (len(key_fields) + 1), 2)
