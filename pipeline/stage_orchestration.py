"""pipeline/stage_orchestration.py — Phase 3: guardrails, fallback chain and human escalation.

Model routing and PII redaction happen inside the extraction stage (they wrap the LLM call).
This stage governs the *result*: schema/output guardrails, then the LLM → rules → human chain,
run as a LangChain Runnable chain (see orchestration/langchain_chain.py).
"""
from __future__ import annotations

import time

from contracts.pipeline import Disposition, PipelineRecord
from contracts.schemas import ExtractedField, ExtractionResult, RawDocument
from extraction.engine import HUMAN_REVIEW_THRESHOLD
from orchestration.langchain_chain import OrchestrationInput, run_orchestration
from pipeline.context import PipelineContext

STAGE = "orchestration"
REQUIRED_KEYS = ["document_id", "document_type", "mean_confidence"]
RULES_CONFIDENCE = 0.70


def rules_extraction(doc: RawDocument, base: ExtractionResult) -> ExtractionResult:
    """Fallback tier: rebuild the result from the fields ingestion already parsed deterministically."""
    def field(name: str, value: str) -> ExtractedField | None:
        return ExtractedField(field_name=name, value=value, confidence=RULES_CONFIDENCE,
                              source="rules") if value else None

    dx = [ExtractedField(field_name="diagnosis_codes", value=c, confidence=RULES_CONFIDENCE, source="rules")
          for c in doc.diagnosis_codes]
    px = [ExtractedField(field_name="procedure_codes", value=c, confidence=RULES_CONFIDENCE, source="rules")
          for c in doc.procedure_codes]
    if not (doc.patient_name or dx or px):
        raise ValueError("no structured fields available for rules fallback")
    return base.model_copy(update={
        "patient_name": field("patient_name", doc.patient_name), "patient_dob": field("patient_dob", doc.patient_dob),
        "patient_id": field("patient_id", doc.patient_id), "payer_id": field("payer_id", doc.payer_id),
        "diagnosis_codes": dx, "procedure_codes": px, "mean_confidence": RULES_CONFIDENCE,
        "extraction_warnings": [*base.extraction_warnings, "rules_fallback_used"]})


def run(records: list[PipelineRecord], ctx: PipelineContext) -> list[PipelineRecord]:
    for rec in (r for r in records if r.in_flight):
        t0 = time.perf_counter()
        ex, doc = rec.extraction, rec.document
        result = run_orchestration(OrchestrationInput(
            extraction=ex, rules_fn=lambda doc=doc, ex=ex: rules_extraction(doc, ex),
            required_keys=REQUIRED_KEYS, min_confidence=HUMAN_REVIEW_THRESHOLD))

        rec.governance.update(schema_ok=result.schema.passed, output_ok=result.output.passed,
                              guardrail_failures=result.schema.failures + result.output.failures)
        fb = result.fallback
        rec.governance.update(fallback_source=fb.source, used_fallback=fb.used_fallback)
        if fb.source == "rules":
            rec.extraction = fb.value
        elif fb.source == "human_queue":
            rec.disposition = Disposition.HUMAN_REVIEW
            rec.errors.append("orchestration: extraction unusable after fallback — sent to human review")

        rec.stage_ms[STAGE] = round((time.perf_counter() - t0) * 1000, 2)
        rec.stages_completed.append(STAGE)
    return records
