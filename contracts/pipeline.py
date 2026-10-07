"""contracts/pipeline.py — data contracts for the phased sample-data pipeline."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from contracts.schemas import AgentState, ClassificationResult, ExtractionResult, RawDocument


class Disposition(StrEnum):
    """Where a record ended up. None on a PipelineRecord means it is still in flight."""
    COMPLETED    = "completed"         # agent finished with no human needed
    HITL         = "needs_hitl"        # agent paused for a human checkpoint
    HUMAN_REVIEW = "human_review"      # unclassifiable or extraction unusable
    DLQ          = "dlq"               # rejected by ingestion validation
    ROUTED       = "routed_no_agent"   # classified and queued, no agent for that type yet
    FAILED       = "failed"            # agent raised or reported failure


class PipelineRecord(BaseModel):
    """One sample file carried through every phase. Each phase fills in its own slot."""
    record_id:  str
    source:     str                    # sample_data sub-directory: fax, hl7v2, ...
    file:       str

    document:            RawDocument | None = None
    validation_errors:   list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    classification:      ClassificationResult | None = None
    extraction:          ExtractionResult | None = None
    governance:          dict[str, Any] = Field(default_factory=dict)
    agent:               AgentState | None = None

    disposition:      Disposition | None = None
    stages_completed: list[str] = Field(default_factory=list)
    stage_ms:         dict[str, float] = Field(default_factory=dict)
    errors:           list[str] = Field(default_factory=list)

    @property
    def in_flight(self) -> bool:
        return self.disposition is None


class PipelineReport(BaseModel):
    total_records:        int
    by_source:            dict[str, int]
    by_disposition:       dict[str, int]
    by_document_type:     dict[str, int]
    by_classifier_method: dict[str, int]
    by_agent:             dict[str, int]
    mean_extraction_confidence: float
    llm_calls:            int
    llm_cost_usd:         float
    llm_mean_latency_ms:  float
    stage_mean_ms:        dict[str, float]
    eval_mean_f1:         float | None = None
    eval_passed:          bool | None = None
