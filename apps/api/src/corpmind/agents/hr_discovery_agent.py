"""HRDiscoveryAgent — finds matching companies and opted-in HR contacts."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class HRDiscoveryAgent(BaseAgent):
    name = "HRDiscoveryAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("discover_companies", self._discover_companies)
        graph.add_node("find_contacts", self._find_contacts)
        graph.add_node("qualify", self._qualify)
        graph.set_entry_point("discover_companies")
        graph.add_edge("discover_companies", "find_contacts")
        graph.add_edge("find_contacts", "qualify")
        graph.add_edge("qualify", END)
        return graph

    async def _discover_companies(self, state: AgentState) -> AgentState:
        state["last_node"] = "discover_companies"
        return state

    async def _find_contacts(self, state: AgentState) -> AgentState:
        state["last_node"] = "find_contacts"
        return state

    async def _qualify(self, state: AgentState) -> AgentState:
        state["qualified_contact_ids"] = list(state.get("discovered_contact_ids", []))
        state["last_node"] = "qualify"
        state["status"] = "completed"
        return state
