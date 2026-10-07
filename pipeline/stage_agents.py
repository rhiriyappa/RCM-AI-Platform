"""pipeline/stage_agents.py — Phase 4: dispatch each record to the agent for its document type."""
from __future__ import annotations

import time
from typing import Any

from agents.base import BaseAgent
from agents.denial import DenialAppealAgent
from agents.prior_auth import PriorAuthAgent
from agents.triage import ReferralTriageAgent
from contracts.pipeline import Disposition, PipelineRecord
from contracts.schemas import AgentState, AgentStatus, DocumentType, ExtractionResult
from pipeline.context import PipelineContext

STAGE = "agents"

_AGENTS: dict[DocumentType, type[BaseAgent]] = {
    DocumentType.PRIOR_AUTH: PriorAuthAgent,
    DocumentType.DENIAL_EOB: DenialAppealAgent,
    DocumentType.REFERRAL:   ReferralTriageAgent,
}
_DISPOSITION = {AgentStatus.COMPLETED: Disposition.COMPLETED, AgentStatus.NEEDS_HITL: Disposition.HITL,
                AgentStatus.FAILED: Disposition.FAILED}


def flatten_extraction(result: ExtractionResult) -> dict[str, Any]:
    """Agents read plain values; ExtractionResult carries ExtractedField wrappers."""
    flat: dict[str, Any] = {"mean_confidence": result.mean_confidence}
    for name in ExtractionResult.model_fields:
        v = getattr(result, name)
        if isinstance(v, list) and v and hasattr(v[0], "value"):
            flat[name] = [f.value for f in v]
        elif hasattr(v, "value"):
            flat[name] = v.value
    return flat


def run(records: list[PipelineRecord], ctx: PipelineContext) -> list[PipelineRecord]:
    for rec in (r for r in records if r.in_flight):
        t0 = time.perf_counter()
        doc, clf = rec.document, rec.classification
        agent_cls = _AGENTS.get(doc.document_type)
        if agent_cls is None:
            rec.disposition = Disposition.ROUTED
            rec.governance["queue"] = clf.routing_queue
        else:
            try:
                state = AgentState(document_id=doc.document_id, document_type=doc.document_type,
                                   raw_doc=doc.model_dump(mode="json"),
                                   extraction=flatten_extraction(rec.extraction))
                rec.agent = agent_cls().run(state)
                rec.disposition = _DISPOSITION.get(rec.agent.status, Disposition.FAILED)
            except Exception as exc:
                rec.errors.append(f"agents: {type(exc).__name__}: {exc}")
                rec.disposition = Disposition.FAILED
        rec.stage_ms[STAGE] = round((time.perf_counter() - t0) * 1000, 2)
        rec.stages_completed.append(STAGE)
    return records
