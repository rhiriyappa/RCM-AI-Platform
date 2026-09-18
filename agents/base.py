"""agents/base.py — base agent class for all LangGraph-style agents."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from contracts.schemas import AgentState, AgentStatus

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Minimal LangGraph-compatible agent base.
    Each node is a method decorated with @node.
    HITL checkpoints call self._hitl_gate().
    """

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError

    def _audit(self, state: AgentState, node: str, detail: dict[str, Any]) -> AgentState:
        trail = list(state.audit_trail)
        trail.append({"node": node, "agent": self.agent_name,
                      "ts": datetime.now(UTC).isoformat(), **detail})
        return state.model_copy(update={"audit_trail": trail})

    def _hitl_gate(self, state: AgentState, reason: str) -> AgentState:
        logger.info("[%s] HITL required: %s", state.document_id, reason)
        return state.model_copy(update={"status": AgentStatus.NEEDS_HITL,
                                        "hitl_required": True, "hitl_reason": reason})

    def _fail(self, state: AgentState, error: str) -> AgentState:
        errors = list(state.errors) + [error]
        return state.model_copy(update={"status": AgentStatus.FAILED, "errors": errors})
