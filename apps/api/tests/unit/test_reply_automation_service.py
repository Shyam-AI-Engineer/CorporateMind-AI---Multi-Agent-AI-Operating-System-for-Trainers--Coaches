"""Unit tests for ReplyAutomationService — mocked repos, no DB.

Covers:
  - Per-intent dispatch (interested, not_interested, question, out_of_office,
    bounce, auto_reply, unknown).
  - Validation gates (no_outbound_match, contact_not_found, lead_not_found,
    tenant_mismatch).
  - Idempotency: a second call for the same inbox_message returns
    "already_applied" with no further repo mutations.
  - Stage-aware no-op behaviour for interested (skip advance when lead
    already past discovered) and not_interested (skip mark_lost on terminal).

External dependencies — LeadRepo, ActivityRepo, FollowUpTaskRepo,
AutomationLogRepo, CRMService, the raw-SQL outbound lookup, and
get_tenant_context — are mocked via patch.  No DB session is required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.crm.automation import (
    AutomationResult,
    ReplyAutomationService,
    _OOO_FOLLOWUP_HOURS,
)


TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
CONTACT_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
OUTBOUND_ID = uuid.uuid4()
INBOX_MSG_ID = uuid.uuid4()


def _ctx(org_id: uuid.UUID = TENANT_ID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    ctx.workspace_id = WORKSPACE_ID
    return ctx


def _lead(stage: str = "discovered") -> MagicMock:
    lead = MagicMock()
    lead.id = LEAD_ID
    lead.tenant_id = TENANT_ID
    lead.contact_id = CONTACT_ID
    lead.workspace_id = WORKSPACE_ID
    lead.stage = stage
    return lead


def _make_service(
    *,
    reserve_returns: bool = True,
    outbound_returns: tuple[uuid.UUID, uuid.UUID] | None = (CONTACT_ID, WORKSPACE_ID),
    lead_returns: MagicMock | None = None,
) -> ReplyAutomationService:
    """Build a ReplyAutomationService with all collaborators mocked."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    svc = ReplyAutomationService(session)

    # Patch every repo + the CRMService entry points
    svc._log_repo = MagicMock()
    svc._log_repo.reserve = AsyncMock(return_value=reserve_returns)

    svc._activity_repo = MagicMock()
    svc._activity_repo.create = AsyncMock(side_effect=lambda a: a)

    svc._followup_repo = MagicMock()
    svc._followup_repo.create = AsyncMock(side_effect=lambda t: t)

    svc._lead_repo = MagicMock()
    svc._lead_repo.find_active_by_contact = AsyncMock(return_value=lead_returns)
    svc._lead_repo.find_active_by_contact_any_workspace = AsyncMock(
        return_value=lead_returns
    )

    svc._crm = MagicMock()
    svc._crm.advance_stage = AsyncMock()
    svc._crm.mark_lost = AsyncMock()

    # _resolve_outbound is private and hits raw SQL — mock it directly.
    svc._resolve_outbound = AsyncMock(return_value=outbound_returns)  # type: ignore[method-assign]

    return svc


# ── Per-intent: interested ────────────────────────────────────────────────────

class TestInterested:
    @pytest.mark.asyncio
    async def test_advances_lead_when_in_discovered(self):
        svc = _make_service(lead_returns=_lead("discovered"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.advance_stage.assert_awaited_once_with(LEAD_ID)
        svc._activity_repo.create.assert_awaited_once()
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_skips_advance_when_already_engaged(self):
        """Critical correctness: do not skip stages on a second `interested` reply."""
        svc = _make_service(lead_returns=_lead("engaged"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.advance_stage.assert_not_awaited()
        svc._activity_repo.create.assert_awaited_once()
        # Activity still logs the no-op so audit trail captures the signal.
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_skips_advance_when_meeting_scheduled(self):
        svc = _make_service(lead_returns=_lead("meeting_scheduled"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.advance_stage.assert_not_awaited()


# ── Per-intent: not_interested ────────────────────────────────────────────────

class TestNotInterested:
    @pytest.mark.asyncio
    async def test_marks_lost_for_active_lead(self):
        svc = _make_service(lead_returns=_lead("engaged"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="not_interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.mark_lost.assert_awaited_once_with(LEAD_ID)
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_skips_mark_lost_when_already_terminal(self):
        svc = _make_service(lead_returns=_lead("lost"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="not_interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.mark_lost.assert_not_awaited()
        svc._activity_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_mark_lost_when_already_booked(self):
        svc = _make_service(lead_returns=_lead("booked"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="not_interested",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.mark_lost.assert_not_awaited()


# ── Per-intent: question ──────────────────────────────────────────────────────

class TestQuestion:
    @pytest.mark.asyncio
    async def test_creates_followup_task_with_no_schedule(self):
        svc = _make_service(lead_returns=_lead("engaged"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="question",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._followup_repo.create.assert_awaited_once()
        task = svc._followup_repo.create.await_args.args[0]
        assert task.type == "question_followup"
        assert task.scheduled_for is None
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_creates_task_even_without_lead(self):
        """question doesn't require an active lead — just a contact."""
        svc = _make_service(lead_returns=None)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="question",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._followup_repo.create.assert_awaited_once()
        task = svc._followup_repo.create.await_args.args[0]
        assert task.lead_id is None
        assert result.outcome == "applied"


# ── Per-intent: out_of_office ─────────────────────────────────────────────────

class TestOutOfOffice:
    @pytest.mark.asyncio
    async def test_schedules_followup_in_future(self):
        from datetime import UTC, datetime

        svc = _make_service(lead_returns=_lead("engaged"))
        before = datetime.now(UTC)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="out_of_office",
                outbound_message_id=OUTBOUND_ID,
            )

        task = svc._followup_repo.create.await_args.args[0]
        assert task.type == "out_of_office_followup"
        assert task.scheduled_for is not None
        # Window is approx now + _OOO_FOLLOWUP_HOURS (72h default).
        delta_hours = (task.scheduled_for - before).total_seconds() / 3600
        assert _OOO_FOLLOWUP_HOURS - 1 <= delta_hours <= _OOO_FOLLOWUP_HOURS + 1


# ── Per-intent: bounce ────────────────────────────────────────────────────────

class TestBounce:
    @pytest.mark.asyncio
    async def test_updates_hr_contact_deliverable(self):
        svc = _make_service(lead_returns=_lead("engaged"))
        # session.execute is the raw-SQL escape hatch the service uses for
        # cross-module hr_contacts updates.  Assert it ran exactly once.
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="bounce",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._session.execute.assert_awaited()
        svc._activity_repo.create.assert_awaited_once()
        assert result.outcome == "applied"

    @pytest.mark.asyncio
    async def test_bounce_processed_even_without_active_lead(self):
        """Bounce bypasses the lead-required gate."""
        svc = _make_service(lead_returns=None)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="bounce",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "applied"
        svc._activity_repo.create.assert_awaited_once()


# ── Per-intent: auto_reply ────────────────────────────────────────────────────

class TestAutoReply:
    @pytest.mark.asyncio
    async def test_logs_activity_only(self):
        svc = _make_service(lead_returns=_lead("engaged"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="auto_reply",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.advance_stage.assert_not_awaited()
        svc._crm.mark_lost.assert_not_awaited()
        svc._followup_repo.create.assert_not_awaited()
        svc._activity_repo.create.assert_awaited_once()


# ── Per-intent: unknown ───────────────────────────────────────────────────────

class TestUnknown:
    @pytest.mark.asyncio
    async def test_logs_activity_only(self):
        svc = _make_service(lead_returns=_lead("engaged"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="unknown",
                outbound_message_id=OUTBOUND_ID,
            )

        svc._crm.advance_stage.assert_not_awaited()
        svc._followup_repo.create.assert_not_awaited()
        svc._activity_repo.create.assert_awaited_once()


# ── Validation gates ──────────────────────────────────────────────────────────

class TestValidationGates:
    @pytest.mark.asyncio
    async def test_missing_outbound_message_id_fails(self):
        svc = _make_service()
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=None,
            )

        assert result.outcome == "failed"
        assert result.reason == "no_outbound_match"
        svc._crm.advance_stage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_contact_fails(self):
        """_resolve_outbound returns None when the outbound row has no contact."""
        svc = _make_service(outbound_returns=None)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "failed"
        assert result.reason == "contact_not_found"

    @pytest.mark.asyncio
    async def test_missing_lead_fails_for_interested(self):
        svc = _make_service(lead_returns=None)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "failed"
        assert result.reason == "lead_not_found"

    @pytest.mark.asyncio
    async def test_missing_lead_fails_for_not_interested(self):
        svc = _make_service(lead_returns=None)
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="not_interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "failed"
        assert result.reason == "lead_not_found"

    @pytest.mark.asyncio
    async def test_tenant_mismatch_fails_before_any_repo_access(self):
        """When TenantContext.org_id != event.tenant_id, the service short-circuits."""
        svc = _make_service()
        other_tenant = uuid.uuid4()
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(org_id=other_tenant),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "failed"
        assert result.reason == "tenant_mismatch"
        # Reservation must NOT have been attempted under the wrong tenant.
        svc._log_repo.reserve.assert_not_awaited()


# ── Idempotency ───────────────────────────────────────────────────────────────

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_returns_already_applied_when_reservation_conflicts(self):
        """Duplicate sync events for the same inbox_message must NOT re-run any handler."""
        svc = _make_service(reserve_returns=False, lead_returns=_lead("discovered"))
        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            result = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert result.outcome == "already_applied"
        # None of the downstream handlers should have run.
        svc._crm.advance_stage.assert_not_awaited()
        svc._activity_repo.create.assert_not_awaited()
        svc._followup_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_classified_event_no_double_advance(self):
        """Two back-to-back handle_classified calls share the same reservation key.

        Simulates a duplicate ReplyClassified event by toggling reserve_returns
        between True (first call) and False (second call) — mirrors the real
        UNIQUE constraint behaviour.
        """
        svc = _make_service(lead_returns=_lead("discovered"))
        svc._log_repo.reserve.side_effect = [True, False]

        with patch(
            "corpmind.modules.crm.automation.get_tenant_context",
            return_value=_ctx(),
        ):
            first = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )
            second = await svc.handle_classified(
                inbox_message_id=INBOX_MSG_ID,
                tenant_id=TENANT_ID,
                intent="interested",
                outbound_message_id=OUTBOUND_ID,
            )

        assert first.outcome == "applied"
        assert second.outcome == "already_applied"
        # CRM mutation happened exactly once across both calls.
        assert svc._crm.advance_stage.await_count == 1


# ── AutomationResult schema ───────────────────────────────────────────────────

class TestAutomationResult:
    def test_default_fields(self):
        r = AutomationResult(outcome="applied")
        assert r.outcome == "applied"
        assert r.reason is None
        assert r.activity_id is None

    def test_failed_with_reason(self):
        r = AutomationResult(outcome="failed", reason="lead_not_found")
        assert r.outcome == "failed"
        assert r.reason == "lead_not_found"
