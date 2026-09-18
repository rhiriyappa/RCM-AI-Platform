"""contracts/schemas.py — canonical data contracts for the entire platform."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class SourceType(StrEnum):
    FAX_S3  = "fax_s3"
    HL7_V2  = "hl7_v2"
    FHIR_R4 = "fhir_r4"
    EDI_837 = "edi_837"
    WEBHOOK = "webhook"


class DocumentType(StrEnum):
    REFERRAL      = "referral"
    PRIOR_AUTH    = "prior_auth"
    DENIAL_EOB    = "denial_eob"
    CLAIM_837     = "claim_837"
    CLINICAL_NOTE = "clinical_note"
    ELIGIBILITY   = "eligibility"
    UNKNOWN       = "unknown"


class AgentStatus(StrEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    NEEDS_HITL = "needs_hitl"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── Phase 1 ───────────────────────────────────────────────────────────────────

class RawDocument(BaseModel):
    """Canonical ingest contract. Immutable after creation."""
    model_config = {"frozen": True}

    document_id:         str
    source_id:           str
    source_type:         SourceType
    document_type:       DocumentType  = DocumentType.UNKNOWN
    ingested_at:         datetime
    full_text:           str           = ""
    page_count:          int           = Field(default=1, ge=1)
    ocr_mean_confidence: Optional[float] = None
    patient_name:        str           = ""
    patient_dob:         str           = ""
    patient_id:          str           = ""
    diagnosis_codes:     list[str]     = Field(default_factory=list)
    procedure_codes:     list[str]     = Field(default_factory=list)
    payer_id:            str           = ""
    raw_metadata:        dict[str, Any] = Field(default_factory=dict)

    @field_validator("diagnosis_codes", "procedure_codes", mode="before")
    @classmethod
    def deduplicate_codes(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for c in v:
            s = c.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out


# ── Phase 2 ───────────────────────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    document_id:    str
    document_type:  DocumentType
    confidence:     float              = Field(ge=0.0, le=1.0)
    runner_up_type: Optional[DocumentType] = None
    runner_up_conf: Optional[float]    = None
    method:         str                = "ensemble"
    routing_queue:  str                = ""


class ExtractedField(BaseModel):
    field_name:  str
    value:       Any
    confidence:  float              = Field(ge=0.0, le=1.0)
    source:      str                = "llm"
    page_ref:    Optional[int]      = None
    char_span:   Optional[tuple[int, int]] = None


class ExtractionResult(BaseModel):
    model_config = {"frozen": True}

    document_id:    str
    document_type:  DocumentType
    extracted_at:   datetime

    patient_name:   Optional[ExtractedField] = None
    patient_dob:    Optional[ExtractedField] = None
    patient_id:     Optional[ExtractedField] = None
    member_id:      Optional[ExtractedField] = None
    provider_name:  Optional[ExtractedField] = None
    provider_npi:   Optional[ExtractedField] = None

    diagnosis_codes:  list[ExtractedField]   = Field(default_factory=list)
    procedure_codes:  list[ExtractedField]   = Field(default_factory=list)
    service_date:     Optional[ExtractedField] = None
    place_of_service: Optional[ExtractedField] = None

    payer_id:         Optional[ExtractedField] = None
    payer_name:       Optional[ExtractedField] = None
    claim_number:     Optional[ExtractedField] = None
    total_charge:     Optional[ExtractedField] = None

    denial_reason_codes: list[ExtractedField] = Field(default_factory=list)
    denial_date:      Optional[ExtractedField] = None
    appeal_deadline:  Optional[ExtractedField] = None

    auth_number:      Optional[ExtractedField] = None
    auth_status:      Optional[ExtractedField] = None

    mean_confidence:      float      = 0.0
    low_conf_fields:      list[str]  = Field(default_factory=list)
    extraction_warnings:  list[str]  = Field(default_factory=list)

    npi_validated:        bool = False
    codes_validated:      bool = False


# ── Phase 3 ───────────────────────────────────────────────────────────────────

class PromptTemplate(BaseModel):
    name:         str
    version:      str
    document_type: Optional[DocumentType] = None
    system:       str
    user_template: str
    model:        str   = "claude-sonnet-4-20250514"
    max_tokens:   int   = 2048
    temperature:  float = 0.0


class ModelCallRecord(BaseModel):
    call_id:       str
    document_id:   str
    model:         str
    prompt_name:   str
    prompt_version: str
    input_tokens:  int
    output_tokens: int
    latency_ms:    float
    cost_usd:      float
    success:       bool
    error:         Optional[str] = None
    called_at:     datetime


# ── Phase 4 ───────────────────────────────────────────────────────────────────

class AgentState(BaseModel):
    """Shared state passed through all LangGraph agent nodes."""
    document_id:   str
    document_type: DocumentType
    raw_doc:       Optional[dict[str, Any]] = None
    extraction:    Optional[dict[str, Any]] = None
    status:        AgentStatus = AgentStatus.PENDING
    hitl_required: bool        = False
    hitl_reason:   str         = ""
    output:        dict[str, Any] = Field(default_factory=dict)
    errors:        list[str]   = Field(default_factory=list)
    audit_trail:   list[dict[str, Any]] = Field(default_factory=list)


# ── Shared ────────────────────────────────────────────────────────────────────

class ErrorEnvelope(BaseModel):
    document_id:  str
    source_id:    str
    errors:       list[str]
    warnings:     list[str]
    raw_snapshot: dict[str, Any]
