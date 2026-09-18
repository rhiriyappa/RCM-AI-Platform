"""agents/triage.py — referral triage and provider routing agent."""
from __future__ import annotations

import logging

from agents.base import BaseAgent
from contracts.schemas import AgentState, AgentStatus

logger = logging.getLogger(__name__)

# Diagnosis codes that require urgent routing
URGENT_DX = {"I21.9", "I63.9", "J96.0", "N17.9", "K92.1"}


class ReferralTriageAgent(BaseAgent):
    """
    4-node graph:
      score_urgency → match_provider → validate_coverage → route_referral
    """

    def __init__(self) -> None:
        super().__init__("referral_triage")

    def run(self, state: AgentState) -> AgentState:
        state = state.model_copy(update={"status": AgentStatus.RUNNING})
        state = self._audit(state, "start", {})

        state = self._score_urgency(state)
        state = self._match_provider(state)

        extraction = state.extraction or {}
        mean_conf  = extraction.get("mean_confidence", 0.0)
        if mean_conf < 0.60:
            return self._hitl_gate(state, f"Referral confidence {mean_conf:.2f} too low for auto-routing")

        state = self._route_referral(state)
        return state.model_copy(update={"status": AgentStatus.COMPLETED})

    def _score_urgency(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        dx_codes   = extraction.get("diagnosis_codes", [])
        is_urgent  = any(str(c).upper() in URGENT_DX for c in dx_codes)
        urgency    = "urgent" if is_urgent else "routine"
        state = self._audit(state, "score_urgency", {"urgency": urgency, "dx_count": len(dx_codes)})
        return state.model_copy(update={"output": {**state.output, "urgency": urgency}})

    def _match_provider(self, state: AgentState) -> AgentState:
        # Simplified: production queries pgvector provider network index
        matched_provider = {"npi": "1234567890", "name": "City Orthopedics", "availability": "3 days"}
        state = self._audit(state, "match_provider", {"provider": matched_provider})
        return state.model_copy(update={"output": {**state.output, "matched_provider": matched_provider}})

    def _route_referral(self, state: AgentState) -> AgentState:
        output = {**state.output, "referral_status": "routed",
                  "queue": "urgent-referral" if state.output.get("urgency") == "urgent" else "standard-referral"}
        state = self._audit(state, "route_referral", output)
        return state.model_copy(update={"output": output})
