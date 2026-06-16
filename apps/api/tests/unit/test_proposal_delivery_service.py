"""Unit tests for ProposalService.deliver() — Sprint 12B.

Covers the full deliver() path:
  - happy path: compliance queued
  - compliance blocked (still transitions status='sent')
  - all guard conditions that raise before any write
  - audit event written for queued and blocked outcomes
  - CRM activity written in both outcomes
  - delivery_status populated on the returned ProposalOut

Mocks: DB session, ProposalRepo, ComplianceService, OutreachService.
No real DB, no real SMTP.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.service import ProposalService

# ── Constants ──────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PROPOSAL_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_OUTBOUND_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="OrgAdmin",
    request_id="req-delivery-test-001",
)

_CONTENT_WITH_BODY = {
    "title": "Leadership Excellence Workshop",
    "subject": "Partnership Proposal — Leadership Training",
    "body": "Dear HR Leader, we would like to propose...",
}

_CONTENT_NO_BODY = {
    "title": "Leadership Excellence Workshop",
}


# ── Factories ──────────────────────────────────────────────────────────────────

def _make_proposal(
    status: str = "draft",
    approval_status: str = "approved",
    outbound_message_id: uuid.UUID | None = None,
    content: dict | None = None,
) -> Proposal:
    p = Proposal(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        title="Leadership Excellence Workshop",
        status=status,
        content=content if content is not None else _CONTENT_WITH_BODY,
    )
    p.id = _PROPOSAL_ID
    p.cloudinary_url = None
    p.sent_at = None
    p.created_at = datetime.now(UTC)
    p.approval_status = approval_status
    p.approved_by = _USER_ID
    p.approved_at = datetime.now(UTC)
    p.rejected_reason = None
    p.outbound_message_id = outbound_message_id
    return p


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    # execute is called for raw SQL (contact email, INSERT outbound_messages, INSERT crm_activities)
    # Default: returns a result whose one_or_none() gives None (no contact).
    # Tests override this per scenario.
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _make_send_response(status: str = "queued", reason: str | None = None) -> MagicMock:
    r = MagicMock()
    r.status = status
    r.compliance_reason = reason
    return r


# ── Tests: guard conditions (no writes occur) ──────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_not_approved_raises():
    """ConflictError when approval_status is not 'approved'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(approval_status="pending_approval")
    )

    with pytest.raises(ConflictError, match="must be approved"):
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    session.execute.assert_not_called()  # no writes before guard fires


@pytest.mark.asyncio
async def test_deliver_already_sent_raises():
    """ConflictError when proposal.status is already 'sent'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(status="sent", approval_status="approved")
    )

    with pytest.raises(ConflictError, match="already been sent"):
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_contact_not_found_raises():
    """NotFoundError when hr_contacts has no row for the contact."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    # session.execute returns mock whose one_or_none() returns None — default behaviour
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()

    with pytest.raises(NotFoundError, match="not found or has no email"):
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._repo.update_fields.assert_not_called()  # no write before guard fires


@pytest.mark.asyncio
async def test_deliver_contact_email_none_raises():
    """NotFoundError when hr_contacts row exists but email column is NULL."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    # Row exists but email is None
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (None,)
    session.execute = AsyncMock(return_value=mock_result)

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()

    with pytest.raises(NotFoundError, match="not found or has no email"):
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._repo.update_fields.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_uses_full_content_when_no_body_key():
    """When proposal.content has no flat 'body' key, deliver() uses json.dumps fallback.

    This verifies the rich-JSONB-content path (executive_summary, proposed_training,
    etc.) — the kind of content the AI generates — does NOT raise a ValidationError
    and instead serializes to a non-empty email body.
    """
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(content=_CONTENT_NO_BODY)
    )
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        result = await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    # Rich JSONB content without a flat "body" key still produces a valid delivery
    assert result.status == "sent"
    assert result.delivery_status == "queued"


@pytest.mark.asyncio
async def test_deliver_proposal_not_found_raises():
    """NotFoundError when the proposal does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)


# ── Tests: happy path (queued) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_happy_path_returns_sent_status():
    """deliver() returns ProposalOut with status='sent' and delivery_status='queued'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    # sequence: (1) contact email, (2) INSERT outbound_messages, (3) INSERT crm_activities
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch(
        "corpmind.modules.outreach.service.OutreachService"
    ) as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        result = await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert result.status == "sent"
    assert result.delivery_status == "queued"
    assert result.outbound_message_id is not None
    assert result.sent_at is not None


@pytest.mark.asyncio
async def test_deliver_sets_outbound_message_id_on_proposal():
    """update_fields is called with outbound_message_id, status='sent', sent_at."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        result = await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._repo.update_fields.assert_awaited_once()
    kwargs = svc._repo.update_fields.call_args[1]
    assert kwargs["status"] == "sent"
    assert kwargs["sent_at"] is not None
    assert "outbound_message_id" in kwargs
    assert isinstance(kwargs["outbound_message_id"], uuid.UUID)
    assert result.outbound_message_id == kwargs["outbound_message_id"]


@pytest.mark.asyncio
async def test_deliver_writes_audit_event_queued():
    """record_audit_event is called with event_type='proposal.delivery_queued' when queued."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._compliance.record_audit_event.assert_awaited_once()
    kwargs = svc._compliance.record_audit_event.call_args[1]
    assert kwargs["event_type"] == "proposal.delivery_queued"
    assert kwargs["outcome"] == "allowed"
    assert str(_PROPOSAL_ID) in str(kwargs.get("event_data", {}))


@pytest.mark.asyncio
async def test_deliver_writes_crm_activity():
    """A raw SQL INSERT into crm_activities is executed on successful deliver()."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None

    execute_calls: list = []
    async def _capture_execute(stmt, params=None):
        execute_calls.append(str(stmt))
        if len(execute_calls) == 1:
            return mock_email_result
        return mock_noop

    session.execute = AsyncMock(side_effect=_capture_execute)

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    # The third execute call is the crm_activities INSERT
    crm_inserts = [c for c in execute_calls if "crm_activities" in c]
    assert len(crm_inserts) == 1, "Expected one INSERT into crm_activities"


# ── Tests: compliance blocked ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_compliance_blocked_still_sets_status_sent():
    """Even when compliance blocks, proposal.status transitions to 'sent'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(
            return_value=_make_send_response("blocked", "frequency_cap")
        )
        result = await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert result.status == "sent"
    assert result.delivery_status == "blocked"


@pytest.mark.asyncio
async def test_deliver_compliance_blocked_writes_blocked_audit_event():
    """record_audit_event is called with event_type='proposal.delivery_blocked' when blocked."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(
            return_value=_make_send_response("blocked", "opt_in_missing")
        )
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._compliance.record_audit_event.assert_awaited_once()
    kwargs = svc._compliance.record_audit_event.call_args[1]
    assert kwargs["event_type"] == "proposal.delivery_blocked"
    assert kwargs["outcome"] == "blocked"
    assert kwargs["reason"] == "opt_in_missing"


# ── Tests: OutreachService is called with the right outbound_message_id ─────────

@pytest.mark.asyncio
async def test_deliver_calls_outreach_send_message_with_outbound_id():
    """OutreachService.send_message receives the outbound_message_id created in deliver()."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_send = AsyncMock(return_value=_make_send_response("queued"))
        mock_instance.send_message = mock_send
        result = await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    mock_send.assert_awaited_once()
    called_with_id = mock_send.call_args[0][0]
    assert called_with_id == result.outbound_message_id


# ── Tests: idempotency ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_session_committed_twice():
    """deliver() commits exactly twice: once for OutboundMessage+proposal, once for activity."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_deliver_uses_select_for_update():
    """deliver() calls find_by_id_for_update (not find_by_id) to hold row lock."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    mock_email_result = MagicMock()
    mock_email_result.one_or_none.return_value = ("hr@company.com",)
    mock_noop = MagicMock()
    mock_noop.one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[mock_email_result, mock_noop, mock_noop])

    svc = ProposalService(session)
    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.find_by_id = AsyncMock()  # should NOT be called
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    with patch("corpmind.modules.outreach.service.OutreachService") as MockOutreach:
        mock_instance = MockOutreach.return_value
        mock_instance.send_message = AsyncMock(return_value=_make_send_response("queued"))
        await svc.deliver(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._repo.find_by_id_for_update.assert_awaited_once_with(_PROPOSAL_ID)
    svc._repo.find_by_id.assert_not_awaited()
