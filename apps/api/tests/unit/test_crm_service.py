"""Unit tests for CRMService.

Mocks: DB session, LeadRepo.
Tests cover pipeline stage transitions, re-engagement guard, and metadata updates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.crm.models import Lead
from corpmind.modules.crm.schemas import LeadCreate
from corpmind.modules.crm.service import CRMService

# ── Fixtures ───────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_LEAD_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-crm-test-001",
)


def _make_lead(stage: str = "discovered", score: int = 0) -> Lead:
    l = Lead(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        stage=stage,
        score=score,
        notes=None,
    )
    l.id = _LEAD_ID
    l.extra = {}
    l.meeting_scheduled_at = None
    l.booked_at = None
    l.created_at = datetime.now(UTC)
    l.updated_at = datetime.now(UTC)
    return l


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ── Tests: create_lead ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_lead_happy_path():
    """New lead is created in 'discovered' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_active_by_contact = AsyncMock(return_value=None)

    async def _create_side_effect(lead: Lead) -> Lead:
        lead.id = _LEAD_ID
        lead.created_at = datetime.now(UTC)
        lead.updated_at = datetime.now(UTC)
        lead.extra = {}
        return lead

    svc._repo.create = _create_side_effect

    req = LeadCreate(contact_id=_CONTACT_ID, workspace_id=_WS_ID)
    result = await svc.create_lead(req)

    clear_tenant_context(token)
    assert result.stage == "discovered"
    assert result.score == 0
    assert result.contact_id == _CONTACT_ID


@pytest.mark.asyncio
async def test_create_lead_duplicate_active_raises():
    """ConflictError when the contact already has a non-terminal lead."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_active_by_contact = AsyncMock(return_value=_make_lead("engaged"))

    req = LeadCreate(contact_id=_CONTACT_ID, workspace_id=_WS_ID)
    with pytest.raises(ConflictError, match="already has an active lead"):
        await svc.create_lead(req)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_create_lead_after_terminal_allowed():
    """Creating a lead succeeds when prior lead is terminal (re-engagement)."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    # find_active_by_contact only returns non-terminal leads, so None = safe to create
    svc._repo.find_active_by_contact = AsyncMock(return_value=None)

    async def _create_side_effect(lead: Lead) -> Lead:
        lead.id = uuid.uuid4()
        lead.created_at = datetime.now(UTC)
        lead.updated_at = datetime.now(UTC)
        lead.extra = {}
        return lead

    svc._repo.create = _create_side_effect

    req = LeadCreate(contact_id=_CONTACT_ID, workspace_id=_WS_ID)
    result = await svc.create_lead(req)

    clear_tenant_context(token)
    assert result.stage == "discovered"


# ── Tests: advance_stage ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_advance_discovered_to_engaged():
    """discovered → engaged happy path."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("discovered"))
    svc._repo.update_fields = AsyncMock()

    result = await svc.advance_stage(_LEAD_ID)

    clear_tenant_context(token)
    assert result.from_stage == "discovered"
    assert result.to_stage == "engaged"
    svc._repo.update_fields.assert_called_once()
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["stage"] == "engaged"


@pytest.mark.asyncio
async def test_advance_meeting_completed_to_booked_sets_booked_at():
    """Transitioning to 'booked' injects booked_at timestamp."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("meeting_completed"))
    svc._repo.update_fields = AsyncMock()

    result = await svc.advance_stage(_LEAD_ID)

    clear_tenant_context(token)
    assert result.to_stage == "booked"
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert "booked_at" in call_kwargs
    assert isinstance(call_kwargs["booked_at"], datetime)


@pytest.mark.asyncio
async def test_advance_from_terminal_raises():
    """ConflictError when advancing from a terminal stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("booked"))

    with pytest.raises(ConflictError, match="terminal stage"):
        await svc.advance_stage(_LEAD_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_advance_from_lost_raises():
    """ConflictError when advancing from 'lost'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("lost"))

    with pytest.raises(ConflictError, match="terminal stage"):
        await svc.advance_stage(_LEAD_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_advance_with_notes_propagated():
    """Notes are included in update_fields when provided."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("engaged"))
    svc._repo.update_fields = AsyncMock()

    await svc.advance_stage(_LEAD_ID, notes="Sent proposal doc")

    clear_tenant_context(token)
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["notes"] == "Sent proposal doc"


# ── Tests: mark_lost ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_lost_from_engaged():
    """Any non-terminal lead can be marked lost."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("engaged"))
    svc._repo.update_fields = AsyncMock()

    result = await svc.mark_lost(_LEAD_ID, notes="Budget cut")

    clear_tenant_context(token)
    assert result.stage == "lost"
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["stage"] == "lost"
    assert call_kwargs["notes"] == "Budget cut"


@pytest.mark.asyncio
async def test_mark_lost_already_terminal_raises():
    """ConflictError when marking an already-terminal lead as lost."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("booked"))

    with pytest.raises(ConflictError, match="terminal stage"):
        await svc.mark_lost(_LEAD_ID)

    clear_tenant_context(token)


# ── Tests: update_score ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_score():
    """Score is updated and reflected in the response."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    lead = _make_lead("engaged", score=20)
    svc._repo.find_by_id = AsyncMock(return_value=lead)
    svc._repo.update_fields = AsyncMock()

    result = await svc.update_score(_LEAD_ID, 85)

    clear_tenant_context(token)
    assert result.score == 85
    svc._repo.update_fields.assert_called_once_with(_LEAD_ID, score=85)


# ── Tests: schedule_meeting ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_meeting_happy_path():
    """Meeting datetime is set for a lead in 'meeting_scheduled' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    lead = _make_lead("meeting_scheduled")
    svc._repo.find_by_id = AsyncMock(return_value=lead)
    svc._repo.update_fields = AsyncMock()

    meeting_time = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)
    result = await svc.schedule_meeting(_LEAD_ID, meeting_time)

    clear_tenant_context(token)
    assert result.meeting_scheduled_at == meeting_time
    svc._repo.update_fields.assert_called_once_with(_LEAD_ID, meeting_scheduled_at=meeting_time)


@pytest.mark.asyncio
async def test_schedule_meeting_wrong_stage_raises():
    """ConflictError when setting meeting time before advancing to 'meeting_scheduled'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_lead("engaged"))

    with pytest.raises(ConflictError, match="meeting_scheduled"):
        await svc.schedule_meeting(_LEAD_ID, datetime.now(UTC))

    clear_tenant_context(token)


# ── Tests: get_lead ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_lead_not_found_raises():
    """NotFoundError when lead does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.get_lead(_LEAD_ID)

    clear_tenant_context(token)


# ── Tests: list_pipeline ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_pipeline_invalid_stage_raises():
    """ValidationError when filtering by an unrecognised stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    with pytest.raises(ValidationError, match="Invalid stage"):
        await svc.list_pipeline(_WS_ID, stage="flying")

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_list_pipeline_returns_items():
    """Pipeline list returns serialised leads."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.list_pipeline = AsyncMock(return_value=[_make_lead("discovered"), _make_lead("engaged")])
    svc._repo.count_pipeline = AsyncMock(return_value=2)

    result = await svc.list_pipeline(_WS_ID)

    clear_tenant_context(token)
    assert result.total == 2
    assert result.items[0].stage == "discovered"
    assert result.items[1].stage == "engaged"


# ── Tests: get_pipeline_stats ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pipeline_stats_zero_fills_missing_stages():
    """Stages with no leads still appear in stats with count=0."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = CRMService(session)

    svc._repo.count_by_stage = AsyncMock(return_value={"discovered": 3, "booked": 1})

    result = await svc.get_pipeline_stats(_WS_ID)

    clear_tenant_context(token)
    assert result.total == 4
    stage_map = {s.stage: s.count for s in result.stages}
    assert stage_map["discovered"] == 3
    assert stage_map["booked"] == 1
    assert stage_map["engaged"] == 0
    assert stage_map["lost"] == 0
