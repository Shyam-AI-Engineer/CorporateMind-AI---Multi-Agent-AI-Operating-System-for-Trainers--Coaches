"""Unit tests for the Sprint 8B follow-up cadence worker (mocks, no DB/LLM).

Covers:
  • quiet-hours helpers (_within_quiet_hours, _next_window_start_utc, _zone fallback)
  • the kill-switch flag gating on advance_followup_cadence
  • the _process_one eligibility matrix (claim, attempts ceiling, quiet-hours defer,
    OoO auto-send, question always-park, training-wheels park, auto_send-off park,
    compliance-block cancel, opt-in cancel)

Repo + DB correctness lives in tests/repo/test_followup_cadence_repo.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded

from corpmind.core.flags import clear_overrides, override
from corpmind.core.tenancy import TenantContext
from corpmind.workers.tasks import outreach as wk
from corpmind.workers.tasks.outreach import (
    FLAG_CADENCE,
    _next_window_start_utc,
    _process_one,
    _within_quiet_hours,
    _zone,
    advance_followup_cadence,
    process_tenant_followups,
)

_TENANT = uuid.uuid4()
_WS = uuid.uuid4()
_BASE_CTX = TenantContext(
    org_id=_TENANT, workspace_id=_WS, user_id=_TENANT, role="system", request_id="req-cad"
)


# ── Quiet-hours helpers ──────────────────────────────────────────────────────

class TestQuietHours:
    def test_inside_window_ist_morning(self):
        # 03:00 UTC = 08:30 IST → inside [08:00, 21:00)
        assert _within_quiet_hours("Asia/Kolkata", datetime(2026, 6, 11, 3, 0, tzinfo=UTC)) is True

    def test_before_window_ist(self):
        # 01:00 UTC = 06:30 IST → before 08:00
        assert _within_quiet_hours("Asia/Kolkata", datetime(2026, 6, 11, 1, 0, tzinfo=UTC)) is False

    def test_after_window_ist(self):
        # 16:30 UTC = 22:00 IST → after 21:00
        assert _within_quiet_hours("Asia/Kolkata", datetime(2026, 6, 11, 16, 30, tzinfo=UTC)) is False

    def test_next_window_before_window_is_today_0800_local(self):
        # 01:00 UTC (06:30 IST) → today 08:00 IST = 02:30 UTC same day
        nxt = _next_window_start_utc("Asia/Kolkata", datetime(2026, 6, 11, 1, 0, tzinfo=UTC))
        assert (nxt.hour, nxt.minute) == (2, 30)
        assert nxt.day == 11

    def test_next_window_after_window_is_tomorrow_0800_local(self):
        # 16:30 UTC (22:00 IST) → tomorrow 08:00 IST = next-day 02:30 UTC
        nxt = _next_window_start_utc("Asia/Kolkata", datetime(2026, 6, 11, 16, 30, tzinfo=UTC))
        assert (nxt.hour, nxt.minute) == (2, 30)
        assert nxt.day == 12

    def test_zone_falls_back_to_ist_for_bad_tz(self):
        # A malformed tz must not raise; fixed IST offset (UTC+5:30) is used.
        z = _zone("Not/ARealZone")
        offset = datetime(2026, 6, 11, tzinfo=UTC).astimezone(z).utcoffset()
        assert offset.total_seconds() == 5.5 * 3600


# ── advance_followup_cadence kill switch ─────────────────────────────────────

class TestCadenceFlagGate:
    def teardown_method(self):
        clear_overrides()

    def test_disabled_flag_is_noop(self):
        override(FLAG_CADENCE, False)
        with patch("asyncio.run") as mock_run:
            result = advance_followup_cadence.run()
        assert result["status"] == "disabled"
        mock_run.assert_not_called()

    def test_enabled_flag_runs_fan_out(self):
        override(FLAG_CADENCE, True)
        summary = {"status": "ok", "orgs_scanned": 2, "subtasks_queued": 2}
        with patch("asyncio.run", return_value=summary) as mock_run:
            result = advance_followup_cadence.run()
        mock_run.assert_called_once()
        assert result["subtasks_queued"] == 2

    def test_soft_timeout_retries(self):
        override(FLAG_CADENCE, True)
        with patch.object(advance_followup_cadence, "retry", side_effect=Retry()) as mock_retry:
            with patch("asyncio.run", side_effect=SoftTimeLimitExceeded()):
                with pytest.raises(Retry):
                    advance_followup_cadence.run()
        mock_retry.assert_called_once_with(countdown=60)


class TestProcessTenantWrapper:
    def test_delegates_to_async_body(self):
        summary = {"status": "ok", "tenant_id": str(_TENANT)}
        with patch("asyncio.run", return_value=summary) as mock_run:
            result = process_tenant_followups.run(
                tenant_id=str(_TENANT), org_created_at=datetime.now(UTC).isoformat()
            )
        mock_run.assert_called_once()
        assert result["status"] == "ok"

    def test_generic_error_retries(self):
        err = RuntimeError("db down")
        with patch.object(process_tenant_followups, "retry", side_effect=Retry()) as mock_retry:
            with patch("asyncio.run", side_effect=err):
                with pytest.raises(Retry):
                    process_tenant_followups.run(
                        tenant_id=str(_TENANT), org_created_at=datetime.now(UTC).isoformat()
                    )
        mock_retry.assert_called_once_with(exc=err)


# ── _process_one eligibility matrix ──────────────────────────────────────────

def _task(task_type: str = "out_of_office_followup", attempts: int = 0):
    return SimpleNamespace(
        id=uuid.uuid4(),
        attempts=attempts,
        workspace_id=_WS,
        contact_id=uuid.uuid4(),
        type=task_type,
        source_outbound_message_id=uuid.uuid4(),
        source_inbox_message_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )


def _draft(needs_review: bool = False):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    return SimpleNamespace(message=msg, task_type="x", needs_human_review=needs_review, answered=None)


class _Ctx:
    """Bundles the patched helpers + mocked repo/service for _process_one."""

    def __init__(
        self,
        *,
        claim=True,
        within_hours=True,
        send_status="queued",
        generate_exc=None,
        needs_review=False,
    ):
        self.repo = AsyncMock()
        self.repo.claim = AsyncMock(return_value=claim)
        self.repo.mark_done = AsyncMock()
        self.repo.mark_awaiting_approval = AsyncMock()
        self.repo.mark_cancelled = AsyncMock()
        self.repo.defer = AsyncMock()
        self.session = AsyncMock()
        self.session.commit = AsyncMock()

        self.svc = MagicMock()
        if generate_exc is not None:
            self.svc.generate_followup = AsyncMock(side_effect=generate_exc)
        else:
            self.svc.generate_followup = AsyncMock(return_value=_draft(needs_review))
        self.svc.send_message = AsyncMock(
            return_value=SimpleNamespace(
                status=send_status,
                compliance_reason=("frequency_cap" if send_status == "blocked" else None),
            )
        )
        self._within = within_hours

    def patches(self):
        inbox = MagicMock()
        inbox.get_decrypted_snippet = AsyncMock(return_value="reply text")
        return (
            patch("corpmind.modules.outreach.service.OutreachService", return_value=self.svc),
            patch("corpmind.modules.inbox.service.InboxService", return_value=inbox),
            patch.object(wk, "_resolve_workspace_timezone", new=AsyncMock(return_value="Asia/Kolkata")),
            patch.object(wk, "_within_quiet_hours", return_value=self._within),
            patch.object(wk, "_next_window_start_utc", return_value=datetime(2026, 6, 12, 2, 30, tzinfo=UTC)),
            patch.object(wk, "_hydrate_original_outbound", new=AsyncMock(return_value={
                "subject": "Building your bench", "body": "orig", "smtp_message_id": "<A@d>"})),
            patch.object(wk, "_lead_stage", new=AsyncMock(return_value="engaged")),
            patch.object(wk, "_write_followup_activity", new=AsyncMock()),
        )


async def _run(ctx: _Ctx, task, *, training_wheels=False, auto_send=True):
    counts = {"due": 1, "sent": 0, "parked": 0, "cancelled": 0, "deferred": 0, "skipped": 0}
    p = ctx.patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
        await _process_one(
            session=ctx.session,
            repo=ctx.repo,
            task=task,
            tenant_uuid=_TENANT,
            base_ctx=_BASE_CTX,
            now_utc=datetime(2026, 6, 11, 3, 0, tzinfo=UTC),
            is_training_wheels=training_wheels,
            auto_send_enabled=auto_send,
            counts=counts,
        )
    return counts


@pytest.mark.asyncio
class TestProcessOne:
    async def test_lost_claim_skips_without_generating(self):
        ctx = _Ctx(claim=False)
        counts = await _run(ctx, _task())
        assert counts["skipped"] == 1
        ctx.svc.generate_followup.assert_not_called()

    async def test_attempts_ceiling_cancels(self):
        ctx = _Ctx(claim=True)
        counts = await _run(ctx, _task(attempts=5))  # +1 = 6 > 5
        ctx.repo.mark_cancelled.assert_awaited_once()
        assert counts["cancelled"] == 1
        ctx.svc.generate_followup.assert_not_called()

    async def test_quiet_hours_defers_without_generating(self):
        ctx = _Ctx(claim=True, within_hours=False)
        counts = await _run(ctx, _task())
        ctx.repo.defer.assert_awaited_once()
        assert counts["deferred"] == 1
        ctx.svc.generate_followup.assert_not_called()

    async def test_ooo_auto_sends_and_marks_done(self):
        ctx = _Ctx(claim=True, send_status="queued")
        counts = await _run(ctx, _task("out_of_office_followup"), auto_send=True)
        ctx.svc.send_message.assert_awaited_once()
        ctx.repo.mark_done.assert_awaited_once()
        assert counts["sent"] == 1
        # threading anchor passed through
        assert ctx.svc.send_message.await_args.kwargs.get("in_reply_to") == "<A@d>"

    async def test_question_is_always_parked_never_sent(self):
        ctx = _Ctx(claim=True)
        counts = await _run(ctx, _task("question_followup"), auto_send=True)
        ctx.svc.send_message.assert_not_called()
        ctx.repo.mark_awaiting_approval.assert_awaited_once()
        assert counts["parked"] == 1

    async def test_training_wheels_parks_ooo(self):
        ctx = _Ctx(claim=True)
        counts = await _run(ctx, _task("out_of_office_followup"), training_wheels=True, auto_send=True)
        ctx.svc.send_message.assert_not_called()
        ctx.repo.mark_awaiting_approval.assert_awaited_once()
        assert counts["parked"] == 1

    async def test_auto_send_disabled_parks_ooo(self):
        ctx = _Ctx(claim=True)
        counts = await _run(ctx, _task("out_of_office_followup"), auto_send=False)
        ctx.svc.send_message.assert_not_called()
        ctx.repo.mark_awaiting_approval.assert_awaited_once()
        assert counts["parked"] == 1

    async def test_compliance_block_cancels(self):
        ctx = _Ctx(claim=True, send_status="blocked")
        counts = await _run(ctx, _task("out_of_office_followup"), auto_send=True)
        ctx.svc.send_message.assert_awaited_once()
        ctx.repo.mark_cancelled.assert_awaited_once()
        assert counts["cancelled"] == 1

    async def test_opt_in_error_cancels(self):
        from corpmind.core.exceptions import OptInRequiredError

        ctx = _Ctx(claim=True, generate_exc=OptInRequiredError("no opt in"))
        counts = await _run(ctx, _task("out_of_office_followup"), auto_send=True)
        ctx.repo.mark_cancelled.assert_awaited_once()
        assert counts["cancelled"] == 1
        ctx.svc.send_message.assert_not_called()
