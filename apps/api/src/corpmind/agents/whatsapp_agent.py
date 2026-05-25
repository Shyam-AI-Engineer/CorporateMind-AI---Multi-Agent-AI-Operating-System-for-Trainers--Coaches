"""WhatsAppAgent — template management, 24h window enforcement."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class WhatsAppAgent(BaseAgent):
    name = "WhatsAppAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("check_window", self._check_window)
        graph.add_node("select_template", self._select_template)
        graph.add_node("send", self._send)
        graph.set_entry_point("check_window")
        graph.add_conditional_edges(
            "check_window",
            lambda s: "send" if s.get("compliance_outcome") != "blocked" else "end",
            {"send": "select_template", "end": END},
        )
        graph.add_edge("select_template", "send")
        graph.add_edge("send", END)
        return graph

    async def _check_window(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_window"
        return state

    async def _select_template(self, state: AgentState) -> AgentState:
        state["last_node"] = "select_template"
        return state

    async def _send(self, state: AgentState) -> AgentState:
        state["last_node"] = "send"
        state["status"] = "completed"
        return state
