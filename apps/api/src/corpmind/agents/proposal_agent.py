"""ProposalAgent — generates pitch decks, agendas, and pricing documents."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class ProposalAgent(BaseAgent):
    name = "ProposalAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("generate", self._generate)
        graph.add_node("render_pdf", self._render_pdf)
        graph.set_entry_point("generate")
        graph.add_edge("generate", "render_pdf")
        graph.add_edge("render_pdf", END)
        return graph

    async def _generate(self, state: AgentState) -> AgentState:
        state["last_node"] = "generate"
        return state

    async def _render_pdf(self, state: AgentState) -> AgentState:
        state["last_node"] = "render_pdf"
        state["status"] = "completed"
        return state
