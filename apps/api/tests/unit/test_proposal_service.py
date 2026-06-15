"""Unit tests for ProposalService.

Mocks: DB session, ProposalRepo, EuriClient.
Tests cover generation stage guard, AI content parsing, status transitions, and CRUD reads.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.crm.schemas import LeadOut
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.schemas import GenerateProposalRequest
from corpmind.modules.proposals.service import ProposalService, _parse_content

# ── Fixtures ───────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PROPOSAL_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_LEAD_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-proposal-test-001",
)

_AI_CONTENT = {
    "title": "Leadership Excellence Workshop",
    "executive_summary": "Transform your leadership team.",
    "proposed_training": {
        "topic": "Executive Communication",
        "duration": "2-day workshop",
        "format": "in-person",
        "participants": "20-30 leaders",
    },
    "value_proposition": ["Outcome 1", "Outcome 2", "Outcome 3"],
    "proposed_agenda": [],
    "investment": "TBD",
    "call_to_action": "Schedule a discovery call",
}


def _make_lead(stage: str = "meeting_completed", score: int = 75) -> LeadOut:
    return LeadOut(
        id=_LEAD_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        stage=stage,
        score=score,
        notes="Interested in leadership training",
        extra={},
        meeting_scheduled_at=datetime(2026, 6, 10, 10, 0, tzinfo=UTC),
        booked_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_proposal(
    status: str = "draft",
    approval_status: str = "pending_approval",
) -> Proposal:
    p = Proposal(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        contact_id=_CONTACT_ID,
        title="Leadership Excellence Workshop",
        status=status,
        content=_AI_CONTENT,
    )
    p.id = _PROPOSAL_ID
    p.cloudinary_url = None
    p.sent_at = None
    p.created_at = datetime.now(UTC)
    # Approval fields must be set explicitly — Python-side default is applied at
    # flush time, not at constructor time, so unit tests using mock sessions need
    # these set directly.
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


# ── Tests: generate ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_happy_path_meeting_completed():
    """Proposal is created for a lead in 'meeting_completed' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    async def _create_side_effect(proposal: Proposal) -> Proposal:
        proposal.id = _PROPOSAL_ID
        proposal.cloudinary_url = None
        proposal.sent_at = None
        proposal.created_at = datetime.now(UTC)
        return proposal

    svc._repo.create = _create_side_effect

    with patch("corpmind.modules.proposals.service.EuriClient") as MockEuriClient:
        mock_client = AsyncMock()
        MockEuriClient.return_value = mock_client
        mock_client.chat = AsyncMock(return_value={"content": json.dumps(_AI_CONTENT)})

        req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
        result = await svc.generate(req, _make_lead("meeting_completed"))

    clear_tenant_context(token)
    assert result.status == "draft"
    assert result.contact_id == _CONTACT_ID
    assert result.workspace_id == _WS_ID
    assert result.title == "Leadership Excellence Workshop"


@pytest.mark.asyncio
async def test_generate_happy_path_booked():
    """Proposal is also allowed for leads in 'booked' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    async def _create_side_effect(proposal: Proposal) -> Proposal:
        proposal.id = _PROPOSAL_ID
        proposal.cloudinary_url = None
        proposal.sent_at = None
        proposal.created_at = datetime.now(UTC)
        return proposal

    svc._repo.create = _create_side_effect

    with patch("corpmind.modules.proposals.service.EuriClient") as MockEuriClient:
        mock_client = AsyncMock()
        MockEuriClient.return_value = mock_client
        mock_client.chat = AsyncMock(return_value={"content": json.dumps(_AI_CONTENT)})

        req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
        result = await svc.generate(req, _make_lead("booked"))

    clear_tenant_context(token)
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_generate_wrong_stage_discovered_raises():
    """ValidationError for lead in 'discovered' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
    with pytest.raises(ValidationError, match="meeting_completed"):
        await svc.generate(req, _make_lead("discovered"))

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_generate_wrong_stage_engaged_raises():
    """ValidationError for lead in 'engaged' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
    with pytest.raises(ValidationError, match="engaged"):
        await svc.generate(req, _make_lead("engaged"))

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_generate_wrong_stage_lost_raises():
    """ValidationError for lead in 'lost' stage."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
    with pytest.raises(ValidationError, match="lost"):
        await svc.generate(req, _make_lead("lost"))

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_generate_ai_content_stored_in_proposal():
    """AI-returned JSON is stored in proposal.content."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    captured: list[Proposal] = []

    async def _create_side_effect(proposal: Proposal) -> Proposal:
        proposal.id = _PROPOSAL_ID
        proposal.cloudinary_url = None
        proposal.sent_at = None
        proposal.created_at = datetime.now(UTC)
        captured.append(proposal)
        return proposal

    svc._repo.create = _create_side_effect

    with patch("corpmind.modules.proposals.service.EuriClient") as MockEuriClient:
        mock_client = AsyncMock()
        MockEuriClient.return_value = mock_client
        mock_client.chat = AsyncMock(return_value={"content": json.dumps(_AI_CONTENT)})

        req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
        await svc.generate(req, _make_lead("meeting_completed"))

    clear_tenant_context(token)
    assert len(captured) == 1
    assert captured[0].content["title"] == "Leadership Excellence Workshop"
    assert captured[0].content["call_to_action"] == "Schedule a discovery call"


@pytest.mark.asyncio
async def test_generate_euri_called_with_correct_task():
    """EuriClient.chat is called with task='proposal_generation'."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    async def _create_side_effect(proposal: Proposal) -> Proposal:
        proposal.id = _PROPOSAL_ID
        proposal.cloudinary_url = None
        proposal.sent_at = None
        proposal.created_at = datetime.now(UTC)
        return proposal

    svc._repo.create = _create_side_effect

    with patch("corpmind.modules.proposals.service.EuriClient") as MockEuriClient:
        mock_client = AsyncMock()
        MockEuriClient.return_value = mock_client
        mock_client.chat = AsyncMock(return_value={"content": json.dumps(_AI_CONTENT)})

        req = GenerateProposalRequest(lead_id=_LEAD_ID, workspace_id=_WS_ID)
        await svc.generate(req, _make_lead("meeting_completed"))

        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["task"] == "proposal_generation"
        assert call_kwargs["prompt_name"] == "proposals.generate"
        assert call_kwargs["tenant_id"] == _ORG_ID

    clear_tenant_context(token)


# ── Tests: _parse_content ──────────────────────────────────────────────────────

def test_parse_content_valid_json():
    """Valid JSON dict is returned unchanged."""
    raw = json.dumps({"title": "Test", "body": "Content"})
    result = _parse_content(raw)
    assert result == {"title": "Test", "body": "Content"}


def test_parse_content_invalid_json_fallback():
    """Non-JSON string falls back to title+body dict."""
    raw = "This is a great proposal for your leadership team."
    result = _parse_content(raw)
    assert "title" in result
    assert "body" in result
    assert result["body"] == raw


def test_parse_content_json_list_fallback():
    """JSON that is a list (not a dict) falls back to title+body."""
    raw = json.dumps(["item1", "item2"])
    result = _parse_content(raw)
    assert "title" in result
    assert "body" in result


def test_parse_content_long_raw_truncates_title():
    """Title field is capped at 200 chars from raw string."""
    raw = "x" * 300
    result = _parse_content(raw)
    assert len(result["title"]) == 200


# ── Tests: get_proposal ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_proposal_happy_path():
    """get_proposal returns a ProposalOut for an existing record."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_proposal("draft"))

    result = await svc.get_proposal(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert result.id == _PROPOSAL_ID
    assert result.status == "draft"


@pytest.mark.asyncio
async def test_get_proposal_not_found_raises():
    """NotFoundError when proposal does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.get_proposal(_PROPOSAL_ID)

    clear_tenant_context(token)


# ── Tests: list_proposals ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_proposals_returns_items():
    """list_proposals returns serialised proposals."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.list_by_workspace = AsyncMock(
        return_value=[_make_proposal("draft"), _make_proposal("sent")]
    )
    svc._repo.count_by_workspace = AsyncMock(return_value=2)

    result = await svc.list_proposals(_WS_ID)

    clear_tenant_context(token)
    assert result.total == 2
    assert result.items[0].status == "draft"
    assert result.items[1].status == "sent"


@pytest.mark.asyncio
async def test_list_proposals_empty():
    """list_proposals returns empty list when no proposals exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.list_by_workspace = AsyncMock(return_value=[])
    svc._repo.count_by_workspace = AsyncMock(return_value=0)

    result = await svc.list_proposals(_WS_ID)

    clear_tenant_context(token)
    assert result.total == 0
    assert result.items == []


# ── Tests: mark_sent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_sent_happy_path():
    """Approved draft proposal transitions to 'sent' with sent_at populated."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_proposal("draft", approval_status="approved"))
    svc._repo.update_fields = AsyncMock()

    result = await svc.mark_sent(_PROPOSAL_ID)

    clear_tenant_context(token)
    assert result.status == "sent"
    assert result.sent_at is not None
    assert isinstance(result.sent_at, datetime)
    call_kwargs = svc._repo.update_fields.call_args[1]
    assert call_kwargs["status"] == "sent"
    assert "sent_at" in call_kwargs


@pytest.mark.asyncio
async def test_mark_sent_already_sent_raises():
    """ConflictError when marking an already-sent proposal (status check fires first)."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    # approval_status="approved" so only the status="sent" guard triggers, not the approval guard
    svc._repo.find_by_id = AsyncMock(return_value=_make_proposal("sent", approval_status="approved"))

    with pytest.raises(ConflictError, match="already been sent"):
        await svc.mark_sent(_PROPOSAL_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_mark_sent_pending_approval_raises():
    """ConflictError when proposal has not been approved yet."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id = AsyncMock(return_value=_make_proposal("draft", approval_status="pending_approval"))

    with pytest.raises(ConflictError, match="must be approved"):
        await svc.mark_sent(_PROPOSAL_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_mark_sent_not_found_raises():
    """NotFoundError when proposal does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()
    svc = ProposalService(session)

    svc._repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.mark_sent(_PROPOSAL_ID)

    clear_tenant_context(token)
