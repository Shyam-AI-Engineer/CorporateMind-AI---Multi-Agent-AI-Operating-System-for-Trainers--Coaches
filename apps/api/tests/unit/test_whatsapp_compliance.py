"""Unit tests for WhatsApp-specific ComplianceService checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.compliance.schemas import ComplianceCheckRequest, ComplianceOutcome
from corpmind.modules.compliance.service import ComplianceService


def _make_req(contact_id: uuid.UUID | None = None) -> ComplianceCheckRequest:
    return ComplianceCheckRequest(
        contact_id=contact_id or uuid.uuid4(),
        channel="whatsapp",
        content_hash="abc123",
        recipient_hash="hashvalue",
    )


def _make_service():
    session = MagicMock()
    session.execute = AsyncMock()
    return ComplianceService(session)


def _mock_ctx(org_id: uuid.UUID | None = None):
    ctx = MagicMock()
    ctx.org_id = org_id or uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    return ctx


class TestCheckWhatsAppOptIn:
    @pytest.mark.asyncio
    async def test_allowed_when_opt_in_present(self):
        svc = _make_service()
        ctx = _mock_ctx()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [datetime.now(UTC), True][i]
        row.__bool__ = lambda self: True

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        svc._session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_whatsapp_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.ALLOWED

    @pytest.mark.asyncio
    async def test_blocked_when_no_opt_in(self):
        svc = _make_service()
        ctx = _mock_ctx()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [None, True][i]
        row.__bool__ = lambda self: True

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        svc._session.execute = AsyncMock(return_value=mock_result)

        # audit write also needs mocking
        svc._audit = MagicMock()
        mock_event = MagicMock()
        mock_event.id = uuid.uuid4()
        svc._audit.append = AsyncMock(return_value=mock_event)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_whatsapp_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "whatsapp_opt_in"

    @pytest.mark.asyncio
    async def test_blocked_when_contact_not_found(self):
        svc = _make_service()
        ctx = _mock_ctx()

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        svc._session.execute = AsyncMock(return_value=mock_result)

        svc._audit = MagicMock()
        mock_event = MagicMock()
        mock_event.id = uuid.uuid4()
        svc._audit.append = AsyncMock(return_value=mock_event)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_whatsapp_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED

    @pytest.mark.asyncio
    async def test_blocked_when_phone_not_deliverable(self):
        svc = _make_service()
        ctx = _mock_ctx()
        row = MagicMock()
        # has opt_in but phone_deliverable=False
        row.__getitem__ = lambda self, i: [datetime.now(UTC), False][i]
        row.__bool__ = lambda self: True

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = row
        svc._session.execute = AsyncMock(return_value=mock_result)

        svc._audit = MagicMock()
        mock_event = MagicMock()
        mock_event.id = uuid.uuid4()
        svc._audit.append = AsyncMock(return_value=mock_event)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_whatsapp_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "phone_not_deliverable"
