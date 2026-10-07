"""pipeline/stage_classification.py — Phase 2a: tiered classification and queue routing."""
from __future__ import annotations

import json
import time

from classification.routing import resolve_routing_queue
from contracts.pipeline import Disposition, PipelineRecord
from contracts.schemas import ClassificationResult, DocumentType, RawDocument, SourceType
from pipeline.context import PipelineContext

STAGE = "classification"


# Declared types carried by the source itself. Only used where the format states the type.
_WEBHOOK_EVENTS = {
    "referral.created":     DocumentType.REFERRAL,
    "prior_auth.submitted": DocumentType.PRIOR_AUTH,
    "claim.denied":         DocumentType.DENIAL_EOB,
    "eligibility.checked":  DocumentType.ELIGIBILITY,
    "note.uploaded":        DocumentType.CLINICAL_NOTE,
}
_HL7_MESSAGES = {"ORM": DocumentType.REFERRAL, "DFT": DocumentType.CLAIM_837}  # ADT (registration) is not RCM work


def _declared_type(doc: RawDocument) -> DocumentType | None:
    text = doc.full_text
    if doc.source_type == SourceType.EDI_837:
        return DocumentType.CLAIM_837
    if doc.source_type == SourceType.FHIR_R4:
        resources = {e.get("resource", {}).get("resourceType") for e in json.loads(text).get("entry", [])}
        return DocumentType.CLAIM_837 if "Claim" in resources else None
    if doc.source_type == SourceType.HL7_V2 and text.startswith("MSH|"):
        msg_type = text.splitlines()[0].split("|")[8].split("^")[0]
        return _HL7_MESSAGES.get(msg_type)
    if doc.source_type == SourceType.WEBHOOK:
        try:
            return _WEBHOOK_EVENTS.get(json.loads(text).get("event"))
        except (json.JSONDecodeError, AttributeError):
            return None
    return None


def _source_hint(doc: RawDocument) -> ClassificationResult | None:
    try:
        declared = _declared_type(doc)
    except (json.JSONDecodeError, IndexError):   # malformed payload: fall through to the text tiers
        return None
    if declared is None:
        return None
    return ClassificationResult(document_id=doc.document_id, document_type=declared, confidence=0.99,
                                method="source_hint", routing_queue=resolve_routing_queue(declared))


def run(records: list[PipelineRecord], ctx: PipelineContext) -> list[PipelineRecord]:
    for rec in (r for r in records if r.in_flight):
        t0 = time.perf_counter()
        doc = rec.document
        result = _source_hint(doc) or ctx.classifier.classify(doc)
        rec.classification = result
        rec.document = doc.model_copy(update={"document_type": result.document_type})
        if result.document_type == DocumentType.UNKNOWN:
            rec.disposition = Disposition.HUMAN_REVIEW
            rec.errors.append("classification: no confident document type — sent to human review")
        rec.stage_ms[STAGE] = round((time.perf_counter() - t0) * 1000, 2)
        rec.stages_completed.append(STAGE)
    return records
