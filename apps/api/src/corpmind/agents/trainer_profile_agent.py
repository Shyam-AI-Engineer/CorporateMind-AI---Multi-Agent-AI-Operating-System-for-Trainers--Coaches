"""TrainerProfileAgent — extracts niche, topics, tone, pricing from uploads."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class TrainerProfileAgent(BaseAgent):
    name = "TrainerProfileAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("extract", self._extract)
        graph.add_node("validate", self._validate)
        graph.set_entry_point("extract")
        graph.add_edge("extract", "validate")
        graph.add_edge("validate", END)
        return graph

    async def _extract(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): call EuriClient with trainer_profile.extract prompt
        state["last_node"] = "extract"
        return state

    async def _validate(self, state: AgentState) -> AgentState:
        state["last_node"] = "validate"
        state["status"] = "completed"
        return state
