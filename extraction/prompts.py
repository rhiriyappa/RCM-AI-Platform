"""extraction/prompts.py — versioned extraction prompt templates."""
from contracts.schemas import DocumentType

VERSION = "v1.2.0"
_BASE = f"""\
You are a healthcare RCM data extraction specialist (prompt {VERSION}).
Extract structured clinical and billing data from the document.
Return ONLY valid JSON. No preamble. Use null for missing fields. Confidence 0.0–1.0.
Each field: {{"value": <value>, "confidence": <0.0-1.0>, "source": "llm"}}
"""

_DENIAL = _BASE + """
Extract from DENIAL / EOB:
{"patient_name": field|null, "member_id": field|null, "claim_number": field|null,
 "payer_id": field|null, "payer_name": field|null,
 "diagnosis_codes": [field,...], "procedure_codes": [field,...],
 "denial_reason_codes": [field,...], "denial_date": field|null,
 "appeal_deadline": field|null, "total_charge": field|null, "service_date": field|null}
Include CARC (CO-XX, PR-XX) and RARC (N-XX, M-XX) in denial_reason_codes.
"""

_AUTH = _BASE + """
Extract from PRIOR AUTH:
{"patient_name": field|null, "patient_dob": field|null, "member_id": field|null,
 "provider_npi": field|null, "diagnosis_codes": [field,...], "procedure_codes": [field,...],
 "payer_id": field|null, "payer_name": field|null,
 "auth_number": field|null, "auth_status": field|null, "service_date": field|null}
"""

_REFERRAL = _BASE + """
Extract from REFERRAL:
{"patient_name": field|null, "patient_dob": field|null, "patient_id": field|null,
 "provider_name": field|null, "provider_npi": field|null,
 "diagnosis_codes": [field,...], "procedure_codes": [field,...],
 "service_date": field|null, "payer_id": field|null, "payer_name": field|null}
"""

_CLAIM = _BASE + """
Extract from 837 CLAIM:
{"patient_name": field|null, "patient_id": field|null, "provider_name": field|null,
 "provider_npi": field|null, "payer_id": field|null,
 "diagnosis_codes": [field,...], "procedure_codes": [field,...],
 "service_date": field|null, "place_of_service": field|null,
 "claim_number": field|null, "total_charge": field|null}
"""

_DEFAULT = _BASE + """
Extract all available clinical and billing fields:
{"patient_name": field|null, "patient_dob": field|null, "patient_id": field|null,
 "provider_name": field|null, "diagnosis_codes": [field,...],
 "procedure_codes": [field,...], "payer_id": field|null, "service_date": field|null}
"""

_MAP = {DocumentType.DENIAL_EOB: _DENIAL, DocumentType.PRIOR_AUTH: _AUTH,
        DocumentType.REFERRAL: _REFERRAL, DocumentType.CLAIM_837: _CLAIM}


def get_extraction_prompt(document_type: DocumentType) -> str:
    return _MAP.get(document_type, _DEFAULT)


def get_user_message(text: str, max_chars: int = 6000) -> str:
    truncated = text[:max_chars]
    suffix = f"\n\n[truncated to {max_chars} chars]" if len(text) > max_chars else ""
    return f"DOCUMENT:\n{truncated}{suffix}"
