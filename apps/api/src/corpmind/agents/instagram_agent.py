"""InstagramAgent — Reel captions, story automation, hashtag intelligence."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState


class InstagramAgent(BaseAgent):
    name = "InstagramAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("generate_caption", self._generate_caption)
        graph.add_node("generate_hashtags", self._generate_hashtags)
        graph.add_node("schedule", self._schedule)
        graph.set_entry_point("generate_caption")
        graph.add_edge("generate_caption", "generate_hashtags")
        graph.add_edge("generate_hashtags", "schedule")
        graph.add_edge("schedule", END)
        return graph

    async def _generate_caption(self, state: AgentState) -> AgentState:
        state["last_node"] = "generate_caption"
        return state

    async def _generate_hashtags(self, state: AgentState) -> AgentState:
        state["last_node"] = "generate_hashtags"
        return state

    async def _schedule(self, state: AgentState) -> AgentState:
        state["last_node"] = "schedule"
        state["status"] = "completed"
        return state
