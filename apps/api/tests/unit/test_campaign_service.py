"""Unit tests for CampaignService.

Mocks: DB session, CampaignRepo, CampaignRecipientRepo, Celery task.
Tests cover state-machine transitions, HITL gate, and guard conditions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import TenantContext, set_tenant_context, clear_tenant_context
from corpmind.modules.campaigns.models import Campaign, CampaignRecipient
from corpmind.modules.campaigns.schemas import (
    AddRecipientsRequest,
    CampaignCreate,
)
from corpmind.modules.campaigns.service import CampaignService


# ── Fixtures ──────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_CAMPAIGN_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-test-001",
)


def _make_campaign(status: str = "draft", recipient_count: int = 0) -> Campaign:
    c = Campaign(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        name="Q1 Leadership Outreach",
        channel="email",
        settings={},
        created_by=_USER_ID,
    )
    c.id = _CAMPAIGN_ID
    c.status = status
    c.recipient_count = recipient_count
    c.scheduled_at = None
    c.started_at = None
    c.completed_at = None
    c.created_at = datetime.now(UTC)
    return c


def _make_recipient(contact_id: uuid.UUID | None = None) -> CampaignRecipient:
    r = CampaignRecipient(
        tenant_id=_ORG_ID,
        campaign_id=_CAMPAIGN_ID,
        contact_id=contact_id or uuid.uuid4(),
    )
    r.id = uuid.uuid4()
    r.status = "pending"
    r.message_id = None
    r.sent_at = None
    r.error_code = None
    r.error_detail = None
    return r


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


# ── Tests: create ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_campaign_happy_path():
    """Draft campaign is created with status='draft'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    # _repo.create flushes to get DB-generated id/defaults.
    # In tests, simulate that by mutating the passed Campaign in-place.
    async def _create_side_effect(campaign: Campaign) -> Campaign:
        campaign.id = _CAMPAIGN_ID
        campaign.status = "draft"
        campaign.recipient_count = 0
        campaign.created_at = datetime.now(UTC)
        return campaign

    svc._repo.create = _create_side_effect
    svc._session.commit = AsyncMock()

    req = CampaignCreate(name="Q1 Leadership", channel="email")
    result = await svc.create(req)

    clear_tenant_context(token)
    assert result.status == "draft"
    assert result.channel == "email"


# ── Tests: add_recipients ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_recipients_happy_path():
    """Recipients are added to a draft campaign."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)
    contact_ids = [uuid.uuid4(), uuid.uuid4()]

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("draft"))
    svc._recipient_repo.add_bulk = AsyncMock(return_value=2)
    svc._recipient_repo.count_recipients = AsyncMock(return_value=2)
    svc._session.commit = AsyncMock()

    with patch.object(svc, "_validate_contacts", new_callable=AsyncMock):
        req = AddRecipientsRequest(contact_ids=contact_ids)
        result = await svc.add_recipients(_CAMPAIGN_ID, req)

    clear_tenant_context(token)
    assert result.added_count == 2
    assert result.total_recipients == 2


@pytest.mark.asyncio
async def test_add_recipients_rejects_non_draft():
    """ConflictError when campaign is not in draft status."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("locked"))

    req = AddRecipientsRequest(contact_ids=[uuid.uuid4()])
    with pytest.raises(ConflictError, match="draft"):
        await svc.add_recipients(_CAMPAIGN_ID, req)

    clear_tenant_context(token)


# ── Tests: lock ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_happy_path():
    """Campaign transitions from draft to locked with recipient_count set."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("draft"))
    svc._recipient_repo.count_recipients = AsyncMock(return_value=5)
    svc._repo.update_fields = AsyncMock()
    svc._session.commit = AsyncMock()

    result = await svc.lock(_CAMPAIGN_ID)

    clear_tenant_context(token)
    assert result.status == "locked"
    assert result.recipient_count == 5
    svc._repo.update_fields.assert_called_once_with(
        _CAMPAIGN_ID, status="locked", recipient_count=5
    )


@pytest.mark.asyncio
async def test_lock_empty_recipients_raises():
    """ValidationError when locking a campaign with no recipients."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("draft"))
    svc._recipient_repo.count_recipients = AsyncMock(return_value=0)

    with pytest.raises(ValidationError, match="no recipients"):
        await svc.lock(_CAMPAIGN_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_lock_rejects_non_draft():
    """ConflictError when trying to lock a non-draft campaign."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("running"))

    with pytest.raises(ConflictError):
        await svc.lock(_CAMPAIGN_ID)

    clear_tenant_context(token)


# ── Tests: launch ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_launch_small_campaign_enqueues_task():
    """Campaign with ≤ 200 recipients transitions to 'running' and enqueues Celery task."""
    import sys

    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("locked", recipient_count=10))
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    # The service does a deferred `from corpmind.workers.tasks.campaigns import launch_campaign`.
    # Inject a mock module into sys.modules so the deferred import resolves without
    # triggering a real celery import (celery is not available in the unit-test runner).
    mock_task = MagicMock()
    mock_module = MagicMock()
    mock_module.launch_campaign = mock_task

    with patch.dict(sys.modules, {"corpmind.workers.tasks.campaigns": mock_module}):
        result = await svc.launch(_CAMPAIGN_ID)

    clear_tenant_context(token)
    assert result.status == "running"
    assert result.hitl_required is False
    mock_task.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_launch_large_campaign_triggers_hitl():
    """Campaign with > 200 recipients transitions to 'pending_hitl'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(
        return_value=_make_campaign("locked", recipient_count=201)
    )
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    result = await svc.launch(_CAMPAIGN_ID)

    clear_tenant_context(token)
    assert result.status == "pending_hitl"
    assert result.hitl_required is True
    svc._repo.update_status.assert_called_once_with(_CAMPAIGN_ID, "pending_hitl")


@pytest.mark.asyncio
async def test_launch_from_draft_raises_conflict():
    """ConflictError when trying to launch a campaign not yet locked."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("draft"))

    with pytest.raises(ConflictError, match="Lock"):
        await svc.launch(_CAMPAIGN_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_launch_not_found_raises():
    """NotFoundError when campaign does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.launch(_CAMPAIGN_ID)

    clear_tenant_context(token)


# ── Tests: pause / resume / cancel ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pause_running_campaign():
    """Running campaign can be paused."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("running"))
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    await svc.pause(_CAMPAIGN_ID)

    clear_tenant_context(token)
    svc._repo.update_status.assert_called_once_with(_CAMPAIGN_ID, "paused")


@pytest.mark.asyncio
async def test_pause_draft_campaign_raises():
    """ConflictError when pausing a campaign that isn't running."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("draft"))

    with pytest.raises(ConflictError):
        await svc.pause(_CAMPAIGN_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_cancel_completed_campaign_raises():
    """ConflictError when cancelling an already-terminal campaign."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("completed"))

    with pytest.raises(ConflictError, match="terminal"):
        await svc.cancel(_CAMPAIGN_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_cancel_running_campaign():
    """Any non-terminal campaign can be cancelled."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CampaignService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_campaign("running"))
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    await svc.cancel(_CAMPAIGN_ID)

    clear_tenant_context(token)
    svc._repo.update_status.assert_called_once_with(_CAMPAIGN_ID, "cancelled")
