"""Unit tests for WhatsApp inbound message idempotency (Sprint 17A).

Tests the two-layer dedup strategy:
  Layer 1 — Redis NX lock (wa:inbound:{provider_message_id}, 24h TTL, fail-open)
  Layer 2 — DB unique constraint (connection_id, provider_message_id) via
             InboxService.create_if_not_exists() ON CONFLICT DO NOTHING

The Celery task _persist_wa_inbound() is tested by patching its async
dependencies so no real DB, Redis, or network is needed.

Covers:
  Redis guard
    - first call sets key and allows processing
    - second call sees existing key and returns "duplicate" immediately
    - Redis connection error → fail-open (processing continues)
    - Redis returns False (key exists) → duplicate skip
  DB backstop
    - when Redis is down and create_if_not_exists returns False → duplicate
    - when both Redis and DB succeed → status "created"
  Tenant resolution
    - no context_id + unknown phone → "skipped" with reason "unknown_phone" (Sprint 17B)
    - context_id not in outbound_messages → "skipped" with reason "outbound_not_found"
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.workers.tasks.whatsapp_inbox import _persist_wa_inbound


PROVIDER_MSG_ID = "wamid.inbound.TEST001"
CONTEXT_ID = "wamid.outbound.ORIG001"
TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
OUTBOUND_ID = uuid.uuid4()


def _base_kwargs(**overrides) -> dict:
    return {
        "provider_message_id": PROVIDER_MSG_ID,
        "from_address": "+919876543210",
        "text_body": "Yes, I'm interested!",
        "context_id": CONTEXT_ID,
        "contact_name": "Ravi Kumar",
        "timestamp": "1750000000",
        "request_id": str(uuid.uuid4()),
        "task_key": f"wa:inbound:{PROVIDER_MSG_ID}",
        **overrides,
    }


def _mock_redis(*, was_new: bool = True, raises: Exception | None = None):
    """Build a minimal Redis mock for the NX set call."""
    r = MagicMock()
    if raises:
        r.set.side_effect = raises
    else:
        r.set.return_value = was_new  # True = new key, False = already exists
    r.close = MagicMock()
    return r


def _mock_outbound_row():
    """Simulate a row returned by the cross-tenant outbound lookup."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: [OUTBOUND_ID, TENANT_ID, WORKSPACE_ID][i]
    return row


async def _mock_execute_with_outbound(stmt, params=None):
    result = MagicMock()
    result.one_or_none.return_value = _mock_outbound_row()
    return result


# ── Redis NX guard ────────────────────────────────────────────────────────────

class TestRedisNxGuard:
    @pytest.mark.asyncio
    async def test_first_call_allows_processing(self):
        """was_new=True → not a duplicate → processing continues past Redis."""
        mock_r = _mock_redis(was_new=True)
        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
            patch("corpmind.workers.tasks.whatsapp_inbox.set_rls_tenant", AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.set_tenant_context", return_value=object()),
            patch("corpmind.workers.tasks.whatsapp_inbox.clear_tenant_context"),
            patch("corpmind.workers.tasks.whatsapp_inbox.InboxService") as mock_svc_cls,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_mock_execute_with_outbound)
            mock_factory.return_value.return_value = mock_session

            svc_instance = MagicMock()
            svc_instance.get_or_create_wa_connection = AsyncMock(return_value=uuid.uuid4())
            svc_instance.create_if_not_exists = AsyncMock(return_value=(True, MagicMock()))
            mock_svc_cls.return_value = svc_instance

            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_second_call_returns_duplicate_immediately(self):
        """was_new=False (key already exists) → skip without any DB access."""
        mock_r = _mock_redis(was_new=False)
        with patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r):
            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "duplicate"
        assert result["provider_message_id"] == PROVIDER_MSG_ID

    @pytest.mark.asyncio
    async def test_redis_connection_error_fails_open(self):
        """Redis outage → fail-open, processing continues to DB."""
        mock_r = _mock_redis(raises=ConnectionError("Redis down"))
        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
            patch("corpmind.workers.tasks.whatsapp_inbox.set_rls_tenant", AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.set_tenant_context", return_value=object()),
            patch("corpmind.workers.tasks.whatsapp_inbox.clear_tenant_context"),
            patch("corpmind.workers.tasks.whatsapp_inbox.InboxService") as mock_svc_cls,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_mock_execute_with_outbound)
            mock_factory.return_value.return_value = mock_session

            svc_instance = MagicMock()
            svc_instance.get_or_create_wa_connection = AsyncMock(return_value=uuid.uuid4())
            svc_instance.create_if_not_exists = AsyncMock(return_value=(True, MagicMock()))
            mock_svc_cls.return_value = svc_instance

            # Should not raise; should continue processing
            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "created"


# ── DB backstop ───────────────────────────────────────────────────────────────

class TestDbBackstop:
    @pytest.mark.asyncio
    async def test_db_duplicate_when_redis_down_returns_duplicate(self):
        """Redis down (fail-open) + create_if_not_exists returns False → duplicate."""
        mock_r = _mock_redis(raises=ConnectionError("Redis down"))
        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
            patch("corpmind.workers.tasks.whatsapp_inbox.set_rls_tenant", AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.set_tenant_context", return_value=object()),
            patch("corpmind.workers.tasks.whatsapp_inbox.clear_tenant_context"),
            patch("corpmind.workers.tasks.whatsapp_inbox.InboxService") as mock_svc_cls,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_mock_execute_with_outbound)
            mock_factory.return_value.return_value = mock_session

            svc_instance = MagicMock()
            svc_instance.get_or_create_wa_connection = AsyncMock(return_value=uuid.uuid4())
            # ON CONFLICT DO NOTHING fired — row already exists
            svc_instance.create_if_not_exists = AsyncMock(return_value=(False, MagicMock()))
            mock_svc_cls.return_value = svc_instance

            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "duplicate"


# ── Tenant resolution ─────────────────────────────────────────────────────────

class TestTenantResolution:
    @pytest.mark.asyncio
    async def test_no_context_id_unknown_phone_returns_skipped(self):
        """context_id=None triggers phone lookup; unknown phone → skipped/unknown_phone."""
        mock_r = _mock_redis(was_new=True)

        async def _empty_contacts(stmt, params=None):
            res = MagicMock()
            res.all.return_value = []  # no matching hr_contacts row
            return res

        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_empty_contacts)
            mock_factory.return_value.return_value = mock_session

            result = await _persist_wa_inbound(**_base_kwargs(context_id=None))

        assert result["status"] == "skipped"
        assert result["reason"] == "unknown_phone"

    @pytest.mark.asyncio
    async def test_unknown_context_id_returns_skipped(self):
        """context.id not found in outbound_messages → skip."""
        mock_r = _mock_redis(was_new=True)

        async def _empty_execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = None  # not found
            return result

        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_empty_execute)
            mock_factory.return_value.return_value = mock_session

            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "skipped"
        assert result["reason"] == "outbound_not_found"
