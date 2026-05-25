"""TelegramAgent — channel broadcasts, community nurture."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class TelegramAgent(BaseAgent):
    name = "TelegramAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("compose", self._compose)
        graph.add_node("broadcast", self._broadcast)
        graph.set_entry_point("compose")
        graph.add_edge("compose", "broadcast")
        graph.add_edge("broadcast", END)
        return graph

    async def _compose(self, state: AgentState) -> AgentState:
        state["last_node"] = "compose"
        return state

    async def _broadcast(self, state: AgentState) -> AgentState:
        state["last_node"] = "broadcast"
        state["status"] = "completed"
        return state
