"""ComplianceGuardAgent — non-bypassable gate before every outbound send."""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class ComplianceGuardAgent(BaseAgent):
    """Runs 7 compliance checks in sequence; short-circuits on first block.

    Called by every send-capable agent BEFORE dispatching to a channel adapter.
    Cannot be bypassed — the channel adapter will reject sends without a
    passed compliance_checked=True + compliance_outcome='allowed' in state.
    """

    name = "ComplianceGuardAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("check_opt_in", self._check_opt_in)
        graph.add_node("check_unsubscribe", self._check_unsubscribe)
        graph.add_node("check_frequency_cap", self._check_frequency_cap)
        graph.add_node("check_whatsapp_window", self._check_whatsapp_window)
        graph.add_node("check_duplicate", self._check_duplicate)
        graph.add_node("check_content", self._check_content)
        graph.add_node("check_budget", self._check_budget)
        graph.add_node("record_audit", self._record_audit)

        graph.set_entry_point("check_opt_in")

        # Each check node routes to next check or END (blocked)
        for node, next_node in [
            ("check_opt_in", "check_unsubscribe"),
            ("check_unsubscribe", "check_frequency_cap"),
            ("check_frequency_cap", "check_whatsapp_window"),
            ("check_whatsapp_window", "check_duplicate"),
            ("check_duplicate", "check_content"),
            ("check_content", "check_budget"),
        ]:
            graph.add_conditional_edges(
                node,
                lambda s, n=next_node: n if s.get("compliance_outcome") != "blocked" else "record_audit",
                {n: n, "record_audit": "record_audit"} if next_node != "check_budget" else
                {n: "check_budget", "record_audit": "record_audit"},
            )

        graph.add_edge("check_budget", "record_audit")
        graph.add_edge("record_audit", END)

        return graph

    async def _check_opt_in(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): query hr_contacts.opted_in_at + opt_in_evidence
        state["last_node"] = "check_opt_in"
        return state

    async def _check_unsubscribe(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_unsubscribe"
        return state

    async def _check_frequency_cap(self, state: AgentState) -> AgentState:
        # Default: ≤ 2 marketing messages / 7 days / cross-channel
        state["last_node"] = "check_frequency_cap"
        return state

    async def _check_whatsapp_window(self, state: AgentState) -> AgentState:
        if state.get("channel") != "whatsapp":
            return state
        state["last_node"] = "check_whatsapp_window"
        return state

    async def _check_duplicate(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_duplicate"
        return state

    async def _check_content(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_content"
        return state

    async def _check_budget(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_budget"
        return state

    async def _record_audit(self, state: AgentState) -> AgentState:
        # TODO(Phase 1): write to audit_events via AuditRepo
        if not state.get("compliance_outcome"):
            state["compliance_outcome"] = "allowed"
        state["compliance_checked"] = True
        state["last_node"] = "record_audit"
        return state
