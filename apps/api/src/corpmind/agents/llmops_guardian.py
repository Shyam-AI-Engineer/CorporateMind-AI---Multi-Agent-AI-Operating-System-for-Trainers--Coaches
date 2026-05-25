"""LLMOpsGuardian — monitors quality, triggers retries, escalates to HITL."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class LLMOpsGuardian(BaseAgent):
    name = "LLMOpsGuardian"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("assess_quality", self._assess_quality)
        graph.add_node("decide_action", self._decide_action)
        graph.set_entry_point("assess_quality")
        graph.add_edge("assess_quality", "decide_action")
        graph.add_edge("decide_action", END)
        return graph

    async def _assess_quality(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): query DLQ + Langfuse for quality signals
        state["last_node"] = "assess_quality"
        return state

    async def _decide_action(self, state: AgentState) -> AgentState:
        # retry | escalate_hitl | surface_insight
        state["last_node"] = "decide_action"
        state["status"] = "completed"
        return state
