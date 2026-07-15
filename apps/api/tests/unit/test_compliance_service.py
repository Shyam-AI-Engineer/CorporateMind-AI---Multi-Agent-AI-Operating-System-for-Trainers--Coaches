"""Unit tests for ComplianceService — opt-in, unsubscribe, and audit checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.compliance.schemas import ComplianceCheckRequest, ComplianceOutcome
from corpmind.modules.compliance.service import ComplianceService, _recipient_hmac


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_req(
    contact_id: uuid.UUID | None = None,
    channel: str = "email",
    recipient_hash: str | None = None,
) -> ComplianceCheckRequest:
    return ComplianceCheckRequest(
        contact_id=contact_id or uuid.uuid4(),
        channel=channel,
        content_hash="abc123",
        recipient_hash=recipient_hash,
    )


def _make_svc():
    session = MagicMock()
    session.execute = AsyncMock()
    return ComplianceService(session)


def _mock_ctx(org_id: uuid.UUID | None = None):
    ctx = MagicMock()
    ctx.org_id = org_id or uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    return ctx


def _mock_audit(svc: ComplianceService) -> MagicMock:
    """Replace the audit repo on a service instance with a mock."""
    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    svc._audit = MagicMock()
    svc._audit.append = AsyncMock(return_value=mock_event)
    return svc._audit


def _db_row(*values):
    """Return a mock DB row whose items are indexable."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__bool__ = lambda self: True
    return row


def _db_result(row_or_none):
    result = MagicMock()
    result.one_or_none.return_value = row_or_none
    return result


# ── _recipient_hmac unit tests ────────────────────────────────────────────────

class TestRecipientHmac:
    def test_returns_none_for_none_email(self):
        assert _recipient_hmac(None, uuid.uuid4()) is None

    def test_returns_none_for_empty_email(self):
        assert _recipient_hmac("", uuid.uuid4()) is None

    def test_returns_hex_string(self):
        h = _recipient_hmac("alice@example.com", uuid.uuid4())
        assert h is not None
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_email_same_tenant_same_hash(self):
        tid = uuid.uuid4()
        h1 = _recipient_hmac("bob@example.com", tid)
        h2 = _recipient_hmac("bob@example.com", tid)
        assert h1 == h2

    def test_same_email_different_tenant_different_hash(self):
        h1 = _recipient_hmac("bob@example.com", uuid.uuid4())
        h2 = _recipient_hmac("bob@example.com", uuid.uuid4())
        assert h1 != h2

    def test_different_email_same_tenant_different_hash(self):
        tid = uuid.uuid4()
        h1 = _recipient_hmac("alice@example.com", tid)
        h2 = _recipient_hmac("bob@example.com", tid)
        assert h1 != h2


# ── check_opt_in ──────────────────────────────────────────────────────────────

class TestCheckOptIn:
    @pytest.mark.asyncio
    async def test_passes_when_contactable_and_opted_in(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        now = datetime.now(UTC)
        svc._session.execute = AsyncMock(
            return_value=_db_result(_db_row(True, now, "https://evidence.example.com"))
        )

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.ALLOWED
        assert result.blocked_by is None

    @pytest.mark.asyncio
    async def test_fails_when_contact_not_found(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        _mock_audit(svc)
        svc._session.execute = AsyncMock(return_value=_db_result(None))

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "opt_in"
        assert "not found" in (result.reason or "").lower()

    @pytest.mark.asyncio
    async def test_fails_when_not_contactable(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        _mock_audit(svc)
        now = datetime.now(UTC)
        svc._session.execute = AsyncMock(
            return_value=_db_result(_db_row(False, now, "evidence"))
        )

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "opt_in"
        assert result.audit_event_id is not None

    @pytest.mark.asyncio
    async def test_fails_when_opted_in_at_is_none(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        _mock_audit(svc)
        svc._session.execute = AsyncMock(
            return_value=_db_result(_db_row(True, None, "evidence"))
        )

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "opt_in"
        assert "timestamp" in (result.reason or "").lower()

    @pytest.mark.asyncio
    async def test_passes_without_opt_in_evidence(self):
        """opted_in_at present is sufficient; evidence is optional (best-effort)."""
        svc = _make_svc()
        ctx = _mock_ctx()
        now = datetime.now(UTC)
        svc._session.execute = AsyncMock(
            return_value=_db_result(_db_row(True, now, None))
        )

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_opt_in(_make_req())

        assert result.outcome == ComplianceOutcome.ALLOWED

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_sql(self):
        """SQL WHERE clause must include tenant_id."""
        svc = _make_svc()
        ctx = _mock_ctx()
        now = datetime.now(UTC)
        svc._session.execute = AsyncMock(
            return_value=_db_result(_db_row(True, now, "evidence"))
        )

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.check_opt_in(_make_req())

        call_args = svc._session.execute.call_args
        sql_str = str(call_args[0][0]).lower()
        params = call_args[0][1]
        assert "tenant_id" in sql_str
        assert params["tid"] == str(ctx.org_id)

    @pytest.mark.asyncio
    async def test_audit_event_written_on_block(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        audit = _mock_audit(svc)
        svc._session.execute = AsyncMock(return_value=_db_result(None))

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.check_opt_in(_make_req())

        audit.append.assert_awaited_once()


# ── check_unsubscribe ─────────────────────────────────────────────────────────

class TestCheckUnsubscribe:
    @pytest.mark.asyncio
    async def test_passes_when_not_unsubscribed(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=False)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe(
                _make_req(recipient_hash="hashvalue")
            )

        assert result.outcome == ComplianceOutcome.ALLOWED

    @pytest.mark.asyncio
    async def test_fails_when_unsubscribed(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        _mock_audit(svc)
        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=True)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe(
                _make_req(recipient_hash="hashvalue")
            )

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "unsubscribe"
        assert result.audit_event_id is not None

    @pytest.mark.asyncio
    async def test_allows_when_no_hash(self):
        """No recipient_hash means we cannot check — current safe default is ALLOWED."""
        svc = _make_svc()
        ctx = _mock_ctx()

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe(_make_req(recipient_hash=None))

        assert result.outcome == ComplianceOutcome.ALLOWED

    @pytest.mark.asyncio
    async def test_unsubscribe_calls_repo_with_tenant_id(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=False)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.check_unsubscribe(_make_req(recipient_hash="h", channel="email"))

        svc._unsub.is_unsubscribed.assert_awaited_once_with(ctx.org_id, "h", "email")


# ── check_unsubscribe_by_contact_id ──────────────────────────────────────────

class TestCheckUnsubscribeByContactId:
    @pytest.mark.asyncio
    async def test_resolves_email_and_delegates_to_check_unsubscribe(self):
        contact_id = uuid.uuid4()
        org_id = uuid.uuid4()
        svc = _make_svc()
        ctx = _mock_ctx(org_id=org_id)

        email_row = MagicMock()
        email_row.__getitem__ = lambda self, i: "alice@corp.com" if i == 0 else None
        email_row.__bool__ = lambda self: True
        svc._session.execute = AsyncMock(return_value=_db_result(email_row))

        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=False)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe_by_contact_id(
                _make_req(contact_id=contact_id)
            )

        assert result.outcome == ComplianceOutcome.ALLOWED
        # recipient_hash was computed from email and passed to repo
        svc._unsub.is_unsubscribed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blocked_when_email_is_on_unsubscribe_list(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        _mock_audit(svc)

        email_row = MagicMock()
        email_row.__getitem__ = lambda self, i: "bob@corp.com" if i == 0 else None
        email_row.__bool__ = lambda self: True
        svc._session.execute = AsyncMock(return_value=_db_result(email_row))

        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=True)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe_by_contact_id(_make_req())

        assert result.outcome == ComplianceOutcome.BLOCKED
        assert result.blocked_by == "unsubscribe"

    @pytest.mark.asyncio
    async def test_allows_when_contact_not_found(self):
        """Contact not found = already handled by opt_in check; don't double-block."""
        svc = _make_svc()
        ctx = _mock_ctx()
        svc._session.execute = AsyncMock(return_value=_db_result(None))

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            result = await svc.check_unsubscribe_by_contact_id(_make_req())

        assert result.outcome == ComplianceOutcome.ALLOWED

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_email_lookup(self):
        svc = _make_svc()
        ctx = _mock_ctx()

        email_row = MagicMock()
        email_row.__getitem__ = lambda self, i: "x@y.com" if i == 0 else None
        email_row.__bool__ = lambda self: True
        svc._session.execute = AsyncMock(return_value=_db_result(email_row))
        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=False)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.check_unsubscribe_by_contact_id(_make_req())

        params = svc._session.execute.call_args[0][1]
        assert params["tid"] == str(ctx.org_id)

    @pytest.mark.asyncio
    async def test_workspace_isolation_via_tenant_context(self):
        """All lookups use org_id from TenantContext; callers cannot override it."""
        svc = _make_svc()
        ctx = _mock_ctx(org_id=uuid.uuid4())

        email_row = MagicMock()
        email_row.__getitem__ = lambda self, i: "x@y.com" if i == 0 else None
        email_row.__bool__ = lambda self: True
        svc._session.execute = AsyncMock(return_value=_db_result(email_row))
        svc._unsub = MagicMock()
        svc._unsub.is_unsubscribed = AsyncMock(return_value=False)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.check_unsubscribe_by_contact_id(_make_req())

        params = svc._session.execute.call_args[0][1]
        assert params["tid"] == str(ctx.org_id)


# ── record_audit_event ────────────────────────────────────────────────────────

class TestRecordAuditEvent:
    @pytest.mark.asyncio
    async def test_writes_audit_event_to_repo(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        audit = _mock_audit(svc)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.record_audit_event(event_type="compliance.decision", outcome="allowed")

        audit.append.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_event_carries_outcome(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        audit = _mock_audit(svc)

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.record_audit_event(
                event_type="compliance.decision",
                outcome="blocked",
                reason="opt_in",
            )

        call = audit.append.call_args[0][0]
        assert call.outcome == "blocked"
        assert call.reason == "opt_in"

    @pytest.mark.asyncio
    async def test_audit_event_carries_event_data(self):
        svc = _make_svc()
        ctx = _mock_ctx()
        audit = _mock_audit(svc)
        extra = {"contact_id": "abc", "workspace_id": "ws1", "campaign_id": "cmp1"}

        with patch("corpmind.modules.compliance.service.get_tenant_context", return_value=ctx):
            await svc.record_audit_event(
                event_type="compliance.decision",
                outcome="allowed",
                event_data=extra,
            )

        call = audit.append.call_args[0][0]
        assert call.event_data == extra
