"""RootOrchestrator — decomposes user intent and manages global state."""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class RootOrchestrator(BaseAgent):
    name = "RootOrchestrator"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("plan", self._plan)
        graph.add_node("check_hitl", self._check_hitl)
        graph.add_node("dispatch", self._dispatch)

        graph.set_entry_point("classify_intent")
        graph.add_edge("classify_intent", "plan")
        graph.add_edge("plan", "check_hitl")
        graph.add_conditional_edges(
            "check_hitl",
            lambda s: "pause" if s.get("hitl_required") else "dispatch",
            {"pause": END, "dispatch": "dispatch"},
        )
        graph.add_edge("dispatch", END)

        return graph

    async def _classify_intent(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): call EuriClient with classify_intent prompt
        state["last_node"] = "classify_intent"
        return state

    async def _plan(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): generate Plan with Planner node
        state["last_node"] = "plan"
        return state

    async def _check_hitl(self, state: AgentState) -> AgentState:
        from corpmind.agents.hitl import should_require_hitl
        state["hitl_required"] = should_require_hitl(state)
        if state["hitl_required"]:
            state["status"] = "paused_hitl"
        state["last_node"] = "check_hitl"
        return state

    async def _dispatch(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): fan-out to sub-agents based on plan
        state["last_node"] = "dispatch"
        state["status"] = "completed"
        return state
