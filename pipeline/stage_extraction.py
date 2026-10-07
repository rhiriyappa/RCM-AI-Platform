"""pipeline/stage_extraction.py — Phase 2b: LLM field extraction, OCR penalty, completeness."""
from __future__ import annotations

import time

from contracts.pipeline import PipelineRecord
from extraction.confidence import apply_ocr_penalty, score_completeness
from extraction.prompts import VERSION
from orchestration.guardrails import redact_pii
from orchestration.model_router import route
from pipeline.context import PipelineContext
from pipeline.stage_observability import instrument

STAGE = "extraction"


def run(records: list[PipelineRecord], ctx: PipelineContext) -> list[PipelineRecord]:
    for rec in (r for r in records if r.in_flight):
        t0 = time.perf_counter()
        doc, clf = rec.document, rec.classification

        # The model text is redacted first: PII patterns never reach the LLM.
        safe_text = redact_pii(doc.full_text)
        choice = route("extraction", len(safe_text), prefer_local=ctx.use_slm)
        rec.governance.update(model=choice.model_id, model_tier=choice.tier.value,
                              pii_redacted=safe_text != doc.full_text,
                              prompt=f"extraction-{clf.document_type.value}:{VERSION}")

        engine = ctx.engine
        original = engine._call_llm
        engine._call_llm = instrument(original, ctx, doc.document_id, choice.model_id,
                                      rec.governance["prompt"].split(":")[0], VERSION)
        try:
            result = engine.extract(doc.model_copy(update={"full_text": safe_text}), clf)
        finally:
            engine._call_llm = original

        result = apply_ocr_penalty(result, doc.ocr_mean_confidence)
        rec.extraction = result
        rec.governance["completeness"] = score_completeness(result)
        rec.stage_ms[STAGE] = round((time.perf_counter() - t0) * 1000, 2)
        rec.stages_completed.append(STAGE)
    return records
