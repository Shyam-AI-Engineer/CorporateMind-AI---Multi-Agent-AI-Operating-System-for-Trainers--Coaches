"""AnalyticsAgent — daily rollups, insight cards, anomaly detection."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class AnalyticsAgent(BaseAgent):
    name = "AnalyticsAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("compute_rollup", self._compute_rollup)
        graph.add_node("detect_anomalies", self._detect_anomalies)
        graph.add_node("generate_insights", self._generate_insights)
        graph.set_entry_point("compute_rollup")
        graph.add_edge("compute_rollup", "detect_anomalies")
        graph.add_edge("detect_anomalies", "generate_insights")
        graph.add_edge("generate_insights", END)
        return graph

    async def _compute_rollup(self, state: AgentState) -> AgentState:
        state["last_node"] = "compute_rollup"
        return state

    async def _detect_anomalies(self, state: AgentState) -> AgentState:
        state["last_node"] = "detect_anomalies"
        return state

    async def _generate_insights(self, state: AgentState) -> AgentState:
        state["last_node"] = "generate_insights"
        state["status"] = "completed"
        return state
