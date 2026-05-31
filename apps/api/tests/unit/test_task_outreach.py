"""Unit tests for workers/tasks/outreach.py — send_message + _run_send."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded
from unittest.mock import ANY

from corpmind.workers.tasks.outreach import _get_adapter, _run_send, send_message


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ids(message_id: str | None = None):
    return {
        "message_id": message_id or str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "channel": "email",
        "request_id": "req-out-test",
    }


def _redis_mock(*, already_sent: bool = False):
    r = MagicMock()
    r.get.return_value = "1" if already_sent else None
    r.setex = MagicMock()
    r.close = MagicMock()
    return r


def _db_mocks():
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()
    return mock_engine, mock_factory, mock_session


def _compliance_allowed():
    from corpmind.modules.compliance.schemas import ComplianceOutcome
    r = MagicMock()
    r.outcome = ComplianceOutcome.ALLOWED
    return r


def _compliance_blocked(by: str = "unsubscribed"):
    from corpmind.modules.compliance.schemas import ComplianceOutcome
    r = MagicMock()
    r.outcome = ComplianceOutcome.BLOCKED
    r.blocked_by = by
    return r


def _queued_msg():
    return MagicMock(
        status="queued",
        contact_id=uuid.uuid4(),
        channel="email",
        campaign_id=uuid.uuid4(),
        subject="Hello",
        body="Body text",
    )


# ── _get_adapter ───────────────────────────────────────────────────────────────

class TestGetAdapter:
    def test_email_returns_smtp_adapter(self):
        adapter = _get_adapter("email")
        assert adapter is not None
        assert hasattr(adapter, "send")

    def test_unknown_channel_raises_value_error(self):
        with pytest.raises(ValueError, match="No adapter registered"):
            _get_adapter("fax")


# ── Sync wrapper tests ─────────────────────────────────────────────────────────
# For bind=True tasks, .run() already passes the task instance as self.
# Use patch.object on the task to intercept retry calls.

class TestSendMessageSyncWrapper:
    def test_already_sent_returns_early(self):
        msg_id = str(uuid.uuid4())
        r = _redis_mock(already_sent=True)
        with patch("redis.from_url", return_value=r):
            result = send_message.run(**_ids(msg_id))
        assert result["status"] == "already_sent"
        assert result["message_id"] == msg_id

    def test_soft_timeout_retries_with_countdown(self):
        r = _redis_mock()
        with patch.object(send_message, "retry", side_effect=Retry()) as mock_retry:
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=SoftTimeLimitExceeded()):
                    with pytest.raises(Retry):
                        send_message.run(**_ids())
        mock_retry.assert_called_once_with(countdown=30)

    def test_generic_exception_retries(self):
        r = _redis_mock()
        err = RuntimeError("smtp down")
        with patch.object(send_message, "retry", side_effect=Retry()) as mock_retry:
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=err):
                    with pytest.raises(Retry):
                        send_message.run(**_ids())
        mock_retry.assert_called_once_with(exc=err)

    def test_sent_result_sets_redis_key(self):
        r = _redis_mock()
        msg_id = str(uuid.uuid4())
        expected = {"status": "sent", "message_id": msg_id}
        with patch("redis.from_url", return_value=r):
            with patch("asyncio.run", return_value=expected):
                result = send_message.run(**_ids(msg_id))
        r.setex.assert_called_once()
        assert result["status"] == "sent"

    def test_blocked_result_does_not_set_redis_key(self):
        r = _redis_mock()
        msg_id = str(uuid.uuid4())
        blocked = {"status": "blocked", "message_id": msg_id}
        with patch("redis.from_url", return_value=r):
            with patch("asyncio.run", return_value=blocked):
                result = send_message.run(**_ids(msg_id))
        r.setex.assert_not_called()
        assert result["status"] == "blocked"

    def test_redis_connection_always_closed(self):
        r = _redis_mock()
        with patch.object(send_message, "retry", side_effect=Retry()):
            with patch("redis.from_url", return_value=r):
                with patch("asyncio.run", side_effect=RuntimeError("boom")):
                    with pytest.raises(Retry):
                        send_message.run(**_ids())
        r.close.assert_called_once()


# ── Async body: _run_send ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRunSend:
    async def test_message_not_found_returns_skipped(self):
        mock_engine, mock_factory, _ = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = None

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
        ):
            result = await _run_send(**_ids())

        assert result["status"] == "skipped"

    async def test_message_wrong_status_returns_skipped(self):
        mock_engine, mock_factory, _ = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = MagicMock(status="sent")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
        ):
            result = await _run_send(**_ids())

        assert result["status"] == "skipped"

    async def test_no_contact_email_returns_blocked(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = MagicMock(status="queued", contact_id=uuid.uuid4())

        no_email = MagicMock()
        no_email.one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=no_email)

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
        ):
            result = await _run_send(**_ids())

        assert result["status"] == "blocked"
        assert result["reason"] == "no_email"

    async def test_compliance_opt_in_block_returns_blocked(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = _queued_msg()

        email_res = MagicMock()
        email_res.one_or_none.return_value = ("blocked@example.com",)
        mock_session.execute = AsyncMock(return_value=email_res)

        blocked = _compliance_blocked("opt_in_missing")
        mock_compliance = AsyncMock()
        mock_compliance.check_opt_in = AsyncMock(return_value=blocked)

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
            patch("corpmind.modules.compliance.service.ComplianceService", return_value=mock_compliance),
            patch("corpmind.modules.outreach.service.recipient_hmac", return_value="rhash"),
            patch("corpmind.modules.outreach.service._content_hash", return_value="chash"),
        ):
            result = await _run_send(**_ids())

        assert result["status"] == "blocked"
        assert result["reason"] == "opt_in_missing"
        mock_repo.update_status.assert_called()

    async def test_successful_send_returns_sent_and_writes_audit(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = _queued_msg()

        email_res = MagicMock()
        email_res.one_or_none.return_value = ("ok@example.com",)
        mock_session.execute = AsyncMock(return_value=email_res)

        allowed = _compliance_allowed()
        mock_compliance = AsyncMock()
        mock_compliance.check_opt_in = AsyncMock(return_value=allowed)
        mock_compliance.check_frequency_cap = AsyncMock(return_value=allowed)
        mock_compliance.check_unsubscribe = AsyncMock(return_value=allowed)

        mock_adapter = AsyncMock()
        mock_adapter.send.return_value = MagicMock(success=True, provider_message_id="smtp-abc")

        mock_audit_repo = AsyncMock()
        mock_audit_repo.append = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
            patch("corpmind.modules.compliance.service.ComplianceService", return_value=mock_compliance),
            patch("corpmind.modules.compliance.repo.AuditRepo", return_value=mock_audit_repo),
            patch("corpmind.workers.tasks.outreach._get_adapter", return_value=mock_adapter),
            patch("corpmind.modules.outreach.service.recipient_hmac", return_value="rhash"),
            patch("corpmind.modules.outreach.service._content_hash", return_value="chash"),
        ):
            result = await _run_send(**_ids())

        assert result["status"] == "sent"
        assert result["provider_message_id"] == "smtp-abc"
        mock_audit_repo.append.assert_called_once()

    async def test_provider_failure_raises_runtime_error(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = _queued_msg()

        email_res = MagicMock()
        email_res.one_or_none.return_value = ("fail@example.com",)
        mock_session.execute = AsyncMock(return_value=email_res)

        allowed = _compliance_allowed()
        mock_compliance = AsyncMock()
        mock_compliance.check_opt_in = AsyncMock(return_value=allowed)
        mock_compliance.check_frequency_cap = AsyncMock(return_value=allowed)
        mock_compliance.check_unsubscribe = AsyncMock(return_value=allowed)

        mock_adapter = AsyncMock()
        mock_adapter.send.return_value = MagicMock(success=False, error_code="SMTP_REJECT", error_detail="Mailbox full")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
            patch("corpmind.modules.compliance.service.ComplianceService", return_value=mock_compliance),
            patch("corpmind.workers.tasks.outreach._get_adapter", return_value=mock_adapter),
            patch("corpmind.modules.outreach.service.recipient_hmac", return_value="rhash"),
            patch("corpmind.modules.outreach.service._content_hash", return_value="chash"),
        ):
            with pytest.raises(RuntimeError, match="SMTP_REJECT"):
                await _run_send(**_ids())

        mock_repo.update_status.assert_called_with(ANY, "failed")

    async def test_tenant_context_cleared_on_exception(self):
        mock_engine, mock_factory, _ = _db_mocks()
        mock_repo = AsyncMock()
        mock_repo.find_by_id.side_effect = RuntimeError("connection lost")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="mytoken"),
            patch("corpmind.core.tenancy.clear_tenant_context") as mock_clear,
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo", return_value=mock_repo),
        ):
            with pytest.raises(RuntimeError):
                await _run_send(**_ids())

        mock_clear.assert_called_once_with("mytoken")
