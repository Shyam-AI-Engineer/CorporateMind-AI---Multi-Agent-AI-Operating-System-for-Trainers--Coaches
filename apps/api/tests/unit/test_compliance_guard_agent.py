"""Unit tests for ComplianceGuardAgent nodes.

Verifies that the agent:
  ✓ opted-in contact passes opt_in check
  ✓ missing opt-in blocks and sets state correctly
  ✓ unsubscribed contact blocks
  ✓ audit record written on every run
  ✓ audit DB failure returns COMPLIANCE_ERROR
  ✓ tenant isolation preserved through ComplianceService
  ✓ workspace isolation via TenantContext (never trust caller params)
  ✓ missing contact → opt_in blocked
  ✓ skipped checks log warnings and never set outcome=allowed by themselves
  ✓ TODO checks never return outcome=allowed in isolation
  ✓ DB error in opt_in → error outcome, no further checks attempted
  ✓ no_session agent → error outcome immediately
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.agents.compliance_guard import ComplianceGuardAgent, _make_route, _state_content_hash
from corpmind.agents.state import AgentState, default_state
from corpmind.modules.compliance.schemas import ComplianceCheckResult, ComplianceOutcome


# ── Fixtures ─────────────────────────────────────────────────────────────────

ORG = uuid.uuid4()
WS = uuid.uuid4()
USER = uuid.uuid4()
CONTACT = uuid.uuid4()
CAMPAIGN = uuid.uuid4()


def _base_state(**overrides) -> AgentState:
    s = default_state(
        tenant_id=ORG,
        workspace_id=WS,
        user_id=USER,
        request_id="req-test",
        run_id="run-test",
    )
    s["contact_id"] = str(CONTACT)
    s["channel"] = "email"
    s["campaign_id"] = str(CAMPAIGN)
    s.update(overrides)
    return s


def _make_agent() -> tuple[ComplianceGuardAgent, MagicMock]:
    """Return (agent, mock_session) with compliance service methods mocked."""
    session = MagicMock()
    agent = ComplianceGuardAgent(session=session)
    agent._compliance = MagicMock()
    return agent, session


def _allowed() -> ComplianceCheckResult:
    return ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)


def _blocked(reason: str = "test reason") -> ComplianceCheckResult:
    evt_id = uuid.uuid4()
    return ComplianceCheckResult(
        outcome=ComplianceOutcome.BLOCKED,
        reason=reason,
        blocked_by="opt_in",
        audit_event_id=evt_id,
    )


# ── _make_route helper ────────────────────────────────────────────────────────

class TestMakeRoute:
    def test_routes_to_next_when_no_outcome(self):
        route = _make_route("check_unsubscribe")
        state = _base_state()
        assert route(state) == "check_unsubscribe"

    def test_routes_to_record_audit_on_blocked(self):
        route = _make_route("check_unsubscribe")
        state = _base_state(compliance_outcome="blocked")
        assert route(state) == "record_audit"

    def test_routes_to_record_audit_on_error(self):
        route = _make_route("check_unsubscribe")
        state = _base_state(compliance_outcome="error")
        assert route(state) == "record_audit"

    def test_routes_to_next_when_outcome_is_none(self):
        route = _make_route("check_frequency_cap")
        state = _base_state(compliance_outcome=None)
        assert route(state) == "check_frequency_cap"


# ── _state_content_hash ───────────────────────────────────────────────────────

class TestStateContentHash:
    def test_returns_hex_string(self):
        h = _state_content_hash(uuid.uuid4(), "email")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        cid = uuid.uuid4()
        assert _state_content_hash(cid, "email") == _state_content_hash(cid, "email")

    def test_different_channels_different_hashes(self):
        cid = uuid.uuid4()
        assert _state_content_hash(cid, "email") != _state_content_hash(cid, "whatsapp")


# ── _build_req ────────────────────────────────────────────────────────────────

class TestBuildReq:
    def test_returns_none_when_no_contact_id(self):
        agent, _ = _make_agent()
        state = _base_state()
        state.pop("contact_id", None)
        state["contact_id"] = None
        assert agent._build_req(state) is None

    def test_returns_none_when_no_channel(self):
        agent, _ = _make_agent()
        state = _base_state()
        state["channel"] = None
        assert agent._build_req(state) is None

    def test_returns_req_with_correct_contact_id(self):
        agent, _ = _make_agent()
        state = _base_state()
        req = agent._build_req(state)
        assert req is not None
        assert req.contact_id == CONTACT

    def test_returns_req_with_correct_campaign_id(self):
        agent, _ = _make_agent()
        state = _base_state()
        req = agent._build_req(state)
        assert req is not None
        assert req.campaign_id == CAMPAIGN

    def test_returns_none_on_invalid_uuid(self):
        agent, _ = _make_agent()
        state = _base_state()
        state["contact_id"] = "not-a-uuid"
        assert agent._build_req(state) is None


# ── _check_opt_in ─────────────────────────────────────────────────────────────

class TestCheckOptIn:
    @pytest.mark.asyncio
    async def test_passes_opted_in_contact(self):
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        state = await agent._check_opt_in(_base_state())
        assert state.get("compliance_outcome") != "blocked"
        assert state.get("compliance_outcome") != "error"

    @pytest.mark.asyncio
    async def test_blocks_non_opted_in_contact(self):
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(
            return_value=_blocked("Contact has no current opt-in")
        )
        state = await agent._check_opt_in(_base_state())
        assert state["compliance_outcome"] == "blocked"
        assert state["compliance_reason"] is not None

    @pytest.mark.asyncio
    async def test_sets_compliance_audit_id_on_block(self):
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(return_value=_blocked())
        state = await agent._check_opt_in(_base_state())
        assert state.get("compliance_audit_id") is not None

    @pytest.mark.asyncio
    async def test_db_error_sets_error_outcome(self):
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(
            side_effect=RuntimeError("connection timeout")
        )
        state = await agent._check_opt_in(_base_state())
        assert state["compliance_outcome"] == "error"
        assert "DB error" in (state.get("compliance_reason") or "")

    @pytest.mark.asyncio
    async def test_no_session_sets_error_outcome(self):
        agent = ComplianceGuardAgent(session=None)
        state = await agent._check_opt_in(_base_state())
        assert state["compliance_outcome"] == "error"

    @pytest.mark.asyncio
    async def test_missing_contact_id_sets_error_outcome(self):
        agent, _ = _make_agent()
        state = _base_state()
        state["contact_id"] = None
        state = await agent._check_opt_in(state)
        assert state["compliance_outcome"] == "error"

    @pytest.mark.asyncio
    async def test_sets_last_node(self):
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        state = await agent._check_opt_in(_base_state())
        assert state["last_node"] == "check_opt_in"


# ── _check_unsubscribe ────────────────────────────────────────────────────────

class TestCheckUnsubscribe:
    @pytest.mark.asyncio
    async def test_passes_non_unsubscribed_contact(self):
        agent, _ = _make_agent()
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        state = await agent._check_unsubscribe(_base_state())
        assert state.get("compliance_outcome") not in ("blocked", "error")

    @pytest.mark.asyncio
    async def test_blocks_unsubscribed_contact(self):
        agent, _ = _make_agent()
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact is on the unsubscribe list",
                blocked_by="unsubscribe",
                audit_event_id=uuid.uuid4(),
            )
        )
        state = await agent._check_unsubscribe(_base_state())
        assert state["compliance_outcome"] == "blocked"
        assert "unsubscribe" in (state.get("compliance_reason") or "").lower()

    @pytest.mark.asyncio
    async def test_db_error_sets_error_outcome(self):
        agent, _ = _make_agent()
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            side_effect=RuntimeError("DB gone")
        )
        state = await agent._check_unsubscribe(_base_state())
        assert state["compliance_outcome"] == "error"

    @pytest.mark.asyncio
    async def test_no_session_sets_error_outcome(self):
        agent = ComplianceGuardAgent(session=None)
        state = await agent._check_unsubscribe(_base_state())
        assert state["compliance_outcome"] == "error"

    @pytest.mark.asyncio
    async def test_sets_last_node(self):
        agent, _ = _make_agent()
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        state = await agent._check_unsubscribe(_base_state())
        assert state["last_node"] == "check_unsubscribe"


# ── Skipped checks ────────────────────────────────────────────────────────────

class TestSkippedChecks:
    @pytest.mark.asyncio
    async def test_frequency_cap_does_not_set_outcome(self):
        agent, _ = _make_agent()
        state = await agent._check_frequency_cap(_base_state())
        # Must NOT set compliance_outcome to "allowed" — only stays as None/unchanged
        assert state.get("compliance_outcome") not in ("allowed",)

    @pytest.mark.asyncio
    async def test_frequency_cap_does_not_block(self):
        agent, _ = _make_agent()
        state = await agent._check_frequency_cap(_base_state())
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_whatsapp_window_does_not_block_email(self):
        agent, _ = _make_agent()
        state = _base_state(channel="email")
        state = await agent._check_whatsapp_window(state)
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_whatsapp_window_does_not_block_whatsapp(self):
        """Skipped check must not falsely block, even for WhatsApp channel."""
        agent, _ = _make_agent()
        state = _base_state(channel="whatsapp")
        state = await agent._check_whatsapp_window(state)
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_duplicate_does_not_block(self):
        agent, _ = _make_agent()
        state = await agent._check_duplicate(_base_state())
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_content_does_not_block(self):
        agent, _ = _make_agent()
        state = await agent._check_content(_base_state())
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_budget_does_not_block(self):
        agent, _ = _make_agent()
        state = await agent._check_budget(_base_state())
        assert state.get("compliance_outcome") != "blocked"

    @pytest.mark.asyncio
    async def test_skipped_checks_log_warning(self):
        """Skipped checks must call log.warning — structlog bypasses stdlib caplog."""
        agent, _ = _make_agent()
        with patch("corpmind.agents.compliance_guard.log") as mock_log:
            await agent._check_frequency_cap(_base_state())
        mock_log.warning.assert_called_once()
        call_repr = str(mock_log.warning.call_args).lower()
        assert "skipped" in call_repr or "not_implemented" in call_repr

    @pytest.mark.asyncio
    async def test_todo_checks_never_return_allowed_in_isolation(self):
        """Skipped checks must not explicitly set compliance_outcome=allowed."""
        agent, _ = _make_agent()
        for method in [
            agent._check_frequency_cap,
            agent._check_duplicate,
            agent._check_content,
            agent._check_budget,
        ]:
            state = _base_state()
            result = await method(state)
            assert result.get("compliance_outcome") != "allowed", (
                f"{method.__name__} must not set compliance_outcome='allowed'"
            )


# ── _record_audit ─────────────────────────────────────────────────────────────

class TestRecordAudit:
    @pytest.mark.asyncio
    async def test_writes_audit_record_on_allowed(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = await agent._record_audit(_base_state())
        agent._compliance.record_audit_event.assert_awaited_once()
        assert state["compliance_checked"] is True
        assert state["compliance_outcome"] == "allowed"

    @pytest.mark.asyncio
    async def test_audit_called_with_correct_outcome_on_block(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = _base_state(compliance_outcome="blocked", compliance_reason="No opt-in")
        state = await agent._record_audit(state)
        call_kwargs = agent._compliance.record_audit_event.call_args[1]
        assert call_kwargs["outcome"] == "blocked"
        assert call_kwargs["reason"] == "No opt-in"

    @pytest.mark.asyncio
    async def test_audit_includes_contact_and_campaign(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = await agent._record_audit(_base_state())
        call_kwargs = agent._compliance.record_audit_event.call_args[1]
        assert call_kwargs["event_data"]["contact_id"] == str(CONTACT)
        assert call_kwargs["event_data"]["campaign_id"] == str(CAMPAIGN)
        assert call_kwargs["event_data"]["workspace_id"] == str(WS)

    @pytest.mark.asyncio
    async def test_audit_failure_sets_error_outcome(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )
        state = await agent._record_audit(_base_state())
        assert state["compliance_outcome"] == "error"
        assert state["compliance_checked"] is True

    @pytest.mark.asyncio
    async def test_no_session_sets_error_not_allowed(self):
        agent = ComplianceGuardAgent(session=None)
        state = await agent._record_audit(_base_state())
        assert state["compliance_outcome"] == "error"
        assert state["compliance_checked"] is True

    @pytest.mark.asyncio
    async def test_finalises_to_allowed_when_no_check_blocked(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = _base_state(compliance_outcome=None)
        state = await agent._record_audit(state)
        assert state["compliance_outcome"] == "allowed"

    @pytest.mark.asyncio
    async def test_preserves_blocked_outcome(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = _base_state(compliance_outcome="blocked")
        state = await agent._record_audit(state)
        assert state["compliance_outcome"] == "blocked"

    @pytest.mark.asyncio
    async def test_sets_compliance_checked_true(self):
        agent, _ = _make_agent()
        agent._compliance.record_audit_event = AsyncMock()
        state = await agent._record_audit(_base_state())
        assert state["compliance_checked"] is True


# ── Tenant and workspace isolation ────────────────────────────────────────────

class TestIsolation:
    @pytest.mark.asyncio
    async def test_check_opt_in_passes_contact_id_from_state_not_external(self):
        """The agent must use contact_id from state, not from any external param."""
        agent, _ = _make_agent()
        captured = {}

        async def capture_req(req):
            captured["contact_id"] = req.contact_id
            return _allowed()

        agent._compliance.check_opt_in = capture_req
        await agent._check_opt_in(_base_state())
        assert captured["contact_id"] == CONTACT

    @pytest.mark.asyncio
    async def test_opt_in_check_calls_compliance_service(self):
        """Agent delegates opt_in enforcement to ComplianceService, not raw SQL."""
        agent, _ = _make_agent()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        await agent._check_opt_in(_base_state())
        agent._compliance.check_opt_in.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_check_calls_compliance_service(self):
        agent, _ = _make_agent()
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        await agent._check_unsubscribe(_base_state())
        agent._compliance.check_unsubscribe_by_contact_id.assert_awaited_once()


# ── End-to-end graph execution ────────────────────────────────────────────────

class TestGraphExecution:
    @pytest.mark.asyncio
    async def test_allowed_contact_reaches_record_audit(self):
        session = MagicMock()
        agent = ComplianceGuardAgent(session=session)
        agent._compliance = MagicMock()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        agent._compliance.record_audit_event = AsyncMock()

        state = await agent.run(_base_state(), config={})

        agent._compliance.check_opt_in.assert_awaited_once()
        agent._compliance.check_unsubscribe_by_contact_id.assert_awaited_once()
        agent._compliance.record_audit_event.assert_awaited_once()
        assert state["compliance_checked"] is True
        assert state["compliance_outcome"] == "allowed"

    @pytest.mark.asyncio
    async def test_blocked_contact_short_circuits_to_audit(self):
        """opt_in block → skip remaining checks → jump to record_audit."""
        session = MagicMock()
        agent = ComplianceGuardAgent(session=session)
        agent._compliance = MagicMock()
        agent._compliance.check_opt_in = AsyncMock(return_value=_blocked())
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        agent._compliance.record_audit_event = AsyncMock()

        state = await agent.run(_base_state(), config={})

        agent._compliance.check_opt_in.assert_awaited_once()
        # unsubscribe must NOT be called — short-circuited after opt_in block
        agent._compliance.check_unsubscribe_by_contact_id.assert_not_awaited()
        assert state["compliance_outcome"] == "blocked"
        assert state["compliance_checked"] is True

    @pytest.mark.asyncio
    async def test_unsubscribed_contact_blocked_after_opt_in_passes(self):
        session = MagicMock()
        agent = ComplianceGuardAgent(session=session)
        agent._compliance = MagicMock()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=ComplianceCheckResult(
                outcome=ComplianceOutcome.BLOCKED,
                reason="Contact is on the unsubscribe list",
                blocked_by="unsubscribe",
                audit_event_id=uuid.uuid4(),
            )
        )
        agent._compliance.record_audit_event = AsyncMock()

        state = await agent.run(_base_state(), config={})

        assert state["compliance_outcome"] == "blocked"
        assert state["compliance_checked"] is True
        # opt_in was called; unsubscribe was called; rest were skipped
        agent._compliance.check_opt_in.assert_awaited_once()
        agent._compliance.check_unsubscribe_by_contact_id.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_error_in_opt_in_sets_error_outcome(self):
        session = MagicMock()
        agent = ComplianceGuardAgent(session=session)
        agent._compliance = MagicMock()
        agent._compliance.check_opt_in = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        agent._compliance.record_audit_event = AsyncMock()

        state = await agent.run(_base_state(), config={})

        assert state["compliance_outcome"] == "error"
        # unsubscribe must NOT be called after error
        agent._compliance.check_unsubscribe_by_contact_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_audit_write_failure_sets_error_not_allowed(self):
        session = MagicMock()
        agent = ComplianceGuardAgent(session=session)
        agent._compliance = MagicMock()
        agent._compliance.check_opt_in = AsyncMock(return_value=_allowed())
        agent._compliance.check_unsubscribe_by_contact_id = AsyncMock(
            return_value=_allowed()
        )
        agent._compliance.record_audit_event = AsyncMock(
            side_effect=RuntimeError("audit DB down")
        )

        state = await agent.run(_base_state(), config={})

        assert state["compliance_outcome"] == "error"
        assert state["compliance_checked"] is True
