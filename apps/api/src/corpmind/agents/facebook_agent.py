"""FacebookAgent — page publishing, event promotion."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class FacebookAgent(BaseAgent):
    name = "FacebookAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("compose_post", self._compose_post)
        graph.add_node("publish", self._publish)
        graph.set_entry_point("compose_post")
        graph.add_edge("compose_post", "publish")
        graph.add_edge("publish", END)
        return graph

    async def _compose_post(self, state: AgentState) -> AgentState:
        state["last_node"] = "compose_post"
        return state

    async def _publish(self, state: AgentState) -> AgentState:
        state["last_node"] = "publish"
        state["status"] = "completed"
        return state
