"""OutreachAgent — drafts per-recipient personalized messages with A/B variants."""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class OutreachAgent(BaseAgent):
    name = "OutreachAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("load_context", self._load_context)
        graph.add_node("generate_variants", self._generate_variants)
        graph.add_node("compliance_gate", self._compliance_gate)
        graph.add_node("persist_messages", self._persist_messages)

        graph.set_entry_point("load_context")
        graph.add_edge("load_context", "generate_variants")
        graph.add_edge("generate_variants", "compliance_gate")
        graph.add_conditional_edges(
            "compliance_gate",
            lambda s: "persist" if s.get("compliance_outcome") == "allowed" else "end",
            {"persist": "persist_messages", "end": END},
        )
        graph.add_edge("persist_messages", END)

        return graph

    async def _load_context(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): load trainer profile + HR contact context from Qdrant
        state["last_node"] = "load_context"
        return state

    async def _generate_variants(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): call EuriClient with outreach.email prompt
        state["last_node"] = "generate_variants"
        return state

    async def _compliance_gate(self, state: AgentState) -> AgentState:
        from corpmind.agents.compliance_guard import ComplianceGuardAgent
        guard = ComplianceGuardAgent()
        state = await guard.run(state, {})
        return state

    async def _persist_messages(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): persist OutboundMessage records
        state["last_node"] = "persist_messages"
        state["status"] = "completed"
        return state
