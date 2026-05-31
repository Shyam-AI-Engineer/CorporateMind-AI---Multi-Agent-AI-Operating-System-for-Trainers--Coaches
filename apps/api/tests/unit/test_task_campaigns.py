"""Unit tests for workers/tasks/campaigns.py — launch_campaign task."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded

from corpmind.workers.tasks.campaigns import _run_launch, launch_campaign


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ids():
    return {
        "campaign_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "channel": "email",
        "request_id": "req-test-123",
    }


def _db_mocks(mock_session=None):
    """Return (mock_engine, mock_factory, mock_session) with session context manager wired."""
    if mock_session is None:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()
    return mock_engine, mock_factory, mock_session


# ── Sync wrapper tests ─────────────────────────────────────────────────────────
# For bind=True tasks, .run() passes the task instance as self automatically.
# Patch retry on the task object itself to intercept retry calls.

class TestLaunchCampaignSyncWrapper:
    def test_soft_timeout_retries_with_countdown(self):
        with patch.object(launch_campaign, "retry", side_effect=Retry()) as mock_retry:
            with patch("asyncio.run", side_effect=SoftTimeLimitExceeded()):
                with pytest.raises(Retry):
                    launch_campaign.run(**_ids())
        mock_retry.assert_called_once_with(countdown=30)

    def test_generic_exception_retries_with_exc(self):
        err = RuntimeError("db gone")
        with patch.object(launch_campaign, "retry", side_effect=Retry()) as mock_retry:
            with patch("asyncio.run", side_effect=err):
                with pytest.raises(Retry):
                    launch_campaign.run(**_ids())
        mock_retry.assert_called_once_with(exc=err)

    def test_success_returns_result(self):
        expected = {"status": "completed", "sent": 5, "blocked": 0, "failed": 0}
        with patch("asyncio.run", return_value=expected):
            result = launch_campaign.run(**_ids())
        assert result == expected


# ── Async body: _run_launch ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRunLaunch:
    async def test_campaign_not_found_returns_skipped(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = None

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
        ):
            ids = _ids()
            result = await _run_launch(**ids)

        assert result["status"] == "skipped"
        assert result["campaign_id"] == ids["campaign_id"]

    async def test_campaign_wrong_status_returns_skipped(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="paused")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
        ):
            result = await _run_launch(**_ids())

        assert result["status"] == "skipped"

    async def test_no_recipients_completes_with_zeros(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="running")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign
        mock_r_repo = AsyncMock()
        mock_r_repo.list_by_campaign.return_value = []

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
            patch("corpmind.modules.campaigns.repo.CampaignRecipientRepo", return_value=mock_r_repo),
            patch("corpmind.modules.outreach.service.OutreachService"),
        ):
            result = await _run_launch(**_ids())

        assert result["status"] == "completed"
        assert result["sent"] == 0
        assert result["blocked"] == 0
        assert result["failed"] == 0
        mock_c_repo.update_status.assert_called_once()

    async def test_recipient_sent_successfully(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="running")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign

        recipient = MagicMock(id=uuid.uuid4(), contact_id=uuid.uuid4())
        mock_r_repo = AsyncMock()
        mock_r_repo.list_by_campaign.side_effect = [[recipient], []]

        outbound = MagicMock(id=uuid.uuid4())
        send_resp = MagicMock(status="sent")
        mock_outreach = AsyncMock()
        mock_outreach.generate_message.return_value = outbound
        mock_outreach.send_message.return_value = send_resp

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
            patch("corpmind.modules.campaigns.repo.CampaignRecipientRepo", return_value=mock_r_repo),
            patch("corpmind.modules.outreach.service.OutreachService", return_value=mock_outreach),
        ):
            result = await _run_launch(**_ids())

        assert result["sent"] == 1
        assert result["blocked"] == 0
        assert result["failed"] == 0

    async def test_send_blocked_response_counted_as_blocked(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="running")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign

        recipient = MagicMock(id=uuid.uuid4(), contact_id=uuid.uuid4())
        mock_r_repo = AsyncMock()
        mock_r_repo.list_by_campaign.side_effect = [[recipient], []]

        outbound = MagicMock(id=uuid.uuid4())
        send_resp = MagicMock(status="blocked")
        mock_outreach = AsyncMock()
        mock_outreach.generate_message.return_value = outbound
        mock_outreach.send_message.return_value = send_resp

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
            patch("corpmind.modules.campaigns.repo.CampaignRecipientRepo", return_value=mock_r_repo),
            patch("corpmind.modules.outreach.service.OutreachService", return_value=mock_outreach),
        ):
            result = await _run_launch(**_ids())

        assert result["blocked"] == 1
        assert result["sent"] == 0
        mock_r_repo.update_recipient.assert_called_with(recipient.id, status="blocked")

    async def test_compliance_exception_marks_recipient_blocked(self):
        from corpmind.core.exceptions import ComplianceBlockError

        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="running")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign

        recipient = MagicMock(id=uuid.uuid4(), contact_id=uuid.uuid4())
        mock_r_repo = AsyncMock()
        mock_r_repo.list_by_campaign.side_effect = [[recipient], []]

        mock_outreach = AsyncMock()
        mock_outreach.generate_message.side_effect = ComplianceBlockError("unsubscribed")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
            patch("corpmind.modules.campaigns.repo.CampaignRecipientRepo", return_value=mock_r_repo),
            patch("corpmind.modules.outreach.service.OutreachService", return_value=mock_outreach),
        ):
            result = await _run_launch(**_ids())

        assert result["blocked"] == 1
        assert result["failed"] == 0

    async def test_generic_generation_exception_marks_recipient_failed(self):
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_campaign = MagicMock(status="running")
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.return_value = mock_campaign

        recipient = MagicMock(id=uuid.uuid4(), contact_id=uuid.uuid4())
        mock_r_repo = AsyncMock()
        mock_r_repo.list_by_campaign.side_effect = [[recipient], []]

        mock_outreach = AsyncMock()
        mock_outreach.generate_message.side_effect = RuntimeError("LLM timeout")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok"),
            patch("corpmind.core.tenancy.clear_tenant_context"),
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
            patch("corpmind.modules.campaigns.repo.CampaignRecipientRepo", return_value=mock_r_repo),
            patch("corpmind.modules.outreach.service.OutreachService", return_value=mock_outreach),
        ):
            result = await _run_launch(**_ids())

        assert result["failed"] == 1
        assert result["blocked"] == 0
        mock_r_repo.update_recipient.assert_called_with(recipient.id, status="failed")

    async def test_tenant_context_always_cleared(self):
        """clear_tenant_context is called even when an exception escapes."""
        mock_engine, mock_factory, mock_session = _db_mocks()
        mock_c_repo = AsyncMock()
        mock_c_repo.find_by_id.side_effect = RuntimeError("db exploded")

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
            patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock),
            patch("corpmind.core.tenancy.set_tenant_context", return_value="tok") as mock_set,
            patch("corpmind.core.tenancy.clear_tenant_context") as mock_clear,
            patch("corpmind.modules.campaigns.repo.CampaignRepo", return_value=mock_c_repo),
        ):
            with pytest.raises(RuntimeError):
                await _run_launch(**_ids())

        mock_clear.assert_called_once_with("tok")
