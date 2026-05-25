"""LinkedInAgent — public company-page posts ONLY. Never personal DMs. Ever."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class LinkedInAgent(BaseAgent):
    """Posts to public company pages only.

    Hard constraint: no personal DM automation. This is enforced in the
    LinkedIn channel adapter as well. Belt-and-suspenders.
    """

    name = "LinkedInAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("compose_post", self._compose_post)
        graph.add_node("publish_to_page", self._publish_to_page)
        graph.set_entry_point("compose_post")
        graph.add_edge("compose_post", "publish_to_page")
        graph.add_edge("publish_to_page", END)
        return graph

    async def _compose_post(self, state: AgentState) -> AgentState:
        state["last_node"] = "compose_post"
        return state

    async def _publish_to_page(self, state: AgentState) -> AgentState:
        # Company page posts ONLY — the channel adapter enforces this too
        state["last_node"] = "publish_to_page"
        state["status"] = "completed"
        return state
