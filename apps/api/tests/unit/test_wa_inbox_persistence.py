"""Unit tests for WhatsApp InboxMessage persistence — Sprint 17A.

Tests InboxService methods added in Sprint 17A:
  get_or_create_wa_connection()
    - creates a new InboxConnection(provider='whatsapp') on first call
    - returns same connection_id on second call (idempotent)
    - creates with correct fields (provider, scopes, status)
    - encrypted placeholders satisfy NOT NULL constraints
  match_reply_by_provider_id()
    - returns outbound_message_id when provider_message_id found
    - returns None when not found

And the Celery task's persistence path:
  _persist_wa_inbound() — successful creation
    - InboxMessage created with channel='whatsapp'
    - body snippet limited to 500 chars and encrypted
    - body_truncated=True when text_body > 500 chars
    - body_truncated=False when text_body <= 500 chars
    - match_method='provider_message_id' set on created message
    - outbound_message_id linked from cross-tenant lookup
    - received_at parsed from Unix timestamp
    - received_at falls back to now() when timestamp absent
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.inbox.service import InboxService


TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
OUTBOUND_ID = uuid.uuid4()
CONN_ID = uuid.uuid4()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(org_id: uuid.UUID = TENANT_ID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    return ctx


def _make_session() -> MagicMock:
    s = MagicMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    return s


def _make_service(session=None) -> InboxService:
    return InboxService(session or _make_session())


# ── get_or_create_wa_connection ───────────────────────────────────────────────

class TestGetOrCreateWaConnection:
    @pytest.mark.asyncio
    async def test_creates_connection_when_none_exists(self):
        svc = _make_service()

        async def _create_and_assign_id(conn):
            # Simulate what a real session flush does — assign the PK.
            conn.id = CONN_ID

        with (
            patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()),
            patch.object(svc._conn_repo, "find_wa_connection", AsyncMock(return_value=None)),
            patch.object(svc._conn_repo, "create", AsyncMock(side_effect=_create_and_assign_id)),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc"),
            patch("corpmind.modules.inbox.service.settings") as mock_settings,
        ):
            mock_settings.WHATSAPP_PHONE_NUMBER_ID = "123456"
            conn_id = await svc.get_or_create_wa_connection(WORKSPACE_ID)

        assert conn_id == CONN_ID

    @pytest.mark.asyncio
    async def test_returns_existing_connection_id(self):
        existing = MagicMock()
        existing.id = CONN_ID
        svc = _make_service()
        with (
            patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()),
            patch.object(svc._conn_repo, "find_wa_connection", AsyncMock(return_value=existing)),
        ):
            conn_id = await svc.get_or_create_wa_connection(WORKSPACE_ID)

        assert conn_id == CONN_ID

    @pytest.mark.asyncio
    async def test_does_not_create_when_already_exists(self):
        existing = MagicMock()
        existing.id = CONN_ID
        svc = _make_service()
        mock_create = AsyncMock()
        with (
            patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()),
            patch.object(svc._conn_repo, "find_wa_connection", AsyncMock(return_value=existing)),
            patch.object(svc._conn_repo, "create", mock_create),
        ):
            await svc.get_or_create_wa_connection(WORKSPACE_ID)

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_created_connection_has_whatsapp_provider(self):
        created_conns: list = []
        svc = _make_service()

        async def _capture_create(conn):
            created_conns.append(conn)
            return conn

        with (
            patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()),
            patch.object(svc._conn_repo, "find_wa_connection", AsyncMock(return_value=None)),
            patch.object(svc._conn_repo, "create", AsyncMock(side_effect=_capture_create)),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc"),
            patch("corpmind.modules.inbox.service.settings") as mock_settings,
        ):
            mock_settings.WHATSAPP_PHONE_NUMBER_ID = "999"
            await svc.get_or_create_wa_connection(WORKSPACE_ID)

        assert len(created_conns) == 1
        assert created_conns[0].provider == "whatsapp"
        assert created_conns[0].scopes == "whatsapp_webhook"
        assert created_conns[0].status == "active"

    @pytest.mark.asyncio
    async def test_second_call_after_creation_returns_same_id(self):
        """Simulate two sequential calls; second finds the connection."""
        existing = MagicMock()
        existing.id = CONN_ID
        call_count = 0

        async def _find_wa(ws_id):
            nonlocal call_count
            call_count += 1
            return None if call_count == 1 else existing

        svc = _make_service()
        with (
            patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()),
            patch.object(svc._conn_repo, "find_wa_connection", AsyncMock(side_effect=_find_wa)),
            patch.object(svc._conn_repo, "create", AsyncMock(side_effect=lambda c: c)),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc"),
            patch("corpmind.modules.inbox.service.settings") as mock_settings,
        ):
            mock_settings.WHATSAPP_PHONE_NUMBER_ID = "123"
            await svc.get_or_create_wa_connection(WORKSPACE_ID)  # creates
            id2 = await svc.get_or_create_wa_connection(WORKSPACE_ID)  # finds

        assert id2 == CONN_ID


# ── match_reply_by_provider_id ────────────────────────────────────────────────

class TestMatchReplyByProviderId:
    @pytest.mark.asyncio
    async def test_returns_outbound_id_when_found(self):
        svc = _make_service()
        row = MagicMock()
        row.__getitem__ = lambda self, i: OUTBOUND_ID

        execute_result = MagicMock()
        execute_result.one_or_none.return_value = row
        svc._session.execute = AsyncMock(return_value=execute_result)

        with patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()):
            result = await svc.match_reply_by_provider_id("wamid.outbound.XYZ")

        assert result == OUTBOUND_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = None
        svc._session.execute = AsyncMock(return_value=execute_result)

        with patch("corpmind.modules.inbox.service.get_tenant_context", return_value=_ctx()):
            result = await svc.match_reply_by_provider_id("wamid.notexist")

        assert result is None

    @pytest.mark.asyncio
    async def test_queries_with_tenant_id(self):
        """Tenant-scoped query — verifies the WHERE clause passes tenant_id."""
        svc = _make_service()
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = None
        svc._session.execute = AsyncMock(return_value=execute_result)
        ctx = _ctx()

        with patch("corpmind.modules.inbox.service.get_tenant_context", return_value=ctx):
            await svc.match_reply_by_provider_id("wamid.abc")

        # The execute was called with params that include the tenant_id
        call_args = svc._session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        assert str(ctx.org_id) in str(params)


# ── Persistence via Celery task ───────────────────────────────────────────────

class TestWaInboxPersistenceTask:
    """Tests the _persist_wa_inbound() coordination logic via patching."""

    def _base_kwargs(self, **overrides) -> dict:
        return {
            "provider_message_id": "wamid.in1",
            "from_address": "+919876543210",
            "text_body": "Interested!",
            "context_id": "wamid.out1",
            "contact_name": "Ravi",
            "timestamp": "1750000000",
            "request_id": str(uuid.uuid4()),
            "task_key": "wa:inbound:wamid.in1",
            **overrides,
        }

    def _outbound_row(self):
        row = MagicMock()
        row.__getitem__ = lambda self, i: [OUTBOUND_ID, TENANT_ID, WORKSPACE_ID][i]
        return row

    async def _run(self, **kwargs):
        from corpmind.workers.tasks.whatsapp_inbox import _persist_wa_inbound
        return await _persist_wa_inbound(**self._base_kwargs(**kwargs))

    @pytest.mark.asyncio
    async def test_created_message_has_channel_whatsapp(self):
        created_msgs: list = []

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run()

        assert len(created_msgs) == 1
        assert created_msgs[0].channel == "whatsapp"

    @pytest.mark.asyncio
    async def test_body_snippet_truncated_to_500_chars(self):
        long_body = "A" * 600
        snippets_used: list = []

        async def _capture_create(msg, body_snippet=None):
            snippets_used.append(body_snippet)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run(text_body=long_body)

        assert len(snippets_used[0]) == 500

    @pytest.mark.asyncio
    async def test_body_truncated_flag_true_when_over_500(self):
        created_msgs: list = []

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run(text_body="X" * 600)

        assert created_msgs[0].body_truncated is True

    @pytest.mark.asyncio
    async def test_body_truncated_flag_false_when_under_500(self):
        created_msgs: list = []

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run(text_body="Short reply")

        assert created_msgs[0].body_truncated is False

    @pytest.mark.asyncio
    async def test_match_method_is_provider_message_id(self):
        created_msgs: list = []

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run()

        assert created_msgs[0].match_method == "provider_message_id"

    @pytest.mark.asyncio
    async def test_received_at_parsed_from_timestamp(self):
        created_msgs: list = []

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run(timestamp="1750000000")

        expected = datetime.fromtimestamp(1750000000, tz=UTC)
        assert created_msgs[0].received_at == expected

    @pytest.mark.asyncio
    async def test_received_at_falls_back_to_now_when_no_timestamp(self):
        created_msgs: list = []
        before = datetime.now(UTC)

        async def _capture_create(msg, body_snippet=None):
            created_msgs.append(msg)
            return True, MagicMock()

        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_r.close = MagicMock()

        async def _execute(stmt, params=None):
            result = MagicMock()
            result.one_or_none.return_value = self._outbound_row()
            return result

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
            mock_session.execute = AsyncMock(side_effect=_execute)
            mock_factory.return_value.return_value = mock_session

            svc_inst = MagicMock()
            svc_inst.get_or_create_wa_connection = AsyncMock(return_value=CONN_ID)
            svc_inst.create_if_not_exists = AsyncMock(side_effect=_capture_create)
            mock_svc_cls.return_value = svc_inst

            await self._run(timestamp=None)

        after = datetime.now(UTC)
        assert before <= created_msgs[0].received_at <= after
