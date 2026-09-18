"""agents/denial.py — denial appeal agent."""
from __future__ import annotations

import logging

from agents.base import BaseAgent
from contracts.schemas import AgentState, AgentStatus

logger = logging.getLogger(__name__)

# CARC codes that are most commonly overturnable
OVERTURNABLE_CODES = {"CO-4", "CO-11", "CO-50", "CO-97", "PR-96"}


class DenialAppealAgent(BaseAgent):
    """
    5-node graph:
      decode_denial → assess_appeal_viability →
      build_strategy → generate_letter → queue_submission
    """

    def __init__(self, call_llm=None) -> None:
        super().__init__("denial_appeal")
        self._call_llm = call_llm

    def run(self, state: AgentState) -> AgentState:
        state = state.model_copy(update={"status": AgentStatus.RUNNING})
        state = self._audit(state, "start", {"document_type": state.document_type})

        # Node 1: decode denial reason codes
        state = self._decode_denial(state)

        # Node 2: assess viability
        state = self._assess_viability(state)
        if state.output.get("appeal_viable") is False:
            state = self._audit(state, "no_appeal", {"reason": "codes not overturnable"})
            return state.model_copy(update={"status": AgentStatus.COMPLETED})

        # Node 3: build strategy
        state = self._build_strategy(state)

        # Node 4: generate letter (LLM call or HITL)
        extraction = state.extraction or {}
        mean_conf  = extraction.get("mean_confidence", 0.0)
        if mean_conf < 0.65:
            return self._hitl_gate(state, f"Low extraction confidence {mean_conf:.2f} — review before letter gen")

        state = self._generate_letter(state)
        state = self._audit(state, "complete", {"output": state.output})
        return state.model_copy(update={"status": AgentStatus.COMPLETED})

    def _decode_denial(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        raw_codes  = extraction.get("denial_reason_codes", [])
        decoded = []
        for code in raw_codes:
            code_str = str(code).upper()
            decoded.append({"code": code_str, "overturnable": code_str in OVERTURNABLE_CODES})
        state = self._audit(state, "decode_denial", {"codes": decoded})
        return state.model_copy(update={"output": {**state.output, "decoded_codes": decoded}})

    def _assess_viability(self, state: AgentState) -> AgentState:
        decoded = state.output.get("decoded_codes", [])
        viable  = any(c["overturnable"] for c in decoded)
        state = self._audit(state, "assess_viability", {"viable": viable})
        return state.model_copy(update={"output": {**state.output, "appeal_viable": viable}})

    def _build_strategy(self, state: AgentState) -> AgentState:
        decoded  = state.output.get("decoded_codes", [])
        strategy = "medical_necessity" if any(c["code"] in {"CO-50","CO-97"} for c in decoded) else "coding_correction"
        state    = self._audit(state, "build_strategy", {"strategy": strategy})
        return state.model_copy(update={"output": {**state.output, "strategy": strategy}})

    def _generate_letter(self, state: AgentState) -> AgentState:
        extraction = state.extraction or {}
        letter_meta = {
            "letter_type":    "appeal",
            "strategy":       state.output.get("strategy"),
            "patient_name":   extraction.get("patient_name"),
            "claim_number":   extraction.get("claim_number"),
            "appeal_deadline": extraction.get("appeal_deadline"),
            "letter_status":  "draft_generated",
        }
        state = self._audit(state, "generate_letter", letter_meta)
        return state.model_copy(update={"output": {**state.output, **letter_meta}})
