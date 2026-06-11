"""Unit tests for FollowUpApprovalService (Sprint 8C, mocked deps).

The service composes FollowUpTaskRepo + OutreachService + InboxService +
ComplianceService + ActivityRepo; here each is replaced with a mock so the test
exercises the approval orchestration (status guards, send delegation, audit +
activity writes, block handling) without a DB or LLM.

DB-level transitions are covered by tests/repo/test_followup_cadence_repo.py and
the HTTP layer by tests/api/test_followup_approval_api.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.crm.approval import FollowUpApprovalService

_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_CTX = TenantContext(
    org_id=_ORG, workspace_id=_WS, user_id=uuid.uuid4(), role="trainer", request_id="req-8c"
)


def _task(
    *,
    status: str = "awaiting_approval",
    result_id: uuid.UUID | None = None,
    source_outbound: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=_WS,
        lead_id=lead_id,
        contact_id=uuid.uuid4(),
        type="question_followup",
        status=status,
        scheduled_for=None,
        source_inbox_message_id=uuid.uuid4(),
        source_outbound_message_id=source_outbound,
        result_outbound_message_id=result_id,
        attempts=1,
        notes="Question from reply.",
        created_at=now,
        updated_at=now,
    )


def _svc():
    svc = FollowUpApprovalService(session=AsyncMock())
    svc._session = AsyncMock()
    svc._session.commit = AsyncMock()
    svc._repo = AsyncMock()
    svc._outreach = AsyncMock()
    svc._inbox = AsyncMock()
    svc._compliance = AsyncMock()
    svc._activity = AsyncMock()
    return svc


_token = None


def setup_function():
    global _token
    _token = set_tenant_context(_CTX)


def teardown_function():
    if _token is not None:
        clear_tenant_context(_token)


# ── approve ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_queued_marks_done_and_audits():
    draft_id = uuid.uuid4()
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=draft_id)
    svc._outreach.send_message.return_value = MagicMock(status="queued", compliance_reason=None)

    res = await svc.approve(uuid.uuid4())

    assert res.status == "done"
    svc._outreach.send_message.assert_awaited_once()
    # threading anchor is None (no source_outbound) → passed as in_reply_to
    assert svc._outreach.send_message.await_args.kwargs.get("in_reply_to") is None
    svc._repo.mark_done.assert_awaited_once()
    audit_kwargs = svc._compliance.record_audit_event.await_args.kwargs
    assert audit_kwargs["event_type"] == "followup.approved"
    svc._activity.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_blocked_cancels_and_audits():
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=uuid.uuid4())
    svc._outreach.send_message.return_value = MagicMock(
        status="blocked", compliance_reason="frequency_cap"
    )

    res = await svc.approve(uuid.uuid4())

    assert res.status == "blocked"
    assert res.compliance_reason == "frequency_cap"
    svc._repo.mark_cancelled.assert_awaited_once()
    svc._repo.mark_done.assert_not_awaited()
    assert (
        svc._compliance.record_audit_event.await_args.kwargs["event_type"]
        == "followup.blocked_on_approve"
    )


@pytest.mark.asyncio
async def test_approve_resolves_threading_anchor_when_original_present():
    draft_id = uuid.uuid4()
    original_id = uuid.uuid4()
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=draft_id, source_outbound=original_id)
    svc._outreach.get_message.return_value = MagicMock(smtp_message_id="<A@d>")
    svc._outreach.send_message.return_value = MagicMock(status="queued", compliance_reason=None)

    await svc.approve(uuid.uuid4())

    svc._outreach.get_message.assert_awaited_once_with(original_id)
    assert svc._outreach.send_message.await_args.kwargs["in_reply_to"] == "<A@d>"


@pytest.mark.asyncio
async def test_approve_wrong_status_raises_conflict():
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(status="done", result_id=uuid.uuid4())
    with pytest.raises(ConflictError):
        await svc.approve(uuid.uuid4())
    svc._outreach.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_not_found_raises():
    svc = _svc()
    svc._repo.find_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await svc.approve(uuid.uuid4())


@pytest.mark.asyncio
async def test_approve_without_draft_raises_conflict():
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=None)
    with pytest.raises(ConflictError):
        await svc.approve(uuid.uuid4())
    svc._outreach.send_message.assert_not_awaited()


# ── reject ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_cancels_and_audits():
    svc = _svc()
    svc._repo.find_by_id.side_effect = [
        _task(result_id=uuid.uuid4()),                 # _require_task
        _task(status="cancelled", result_id=uuid.uuid4()),  # refresh after cancel
    ]
    res = await svc.reject(uuid.uuid4(), reason="not relevant")
    assert res.status == "cancelled"
    svc._repo.mark_cancelled.assert_awaited_once()
    assert (
        svc._compliance.record_audit_event.await_args.kwargs["event_type"]
        == "followup.rejected"
    )


@pytest.mark.asyncio
async def test_reject_wrong_status_raises_conflict():
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(status="cancelled", result_id=uuid.uuid4())
    with pytest.raises(ConflictError):
        await svc.reject(uuid.uuid4())


# ── edit ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_updates_draft_and_audits():
    draft_id = uuid.uuid4()
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=draft_id)
    svc._outreach.update_draft_content.return_value = MagicMock(
        id=draft_id, subject="Re: x", body="edited body", status="draft"
    )

    out = await svc.edit_draft(uuid.uuid4(), subject="Re: x", body="edited body")

    assert out.body == "edited body"
    svc._outreach.update_draft_content.assert_awaited_once()
    assert (
        svc._compliance.record_audit_event.await_args.kwargs["event_type"]
        == "followup.edited"
    )


@pytest.mark.asyncio
async def test_edit_without_draft_raises_conflict():
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=None)
    with pytest.raises(ConflictError):
        await svc.edit_draft(uuid.uuid4(), subject=None, body="x")


# ── review ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_review_assembles_payload():
    draft_id = uuid.uuid4()
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=draft_id)
    svc._outreach.get_message.return_value = MagicMock(
        id=draft_id, subject="Re: q", body="draft answer", status="draft"
    )
    svc._inbox.get_message.return_value = MagicMock(
        from_address="hr@acme.example",
        subject="Question",
        body_snippet="What about pricing?",
        received_at=datetime.now(UTC),
    )

    review = await svc.get_review(uuid.uuid4())

    assert review.draft is not None and review.draft.body == "draft answer"
    assert review.reply is not None and review.reply.snippet == "What about pricing?"
    assert review.lead_stage is None  # no lead_id → no lookup


@pytest.mark.asyncio
async def test_get_review_tolerates_missing_reply():
    draft_id = uuid.uuid4()
    svc = _svc()
    svc._repo.find_by_id.return_value = _task(result_id=draft_id)
    svc._outreach.get_message.return_value = MagicMock(
        id=draft_id, subject=None, body="draft", status="draft"
    )
    svc._inbox.get_message.side_effect = NotFoundError("gone")

    review = await svc.get_review(uuid.uuid4())
    assert review.reply is None
    assert review.draft is not None
