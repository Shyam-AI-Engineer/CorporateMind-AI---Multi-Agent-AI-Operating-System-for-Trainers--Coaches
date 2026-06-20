"""Unit tests for WhatsApp delivery timestamp writing and webhook replay guard.

Covers:
  OutboundMessageRepo.update_status_by_provider_id()
    - 'delivered' status writes delivered_at via COALESCE (first-write-wins)
    - 'opened' status writes read_at via COALESCE
    - 'failed' status writes failed_at via COALESCE
    - 'sent' status updates status column only (no timestamp col)
    - COALESCE pattern confirmed in generated SQL

  WhatsAppCloudAdapter._is_duplicate()
    - unknown event_id → not a duplicate (Redis NX sets the key, returns False)
    - same event_id already in Redis → duplicate (returns True)
    - Redis unavailable → fail-open (returns False)

  WhatsAppCloudAdapter.handle_webhook()
    - duplicate event_id in payload is skipped (not emitted as InboundEvent)
    - non-duplicate event_id is emitted as InboundEvent
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import Headers

from corpmind.channels.whatsapp_cloud import WhatsAppCloudAdapter


# ── Repo: delivered_at / read_at / failed_at first-write-wins ─────────────────

class TestOutboundMessageRepoTimestamps:
    """Verifies SQL emitted by update_status_by_provider_id for each status."""

    def _make_repo(self):
        from corpmind.modules.outreach.repo import OutboundMessageRepo
        session = MagicMock()
        session.execute = AsyncMock()
        return OutboundMessageRepo(session), session

    @pytest.mark.asyncio
    async def test_delivered_writes_delivered_at(self):
        repo, session = self._make_repo()
        await repo.update_status_by_provider_id("wamid.abc", "delivered")
        assert session.execute.called
        sql_text = str(session.execute.call_args[0][0])
        assert "delivered_at" in sql_text
        assert "COALESCE" in sql_text

    @pytest.mark.asyncio
    async def test_opened_writes_read_at(self):
        repo, session = self._make_repo()
        await repo.update_status_by_provider_id("wamid.abc", "opened")
        sql_text = str(session.execute.call_args[0][0])
        assert "read_at" in sql_text
        assert "COALESCE" in sql_text

    @pytest.mark.asyncio
    async def test_failed_writes_failed_at(self):
        repo, session = self._make_repo()
        await repo.update_status_by_provider_id("wamid.abc", "failed")
        sql_text = str(session.execute.call_args[0][0])
        assert "failed_at" in sql_text
        assert "COALESCE" in sql_text

    @pytest.mark.asyncio
    async def test_sent_status_no_coalesce(self):
        """'sent' has no timestamp column — COALESCE must not appear in the SQL."""
        repo, session = self._make_repo()
        await repo.update_status_by_provider_id("wamid.abc", "sent")
        assert session.execute.called
        sql_text = str(session.execute.call_args[0][0])
        assert "COALESCE" not in sql_text

    @pytest.mark.asyncio
    async def test_coalesce_semantics_preserved_in_sql(self):
        """The SQL must use COALESCE(delivered_at, :ts) not just SET col = :ts."""
        repo, session = self._make_repo()
        await repo.update_status_by_provider_id("wamid.xyz", "delivered")
        sql_text = str(session.execute.call_args[0][0])
        assert "COALESCE(delivered_at, :ts)" in sql_text


# ── WhatsApp webhook replay guard ─────────────────────────────────────────────

class TestWebhookReplayGuard:
    def _make_adapter(self):
        return WhatsAppCloudAdapter()

    def _mock_redis_module(self, set_return_value):
        """Return a fake redis module where from_url().set() returns set_return_value."""
        mock_conn = MagicMock()
        mock_conn.set.return_value = set_return_value
        mock_mod = MagicMock()
        mock_mod.from_url.return_value = mock_conn
        return mock_mod

    def test_first_event_not_duplicate(self):
        adapter = self._make_adapter()
        fake_redis = self._mock_redis_module(set_return_value=True)  # NX succeeded

        with patch.dict(sys.modules, {"redis": fake_redis}):
            result = adapter._is_duplicate("event-001")

        assert result is False

    def test_second_call_same_event_is_duplicate(self):
        adapter = self._make_adapter()
        fake_redis = self._mock_redis_module(set_return_value=None)  # NX failed

        with patch.dict(sys.modules, {"redis": fake_redis}):
            result = adapter._is_duplicate("event-001")

        assert result is True

    def test_redis_unavailable_fails_open(self):
        adapter = self._make_adapter()
        fake_redis = MagicMock()
        fake_redis.from_url.side_effect = Exception("Redis down")

        with patch.dict(sys.modules, {"redis": fake_redis}):
            result = adapter._is_duplicate("event-002")

        assert result is False

    def _make_webhook_payload(
        self,
        event_id: str,
        meta_status: str = "delivered",
    ) -> tuple[bytes, Headers]:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": event_id,
                            "recipient_id": "+919876543210",
                            "status": meta_status,
                            "timestamp": "1700000000",
                        }]
                    }
                }]
            }]
        }
        raw = json.dumps(body).encode()
        secret = "test_secret"
        sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return raw, Headers({"x-hub-signature-256": sig})

    def test_handle_webhook_skips_duplicate(self):
        adapter = self._make_adapter()
        raw, headers = self._make_webhook_payload("event-dup")

        with (
            patch.object(adapter, "_verify_hmac", return_value=None),
            patch.object(adapter, "_is_duplicate", return_value=True),
        ):
            events = asyncio.run(adapter.handle_webhook(raw, headers))

        assert events == []

    def test_handle_webhook_emits_non_duplicate(self):
        adapter = self._make_adapter()
        raw, headers = self._make_webhook_payload("event-new")

        with (
            patch.object(adapter, "_verify_hmac", return_value=None),
            patch.object(adapter, "_is_duplicate", return_value=False),
        ):
            events = asyncio.run(adapter.handle_webhook(raw, headers))

        assert len(events) == 1
        assert events[0].provider_event_id == "event-new"
