"""Base class and utilities for all CorporateMind AI LangGraph agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog
from langgraph.graph import StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for all 14 CorporateMind agents.

    Subclasses implement `build_graph()` and register their tools.
    The runner (Celery task) calls `run()` which handles checkpointing,
    Langfuse tracing, and HITL routing.

    ``session`` is optional: agents that do not need DB access (e.g.
    ComplianceGuardAgent in its current form) can be constructed without one.
    Agents that persist state (OutreachAgent) require a session and guard
    internally in nodes that write to the DB.
    """

    name: str = ""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Build and return the compiled LangGraph for this agent."""
        ...

    async def run(self, state: AgentState, config: dict[str, Any]) -> AgentState:
        """Execute the agent graph and return the final state."""
        graph = self.build_graph()
        compiled = graph.compile()

        log.info(
            "agent.run.start",
            agent=self.name,
            run_id=state.get("run_id"),
            tenant_id=state.get("tenant_id"),
        )

        try:
            result: AgentState = await compiled.ainvoke(state, config=config)  # type: ignore[arg-type]
            log.info("agent.run.complete", agent=self.name, status=result.get("status"))
            return result
        except Exception as exc:
            log.error("agent.run.failed", agent=self.name, error=str(exc))
            state["error"] = str(exc)
            state["status"] = "failed"
            return state
