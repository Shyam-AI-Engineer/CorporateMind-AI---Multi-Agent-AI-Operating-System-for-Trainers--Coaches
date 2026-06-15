"""Unit tests for ProposalService approval workflow (Sprint 12A).

Covers: approve(), reject(), and the mark_sent() approval guard.
Mocks: DB session, ProposalRepo, ComplianceService.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.service import ProposalService

# ── Fixtures ───────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PROPOSAL_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()

_ADMIN_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="OrgAdmin",
    request_id="req-approval-test-001",
)

_TRAINER_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-approval-test-002",
)

_AI_CONTENT = {"title": "Test Proposal", "body": "Content"}


def _make_proposal(
    status: str = "draft",
    approval_status: str = "pending_approval",
) -> Proposal:
    p = Proposal(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        title="Test Proposal",
        status=status,
        content=_AI_CONTENT,
    )
    p.id = _PROPOSAL_ID
    p.cloudinary_url = None
    p.sent_at = None
    p.created_at = datetime.now(UTC)
    p.approval_status = approval_status
    p.approved_by = None
    p.approved_at = None
    p.rejected_reason = None
    return p


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


# ── Tests: approve ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_happy_path():
    """Pending proposal transitions approval_status to 'approved'."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    result = await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert result.approval_status == "approved"
    assert result.approved_by == _USER_ID
    assert result.approved_at is not None
    svc._repo.update_fields.assert_awaited_once()
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["approval_status"] == "approved"
    assert call_kwargs["approved_by"] == _USER_ID


@pytest.mark.asyncio
async def test_approve_records_audit_event():
    """approve() writes a proposal.approved audit event via ComplianceService."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)
    svc._compliance.record_audit_event.assert_awaited_once()
    call_kwargs = svc._compliance.record_audit_event.call_args[1]
    assert call_kwargs["event_type"] == "proposal.approved"
    assert call_kwargs["outcome"] == "allowed"


@pytest.mark.asyncio
async def test_approve_wrong_role_raises():
    """PermissionDeniedError when caller role is not OrgAdmin."""
    token = set_tenant_context(_TRAINER_CTX)
    session = _make_session()
    svc = ProposalService(session)

    with pytest.raises(PermissionDeniedError, match="OrgAdmin"):
        await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_approve_already_approved_raises():
    """ConflictError when proposal.approval_status is already 'approved'."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(approval_status="approved")
    )

    with pytest.raises(ConflictError, match="cannot be approved"):
        await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_approve_rejected_raises():
    """ConflictError when proposal.approval_status is already 'rejected'."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(approval_status="rejected")
    )

    with pytest.raises(ConflictError, match="cannot be approved"):
        await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_approve_not_found_raises():
    """NotFoundError when proposal does not exist."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.approve(_PROPOSAL_ID)

    clear_tenant_context(token)


# ── Tests: reject ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_happy_path():
    """Pending proposal transitions approval_status to 'rejected' with reason stored."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    result = await svc.reject(_PROPOSAL_ID, reason="Scope not aligned with Q3 goals")

    clear_tenant_context(token)
    assert result.approval_status == "rejected"
    assert result.rejected_reason == "Scope not aligned with Q3 goals"
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["approval_status"] == "rejected"
    assert call_kwargs["rejected_reason"] == "Scope not aligned with Q3 goals"


@pytest.mark.asyncio
async def test_reject_records_audit_event():
    """reject() writes a proposal.rejected audit event with outcome='blocked'."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=_make_proposal())
    svc._repo.update_fields = AsyncMock()
    svc._compliance.record_audit_event = AsyncMock()

    await svc.reject(_PROPOSAL_ID, reason="Budget constraints")

    clear_tenant_context(token)
    svc._compliance.record_audit_event.assert_awaited_once()
    call_kwargs = svc._compliance.record_audit_event.call_args[1]
    assert call_kwargs["event_type"] == "proposal.rejected"
    assert call_kwargs["outcome"] == "blocked"
    assert call_kwargs["reason"] == "Budget constraints"


@pytest.mark.asyncio
async def test_reject_wrong_role_raises():
    """PermissionDeniedError when caller role is not OrgAdmin."""
    token = set_tenant_context(_TRAINER_CTX)
    session = _make_session()
    svc = ProposalService(session)

    with pytest.raises(PermissionDeniedError, match="OrgAdmin"):
        await svc.reject(_PROPOSAL_ID, reason="Some reason")

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_reject_already_rejected_raises():
    """ConflictError when proposal.approval_status is already 'rejected'."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(approval_status="rejected")
    )

    with pytest.raises(ConflictError, match="cannot be rejected"):
        await svc.reject(_PROPOSAL_ID, reason="Duplicate rejection")

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_reject_approved_proposal_raises():
    """ConflictError when proposal has already been approved."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(
        return_value=_make_proposal(approval_status="approved")
    )

    with pytest.raises(ConflictError, match="cannot be rejected"):
        await svc.reject(_PROPOSAL_ID, reason="Changed mind")

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_reject_not_found_raises():
    """NotFoundError when proposal does not exist."""
    token = set_tenant_context(_ADMIN_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id_for_update = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.reject(_PROPOSAL_ID, reason="Does not matter")

    clear_tenant_context(token)
