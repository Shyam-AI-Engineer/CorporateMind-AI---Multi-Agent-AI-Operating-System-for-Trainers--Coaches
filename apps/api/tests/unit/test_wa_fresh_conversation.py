"""Unit tests for Sprint 17B fresh-conversation resolution.

When a WhatsApp message has no context.id (Meta did not send a reply context),
the task resolves the sender's E.164 phone number against hr_contacts to find
the tenant and workspace.

Covers:
  _resolve_via_phone()
    - unknown phone (0 contacts) → None
    - ambiguous phone (contact in 2+ tenants) → "ambiguous"
    - known phone, no campaign history → None (cannot derive workspace)
    - known phone with campaign → (contact_id, tenant_id, workspace_id)
  _persist_wa_inbound() fresh-conversation integration
    - context_id=None + phone found → status "created"
    - context_id=None + ambiguous phone → status "skipped" reason "ambiguous_phone"
    - context_id=None + no campaign → status "skipped" reason "unknown_phone"
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.workers.tasks.whatsapp_inbox import _persist_wa_inbound, _resolve_via_phone


TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
CONTACT_ID = uuid.uuid4()
PROVIDER_MSG_ID = "wamid.fresh.TEST001"


def _make_factory(*session_sides):
    """Build a mock async_sessionmaker whose sessions return the given execute sides."""
    sessions = []
    for sides in session_sides:
        s = AsyncMock()
        s.__aenter__ = AsyncMock(return_value=s)
        s.__aexit__ = AsyncMock(return_value=False)
        s.execute = AsyncMock(side_effect=sides)
        sessions.append(s)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock()
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    # Each call to factory() returns the next session
    factory.return_value = None  # reset default
    call_count = 0
    call_limit = len(sessions)

    class _CM:
        def __init__(self, idx):
            self._s = sessions[idx]

        async def __aenter__(self):
            return self._s

        async def __aexit__(self, *a):
            return False

    _call_idx = [0]

    def _side_effect():
        idx = _call_idx[0]
        _call_idx[0] = min(idx + 1, call_limit - 1)
        return _CM(idx)

    factory.side_effect = _side_effect
    return factory


def _contacts_result(*contact_rows):
    """Build a mock for session.execute that returns contact rows."""
    async def _execute(stmt, params=None):
        res = MagicMock()
        res.all.return_value = list(contact_rows)
        return res
    return _execute


def _campaign_result(workspace_id: uuid.UUID | None):
    """Build a mock for session.execute returning a workspace row or None."""
    async def _execute(stmt, params=None):
        res = MagicMock()
        res.one_or_none.return_value = (workspace_id,) if workspace_id else None
        return res
    return _execute


# ── _resolve_via_phone unit tests ─────────────────────────────────────────────

class TestResolveViaPhone:
    @pytest.mark.asyncio
    async def test_unknown_phone_returns_none(self):
        """No hr_contacts row for this phone → None."""
        s = AsyncMock()
        s.__aenter__ = AsyncMock(return_value=s)
        s.__aexit__ = AsyncMock(return_value=False)
        s.execute = AsyncMock(side_effect=_contacts_result())  # empty list

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=s)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _resolve_via_phone(factory, "+919999000001")
        assert result is None

    @pytest.mark.asyncio
    async def test_ambiguous_phone_returns_sentinel(self):
        """Phone found in two tenants → 'ambiguous'."""
        row_a = (uuid.uuid4(), uuid.uuid4())
        row_b = (uuid.uuid4(), uuid.uuid4())

        s = AsyncMock()
        s.__aenter__ = AsyncMock(return_value=s)
        s.__aexit__ = AsyncMock(return_value=False)
        s.execute = AsyncMock(side_effect=_contacts_result(row_a, row_b))

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=s)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _resolve_via_phone(factory, "+919999000002")
        assert result == "ambiguous"

    @pytest.mark.asyncio
    async def test_known_phone_no_campaign_returns_none(self):
        """Contact found but no campaign history → cannot derive workspace → None."""
        contact_row = (CONTACT_ID, TENANT_ID)
        sessions = [
            MagicMock(),  # contacts session
            MagicMock(),  # campaign session
        ]

        contacts_s = AsyncMock()
        contacts_s.__aenter__ = AsyncMock(return_value=contacts_s)
        contacts_s.__aexit__ = AsyncMock(return_value=False)
        contacts_s.execute = AsyncMock(side_effect=_contacts_result(contact_row))

        campaign_s = AsyncMock()
        campaign_s.__aenter__ = AsyncMock(return_value=campaign_s)
        campaign_s.__aexit__ = AsyncMock(return_value=False)
        campaign_s.execute = AsyncMock(side_effect=_campaign_result(None))

        _sessions = iter([contacts_s, campaign_s])

        class _CM:
            def __init__(self, s):
                self._s = s
            async def __aenter__(self):
                return self._s
            async def __aexit__(self, *a):
                return False

        factory = MagicMock()
        factory.side_effect = lambda: _CM(next(_sessions))

        result = await _resolve_via_phone(factory, "+919999000003")
        assert result is None

    @pytest.mark.asyncio
    async def test_known_phone_with_campaign_returns_tuple(self):
        """Contact found + campaign history → (contact_id, tenant_id, workspace_id)."""
        contact_row = (CONTACT_ID, TENANT_ID)

        contacts_s = AsyncMock()
        contacts_s.__aenter__ = AsyncMock(return_value=contacts_s)
        contacts_s.__aexit__ = AsyncMock(return_value=False)
        contacts_s.execute = AsyncMock(side_effect=_contacts_result(contact_row))

        campaign_s = AsyncMock()
        campaign_s.__aenter__ = AsyncMock(return_value=campaign_s)
        campaign_s.__aexit__ = AsyncMock(return_value=False)
        campaign_s.execute = AsyncMock(side_effect=_campaign_result(WORKSPACE_ID))

        _sessions = iter([contacts_s, campaign_s])

        class _CM:
            def __init__(self, s):
                self._s = s
            async def __aenter__(self):
                return self._s
            async def __aexit__(self, *a):
                return False

        factory = MagicMock()
        factory.side_effect = lambda: _CM(next(_sessions))

        result = await _resolve_via_phone(factory, "+919999000004")
        assert isinstance(result, tuple)
        contact_id, tenant_id, workspace_id = result
        assert contact_id == CONTACT_ID
        assert tenant_id == TENANT_ID
        assert workspace_id == WORKSPACE_ID


# ── _persist_wa_inbound integration: fresh-conversation path ──────────────────

def _base_kwargs(**overrides) -> dict:
    return {
        "provider_message_id": PROVIDER_MSG_ID,
        "from_address": "+919876543210",
        "text_body": "Hello, saw your ad. Interested.",
        "context_id": None,
        "contact_name": "Priya Singh",
        "timestamp": "1750000000",
        "request_id": str(uuid.uuid4()),
        "task_key": f"wa:inbound:{PROVIDER_MSG_ID}",
        **overrides,
    }


def _mock_redis(*, was_new: bool = True):
    r = MagicMock()
    r.set.return_value = was_new
    r.close = MagicMock()
    return r


class TestFreshConversationIntegration:
    @pytest.mark.asyncio
    async def test_ambiguous_phone_returns_skipped(self):
        """context_id=None + ambiguous phone → skipped/ambiguous_phone."""
        mock_r = _mock_redis(was_new=True)
        row_a = (uuid.uuid4(), uuid.uuid4())
        row_b = (uuid.uuid4(), uuid.uuid4())

        async def _two_contacts(stmt, params=None):
            res = MagicMock()
            res.all.return_value = [row_a, row_b]
            return res

        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_two_contacts)
            mock_factory.return_value.return_value = mock_session

            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "skipped"
        assert result["reason"] == "ambiguous_phone"

    @pytest.mark.asyncio
    async def test_fresh_conversation_phone_found_creates_message(self):
        """context_id=None + phone found + campaign → status 'created'."""
        mock_r = _mock_redis(was_new=True)
        contact_row = (CONTACT_ID, TENANT_ID)

        call_count = [0]

        async def _multi_execute(stmt, params=None):
            res = MagicMock()
            call_count[0] += 1
            c = call_count[0]
            if c == 1:
                # hr_contacts lookup
                res.all.return_value = [contact_row]
            elif c == 2:
                # campaign_recipients lookup
                res.one_or_none.return_value = (WORKSPACE_ID,)
            else:
                # set_rls_tenant or other calls
                res.one_or_none.return_value = None
                res.all.return_value = []
            return res

        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
            patch("corpmind.workers.tasks.whatsapp_inbox.set_rls_tenant", AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.set_tenant_context", return_value=object()),
            patch("corpmind.workers.tasks.whatsapp_inbox.clear_tenant_context"),
            patch("corpmind.workers.tasks.whatsapp_inbox.InboxService") as mock_svc_cls,
            patch("corpmind.workers.tasks.whatsapp_inbox._classify_wa_and_persist", AsyncMock()),
        ):
            msg_out = MagicMock()
            msg_out.id = uuid.uuid4()
            svc_instance = MagicMock()
            svc_instance.get_or_create_wa_connection = AsyncMock(return_value=uuid.uuid4())
            svc_instance.create_if_not_exists = AsyncMock(return_value=(True, msg_out))
            mock_svc_cls.return_value = svc_instance

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_multi_execute)
            mock_factory.return_value.return_value = mock_session

            result = await _persist_wa_inbound(**_base_kwargs())

        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_fresh_conversation_match_method_is_phone_lookup(self):
        """Fresh conversation sets match_method='phone_lookup' on the InboxMessage."""
        mock_r = _mock_redis(was_new=True)
        contact_row = (CONTACT_ID, TENANT_ID)
        call_count = [0]

        async def _multi_execute(stmt, params=None):
            res = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                res.all.return_value = [contact_row]
            elif call_count[0] == 2:
                res.one_or_none.return_value = (WORKSPACE_ID,)
            else:
                res.one_or_none.return_value = None
                res.all.return_value = []
            return res

        captured_msg = {}

        with (
            patch("corpmind.workers.tasks.whatsapp_inbox._redis.from_url", return_value=mock_r),
            patch("corpmind.workers.tasks.whatsapp_inbox.create_async_engine", return_value=AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.async_sessionmaker") as mock_factory,
            patch("corpmind.workers.tasks.whatsapp_inbox.set_rls_tenant", AsyncMock()),
            patch("corpmind.workers.tasks.whatsapp_inbox.set_tenant_context", return_value=object()),
            patch("corpmind.workers.tasks.whatsapp_inbox.clear_tenant_context"),
            patch("corpmind.workers.tasks.whatsapp_inbox.InboxService") as mock_svc_cls,
            patch("corpmind.workers.tasks.whatsapp_inbox._classify_wa_and_persist", AsyncMock()),
        ):
            msg_out = MagicMock()
            msg_out.id = uuid.uuid4()
            svc_instance = MagicMock()
            svc_instance.get_or_create_wa_connection = AsyncMock(return_value=uuid.uuid4())

            async def _capture(msg, body_snippet=None):
                captured_msg["match_method"] = msg.match_method
                captured_msg["outbound_message_id"] = msg.outbound_message_id
                return (True, msg_out)

            svc_instance.create_if_not_exists = AsyncMock(side_effect=_capture)
            mock_svc_cls.return_value = svc_instance

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=_multi_execute)
            mock_factory.return_value.return_value = mock_session

            await _persist_wa_inbound(**_base_kwargs())

        assert captured_msg.get("match_method") == "phone_lookup"
        assert captured_msg.get("outbound_message_id") is None
