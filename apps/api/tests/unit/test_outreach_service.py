"""Unit tests for OutreachService.

These tests mock the DB session and EuriClient so they run without a real
Postgres or LLM provider.  Compliance is also mocked at the service level
so tests stay focused on OutreachService logic, not compliance internals.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch


import pytest

from corpmind.core.exceptions import ComplianceBlockError, ConflictError, NotFoundError
from corpmind.core.tenancy import TenantContext, set_tenant_context, clear_tenant_context
from corpmind.modules.compliance.schemas import ComplianceCheckResult, ComplianceOutcome
from corpmind.modules.outreach.models import OutboundMessage
from corpmind.modules.outreach.schemas import GenerateOutreachRequest
from corpmind.modules.outreach.service import OutreachService, recipient_hmac


# ── Fixtures ──────────────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_MESSAGE_ID = uuid.uuid4()

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-test-001",
)

_CONTACT_ROW = {
    "id": _CONTACT_ID,
    "full_name": "Priya Sharma",
    "title": "VP-HR",
    "email": "priya@hdfc.example",
    "is_contactable": True,
    "preferred_language": "en",
    "company_name": "HDFC Life Insurance",
    "industry": "Insurance",
}

_TRAINER_ROW = {
    "niche": "Leadership Development",
    "topics": ["leadership", "coaching"],
    "tone": "semi_formal",
    "pricing_min_inr": 50000,
    "pricing_max_inr": 150000,
    "bio": "10 years in L&D at Fortune 500 companies.",
    "usp": "Cuts promotion-readiness time by 6 months.",
    "target_industries": ["Insurance", "BFSI"],
}

_LLM_COPY = json.dumps({
    "subject": "Building HDFC Life's leadership bench",
    "body": "Hi Priya, I noticed HDFC Life is scaling rapidly. "
            "I help HR teams build leadership pipelines faster. "
            "Would 15 minutes work this week?",
    "tone_used": "semi_formal",
    "language_used": "en",
})

_ALLOWED = ComplianceCheckResult(outcome=ComplianceOutcome.ALLOWED)
_BLOCKED_OPT_IN = ComplianceCheckResult(
    outcome=ComplianceOutcome.BLOCKED,
    reason="Contact has no current opt-in",
    blocked_by="opt_in",
)
_BLOCKED_FREQ = ComplianceCheckResult(
    outcome=ComplianceOutcome.BLOCKED,
    reason="Frequency cap reached",
    blocked_by="frequency_cap",
)


def _make_message(status: str = "draft") -> OutboundMessage:
    msg = OutboundMessage(
        tenant_id=_ORG_ID,
        contact_id=_CONTACT_ID,
        channel="email",
        subject="Building HDFC Life's leadership bench",
        body="Hi Priya…",
        prompt_version="outreach.email.v1",
        status=status,
    )
    msg.id = _MESSAGE_ID
    msg.campaign_id = None
    msg.ab_variant = None
    msg.provider_message_id = None
    msg.sent_at = None
    msg.created_at = datetime.now(UTC)
    return msg


def _make_session(contact_row=_CONTACT_ROW, trainer_row=_TRAINER_ROW):
    """Mock AsyncSession with the minimal execute() chain for contact + trainer queries."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    # We need execute() to return different results depending on the SQL issued.
    # Use a side_effect that inspects the query text.
    execute_results = []

    def _make_mapping_result(row_dict):
        mapping_result = MagicMock()
        mapping_result.mappings.return_value.one_or_none.return_value = (
            row_dict if row_dict else None
        )
        return mapping_result

    # Capture calls and return appropriate mock results.
    call_index = {"n": 0}

    async def _execute(stmt, params=None):
        n = call_index["n"]
        call_index["n"] += 1
        if n == 0:
            # First call: contact lookup
            return _make_mapping_result(contact_row)
        else:
            # Subsequent: trainer profile lookup
            return _make_mapping_result(trainer_row)

    session.execute = _execute

    # flush used by repo.create
    session.flush = AsyncMock(side_effect=lambda: setattr(_make_session, "_flushed", True))
    return session


# ── Tests: generate_message ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_message_happy_path():
    """Draft message is created when contact is contactable and compliance passes."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    with (
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.EuriClient.chat",
            new_callable=AsyncMock,
            return_value={"content": _LLM_COPY},
        ),
        patch.object(
            session.__class__, "__aenter__", return_value=session
        ),
    ):
        # Stub repo.create to assign an ID
        async def _stub_flush():
            pass

        session.flush = AsyncMock()

        svc = OutreachService(session)

        # Patch repo.create to return msg with ID set
        created_msg = _make_message()

        async def _create(msg):
            msg.id = _MESSAGE_ID
            msg.created_at = datetime.now(UTC)
            return msg

        svc._repo.create = _create
        svc._session.commit = AsyncMock()

        req = GenerateOutreachRequest(contact_id=_CONTACT_ID, channel="email")
        result = await svc.generate_message(req)

    clear_tenant_context(token)

    assert result.contact_id == _CONTACT_ID
    assert result.channel == "email"
    assert result.status == "draft"
    assert result.prompt_version == "outreach.email.v1"


@pytest.mark.asyncio
async def test_generate_message_contact_not_found():
    """NotFoundError is raised when the contact lookup returns None."""
    token = set_tenant_context(_CTX)
    session = _make_session(contact_row=None)

    svc = OutreachService(session)
    req = GenerateOutreachRequest(contact_id=_CONTACT_ID, channel="email")

    with pytest.raises(NotFoundError):
        await svc.generate_message(req)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_generate_message_blocked_opt_in():
    """ComplianceBlockError is raised when opt-in check fails (before LLM call)."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    with patch(
        "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
        new_callable=AsyncMock,
        return_value=_BLOCKED_OPT_IN,
    ):
        svc = OutreachService(session)
        req = GenerateOutreachRequest(contact_id=_CONTACT_ID, channel="email")
        with pytest.raises(ComplianceBlockError):
            await svc.generate_message(req)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_generate_message_invalid_llm_response():
    """ValidationError is raised when EuriClient returns non-JSON."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    with (
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.EuriClient.chat",
            new_callable=AsyncMock,
            return_value={"content": "Sure, here is your email: ..."},
        ),
    ):
        from corpmind.core.exceptions import ValidationError

        svc = OutreachService(session)
        req = GenerateOutreachRequest(contact_id=_CONTACT_ID, channel="email")
        with pytest.raises(ValidationError):
            await svc.generate_message(req)

    clear_tenant_context(token)


# ── Tests: send_message ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_enqueues_task():
    """send_message returns status=queued and calls apply_async."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    svc = OutreachService(session)
    svc._repo.find_by_id = AsyncMock(return_value=_make_message("draft"))
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    with (
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_frequency_cap",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_unsubscribe",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.workers.tasks.outreach.send_message"
        ) as mock_task,
    ):
        mock_task.apply_async = MagicMock()
        result = await svc.send_message(_MESSAGE_ID)

    clear_tenant_context(token)

    assert result.status == "queued"
    assert result.message_id == _MESSAGE_ID
    assert result.compliance_reason is None


@pytest.mark.asyncio
async def test_send_message_blocked_by_unsubscribe():
    """send_message returns status=blocked when unsubscribe check fails."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    svc = OutreachService(session)
    svc._repo.find_by_id = AsyncMock(return_value=_make_message("draft"))
    svc._repo.update_status = AsyncMock()
    svc._session.commit = AsyncMock()

    blocked = ComplianceCheckResult(
        outcome=ComplianceOutcome.BLOCKED,
        reason="Contact is on the unsubscribe list",
        blocked_by="unsubscribe",
    )

    with (
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_opt_in",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_frequency_cap",
            new_callable=AsyncMock,
            return_value=_ALLOWED,
        ),
        patch(
            "corpmind.modules.outreach.service.ComplianceService.check_unsubscribe",
            new_callable=AsyncMock,
            return_value=blocked,
        ),
    ):
        result = await svc.send_message(_MESSAGE_ID)

    clear_tenant_context(token)

    assert result.status == "blocked"
    assert "unsubscribe" in (result.compliance_reason or "")
    svc._repo.update_status.assert_called_once_with(_MESSAGE_ID, "blocked")


@pytest.mark.asyncio
async def test_send_message_already_sent_raises_conflict():
    """ConflictError is raised when message is not in draft status."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    svc = OutreachService(session)
    svc._repo.find_by_id = AsyncMock(return_value=_make_message("sent"))

    with pytest.raises(ConflictError, match="already sent"):
        await svc.send_message(_MESSAGE_ID)

    clear_tenant_context(token)


@pytest.mark.asyncio
async def test_send_message_not_found_raises():
    """NotFoundError is raised when message ID does not exist."""
    token = set_tenant_context(_CTX)
    session = _make_session()

    svc = OutreachService(session)
    svc._repo.find_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await svc.send_message(_MESSAGE_ID)

    clear_tenant_context(token)


# ── Tests: helpers ─────────────────────────────────────────────────────────────

def test_recipient_hmac_is_per_tenant():
    """Same email produces different hashes for different tenants."""
    email = "hr@company.example"
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    assert recipient_hmac(email, org_a) != recipient_hmac(email, org_b)


def test_recipient_hmac_none_email():
    """Returns None when no email is available."""
    assert recipient_hmac(None, uuid.uuid4()) is None


def test_recipient_hmac_is_deterministic():
    """Same inputs always produce the same hash."""
    email = "test@example.com"
    org = uuid.uuid4()
    assert recipient_hmac(email, org) == recipient_hmac(email, org)
