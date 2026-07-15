"""ComplianceGuardAgent — non-bypassable gate before every outbound send.

PRODUCTION-SAFETY CONTRACT
──────────────────────────
• Implemented checks (opt_in, unsubscribe): enforce or return COMPLIANCE_ERROR.
• Unimplemented checks (frequency_cap, whatsapp_window, duplicate, content, budget):
  explicitly SKIPPED — never silently pass, always log a warning.
• DB failure in ANY check → compliance_outcome="error", send is blocked.
• DB failure in audit write → compliance_outcome="error", send is blocked.

Routing: blocked|error outcomes short-circuit directly to record_audit,
skipping remaining checks.
"""

from __future__ import annotations

import hashlib
import uuid

import structlog
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState
from corpmind.modules.compliance.schemas import ComplianceCheckRequest, ComplianceOutcome
from corpmind.modules.compliance.service import ComplianceService

log = structlog.get_logger(__name__)

# Outcomes that abort remaining checks and go directly to audit.
_ABORT_OUTCOMES = frozenset({"blocked", "error"})


class ComplianceGuardAgent(BaseAgent):
    """Runs 7 compliance checks in sequence; short-circuits on first block or error.

    Called by every send-capable agent BEFORE dispatching to a channel adapter.
    Cannot be bypassed — the channel adapter will reject sends without
    compliance_checked=True + compliance_outcome='allowed' in state.
    """

    name = "ComplianceGuardAgent"

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)
        self._compliance: ComplianceService | None = (
            ComplianceService(session) if session is not None else None
        )

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
                _make_route(next_node),
                {next_node: next_node, "record_audit": "record_audit"},
            )

        graph.add_edge("check_budget", "record_audit")
        graph.add_edge("record_audit", END)

        return graph

    # ── Implemented checks ────────────────────────────────────────────────────

    async def _check_opt_in(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_opt_in"
        req = self._build_req(state)

        if req is None or self._compliance is None:
            log.warning(
                "compliance.check.skipped",
                check="opt_in",
                reason="missing_contact_id_or_db_session",
            )
            state["compliance_outcome"] = "error"
            state["compliance_reason"] = "opt_in skipped: missing contact_id or DB session"
            return state

        try:
            result = await self._compliance.check_opt_in(req)
        except Exception as exc:
            log.error("compliance.opt_in.db_error", error=str(exc))
            state["compliance_outcome"] = "error"
            state["compliance_reason"] = f"opt_in DB error: {exc!s}"
            return state

        if result.outcome == ComplianceOutcome.BLOCKED:
            log.info(
                "compliance.opt_in.failed",
                contact_id=str(req.contact_id),
                reason=result.reason,
            )
            state["compliance_outcome"] = "blocked"
            state["compliance_reason"] = result.reason
            if result.audit_event_id:
                state["compliance_audit_id"] = str(result.audit_event_id)
        else:
            log.info("compliance.opt_in.passed", contact_id=str(req.contact_id))

        return state

    async def _check_unsubscribe(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_unsubscribe"
        req = self._build_req(state)

        if req is None or self._compliance is None:
            log.warning(
                "compliance.check.skipped",
                check="unsubscribe",
                reason="missing_contact_id_or_db_session",
            )
            state["compliance_outcome"] = "error"
            state["compliance_reason"] = "unsubscribe skipped: missing contact_id or DB session"
            return state

        try:
            result = await self._compliance.check_unsubscribe_by_contact_id(req)
        except Exception as exc:
            log.error("compliance.unsubscribe.db_error", error=str(exc))
            state["compliance_outcome"] = "error"
            state["compliance_reason"] = f"unsubscribe DB error: {exc!s}"
            return state

        if result.outcome == ComplianceOutcome.BLOCKED:
            log.info(
                "compliance.unsubscribe.failed",
                contact_id=str(req.contact_id),
                reason=result.reason,
            )
            state["compliance_outcome"] = "blocked"
            state["compliance_reason"] = result.reason
            if result.audit_event_id:
                state["compliance_audit_id"] = str(result.audit_event_id)
        else:
            log.info("compliance.unsubscribe.passed", contact_id=str(req.contact_id))

        return state

    # ── Explicitly skipped checks (Phase 1 stubs) ─────────────────────────────
    # These never silently PASS. They log a warning and continue.
    # Remaining checks route through; only opt_in and unsubscribe are enforced.

    async def _check_frequency_cap(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_frequency_cap"
        log.warning(
            "compliance.check.skipped",
            check="frequency_cap",
            reason="not_implemented_phase1",
        )
        return state

    async def _check_whatsapp_window(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_whatsapp_window"
        if state.get("channel") == "whatsapp":
            log.warning(
                "compliance.check.skipped",
                check="whatsapp_window",
                reason="not_implemented_phase1",
            )
        return state

    async def _check_duplicate(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_duplicate"
        log.warning(
            "compliance.check.skipped",
            check="duplicate",
            reason="not_implemented_phase1",
        )
        return state

    async def _check_content(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_content"
        log.warning(
            "compliance.check.skipped",
            check="content",
            reason="not_implemented_phase1",
        )
        return state

    async def _check_budget(self, state: AgentState) -> AgentState:
        state["last_node"] = "check_budget"
        log.warning(
            "compliance.check.skipped",
            check="budget",
            reason="not_implemented_phase1",
        )
        return state

    # ── Audit ─────────────────────────────────────────────────────────────────

    async def _record_audit(self, state: AgentState) -> AgentState:
        """Write the compliance decision to the audit trail.

        A DB failure here is fatal — compliance cannot be confirmed without a
        durable audit record.  Sets compliance_outcome='error' on any exception.
        """
        state["last_node"] = "record_audit"

        if self._compliance is None:
            log.error(
                "compliance.audit.no_session",
                reason="Cannot write audit record without DB session",
            )
            state["compliance_outcome"] = "error"
            state["compliance_checked"] = True
            return state

        # Finalise the outcome before writing — if no check blocked/errored, allow.
        outcome = state.get("compliance_outcome")
        if outcome not in ("blocked", "error"):
            outcome = "allowed"
            state["compliance_outcome"] = "allowed"

        try:
            await self._compliance.record_audit_event(
                event_type="compliance.decision",
                outcome=outcome,
                reason=state.get("compliance_reason"),
                event_data={
                    "contact_id": state.get("contact_id"),
                    "campaign_id": state.get("campaign_id"),
                    "workspace_id": state.get("workspace_id"),
                    "channel": state.get("channel"),
                    "run_id": state.get("run_id"),
                    "request_id": state.get("request_id"),
                },
            )
            log.info(
                "compliance.audit.recorded",
                outcome=outcome,
                contact_id=state.get("contact_id"),
                campaign_id=state.get("campaign_id"),
            )
        except Exception as exc:
            log.error("compliance.audit.write_failed", error=str(exc))
            state["compliance_outcome"] = "error"
            state["compliance_checked"] = True
            return state

        state["compliance_checked"] = True
        return state

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_req(self, state: AgentState) -> ComplianceCheckRequest | None:
        """Extract contact_id + channel from state and build a ComplianceCheckRequest."""
        contact_id_str = state.get("contact_id")
        channel = state.get("channel")
        if not contact_id_str or not channel:
            return None
        try:
            contact_id = uuid.UUID(contact_id_str)
        except ValueError:
            return None
        campaign_id_str = state.get("campaign_id")
        campaign_id = uuid.UUID(campaign_id_str) if campaign_id_str else None
        return ComplianceCheckRequest(
            contact_id=contact_id,
            channel=channel,
            content_hash=_state_content_hash(contact_id, channel),
            campaign_id=campaign_id,
            # recipient_hash: may be pre-populated in state by orchestrating agents;
            # check_unsubscribe_by_contact_id computes it from email when absent.
            recipient_hash=state.get("contact_context", {}).get("email_hash"),
        )


# ── Module-level helpers ──────────────────────────────────────────────────────

def _make_route(next_node: str):
    """Return a LangGraph routing function that short-circuits to audit on abort."""
    def _route(state: AgentState) -> str:
        if state.get("compliance_outcome") in _ABORT_OUTCOMES:
            return "record_audit"
        return next_node
    return _route


def _state_content_hash(contact_id: uuid.UUID, channel: str) -> str:
    return hashlib.sha256(f"{contact_id}:{channel}".encode()).hexdigest()
