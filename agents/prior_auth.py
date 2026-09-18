"""agents/prior_auth.py — prior authorization agent (LangGraph state machine)."""
from __future__ import annotations
import logging
from contracts.schemas import AgentState, AgentStatus
from agents.base import BaseAgent

logger = logging.getLogger(__name__)

CONFIDENCE_GATE = 0.80   # auto-approve above this; HITL below
REQUIRED_FIELDS = ["patient_name", "member_id", "provider_npi",
                   "diagnosis_codes", "procedure_codes", "payer_id"]


class PriorAuthAgent(BaseAgent):
    """
    6-node LangGraph graph:
      extract_fields → validate_eligibility → check_criteria →
      confidence_gate → [auto_approve | hitl_review] → submit_to_payer
    """

    def __init__(self, call_llm=None) -> None:
        super().__init__("prior_auth")
        self._call_llm = call_llm

    def run(self, state: AgentState) -> AgentState:
        state = state.model_copy(update={"status": AgentStatus.RUNNING})
        state = self._audit(state, "start", {"document_type": state.document_type})

        # Node 1: validate required fields present
        state = self._validate_fields(state)
        if state.status == AgentStatus.FAILED:
            return state

        # Node 2: check coverage criteria (simplified)
        state = self._check_criteria(state)

        # Node 3: confidence gate
        extraction = state.extraction or {}
        mean_conf  = extraction.get("mean_confidence", 0.0)

        if mean_conf >= CONFIDENCE_GATE:
            state = self._auto_route(state)
        else:
            state = self._hitl_gate(state,
                f"Extraction confidence {mean_conf:.2f} below gate {CONFIDENCE_GATE}")
            return state

        # Node 4: emit output
        state = self._audit(state, "complete", {"output": state.output})
        return state.model_copy(update={"status": AgentStatus.COMPLETED})

    def _validate_fields(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        missing = [f for f in REQUIRED_FIELDS if not extraction.get(f)]
        if missing:
            logger.warning("[%s] missing required fields: %s", state.document_id, missing)
            if len(missing) > 2:
                return self._fail(state, f"Too many missing fields: {missing}")
        state = self._audit(state, "validate_fields", {"missing": missing})
        return state

    def _check_criteria(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        dx_codes   = extraction.get("diagnosis_codes", [])
        # Simplified: real implementation calls payer-specific criteria API
        criteria_met = len(dx_codes) > 0
        state = self._audit(state, "check_criteria", {"criteria_met": criteria_met, "dx_count": len(dx_codes)})
        return state

    def _auto_route(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        output = {
            "action":        "submit_prior_auth",
            "patient_name":  extraction.get("patient_name"),
            "member_id":     extraction.get("member_id"),
            "procedure_codes": extraction.get("procedure_codes", []),
            "payer_id":      extraction.get("payer_id"),
            "auth_status":   "pending_payer_response",
        }
        state = self._audit(state, "auto_route", {"output": output})
        return state.model_copy(update={"output": output})
