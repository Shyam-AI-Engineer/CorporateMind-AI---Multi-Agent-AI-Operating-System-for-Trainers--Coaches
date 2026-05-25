"""CampaignOptimizer — post-hoc analysis of segment × channel × tone performance."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class CampaignOptimizer(BaseAgent):
    name = "CampaignOptimizer"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("load_outcomes", self._load_outcomes)
        graph.add_node("analyze", self._analyze)
        graph.add_node("propose_adjustments", self._propose_adjustments)
        graph.set_entry_point("load_outcomes")
        graph.add_edge("load_outcomes", "analyze")
        graph.add_edge("analyze", "propose_adjustments")
        graph.add_edge("propose_adjustments", END)
        return graph

    async def _load_outcomes(self, state: AgentState) -> AgentState:
        state["last_node"] = "load_outcomes"
        return state

    async def _analyze(self, state: AgentState) -> AgentState:
        state["last_node"] = "analyze"
        return state

    async def _propose_adjustments(self, state: AgentState) -> AgentState:
        state["last_node"] = "propose_adjustments"
        state["status"] = "completed"
        return state
