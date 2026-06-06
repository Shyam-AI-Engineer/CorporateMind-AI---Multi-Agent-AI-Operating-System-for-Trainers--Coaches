"""Unit tests for the inbox sync worker (_run_sync coroutine).

All external dependencies — SQLAlchemy engine/session, Gmail API, OAuth,
encryption, and tenancy — are mocked.  No live DB or network calls are made.

Uses a pytest fixture (base_mocks) with contextlib.ExitStack so that all
infrastructure patches are active for every test without parameter-ordering
confusion from stacked @patch decorators.
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.workers.tasks.inbox import _run_sync

# ── Shared identifiers ─────────────────────────────────────────────────────────

CONN_ID = str(uuid.uuid4())
TENANT_ID = str(uuid.uuid4())
WS_ID = str(uuid.uuid4())
REQUEST_ID = "test-request-001"

CONN_UUID = uuid.UUID(CONN_ID)
TENANT_UUID = uuid.UUID(TENANT_ID)
OUTBOUND_UUID = uuid.uuid4()


# ── Mock object factories ──────────────────────────────────────────────────────

def _make_connection(status: str = "active") -> MagicMock:
    conn = MagicMock()
    conn.id = CONN_UUID
    conn.status = status
    conn.refresh_token_enc = "enc-refresh-token"
    conn.access_token_enc = "enc-access-token"
    conn.token_expiry_at = None
    return conn


def _make_tokens(expires_in: int = 3600) -> MagicMock:
    t = MagicMock()
    t.access_token = "fresh-access-token"
    t.expires_in = expires_in
    t.refresh_token = None
    return t


def _make_summary(msg_id: str = "gmail-msg-1") -> MagicMock:
    s = MagicMock()
    s.message_id = msg_id
    s.thread_id = "thread-1"
    s.snippet = "Hello, following up on your proposal..."
    return s


def _make_detail(
    msg_id: str = "gmail-msg-1",
    in_reply_to: str | None = "<orig@outbound.example.com>",
    references: str | None = None,
    snippet: str | None = "Hello, following up on your proposal...",
) -> MagicMock:
    d = MagicMock()
    d.message_id = msg_id
    d.thread_id = "thread-1"
    d.snippet = snippet
    d.from_address = "hr@company.com"
    d.subject = "Re: Training session"
    d.received_at = datetime.now(UTC)
    d.smtp_message_id = f"<{msg_id}@gmail.example.com>"
    d.in_reply_to = in_reply_to
    d.references_header = references
    return d


def _make_session() -> AsyncMock:
    """Async context manager that yields itself as the DB session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _make_conn_repo(conn: MagicMock | None = None) -> MagicMock:
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=conn if conn is not None else _make_connection())
    repo.update = AsyncMock()
    return repo


def _make_service() -> MagicMock:
    svc = MagicMock()
    svc.match_reply = AsyncMock(return_value=None)
    svc.create_if_not_exists = AsyncMock(return_value=(True, MagicMock()))
    return svc


# ── Shared infrastructure fixture ──────────────────────────────────────────────

@pytest.fixture
def base_mocks():
    """Patch all DB/encryption/tenancy infrastructure for _run_sync().

    Uses ExitStack so patches clean up on fixture teardown with no parameter-
    ordering confusion.  Each test can add further patches via `with patch(...)`
    inside the test body.
    """
    session = _make_session()

    # engine.dispose() is awaited, so it must be AsyncMock.
    engine_instance = MagicMock()
    engine_instance.dispose = AsyncMock()

    factory = MagicMock()
    factory.return_value = session

    with ExitStack() as stack:
        ns = SimpleNamespace(
            engine=stack.enter_context(
                patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine_instance)
            ),
            sessionmaker=stack.enter_context(
                patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=factory)
            ),
            set_rls=stack.enter_context(
                patch("corpmind.core.database.set_rls_tenant", new_callable=AsyncMock)
            ),
            decrypt=stack.enter_context(
                patch("corpmind.core.encryption.decrypt", return_value="plaintext-refresh-token")
            ),
            encrypt=stack.enter_context(
                patch("corpmind.core.encryption.encrypt", return_value="new-encrypted-value")
            ),
            set_ctx=stack.enter_context(
                patch("corpmind.core.tenancy.set_tenant_context", return_value=MagicMock())
            ),
            clear_ctx=stack.enter_context(patch("corpmind.core.tenancy.clear_tenant_context")),
            tenant_ctx=stack.enter_context(patch("corpmind.core.tenancy.TenantContext")),
            session=session,
        )
        yield ns


# ── Helpers for common per-test patches ───────────────────────────────────────

def _gmail_patches(
    *,
    list_return=None,
    get_side_effect=None,
    conn_repo: MagicMock | None = None,
    service: MagicMock | None = None,
):
    """Return a context manager that applies the Gmail + repo/service patches."""
    from contextlib import ExitStack

    list_rv = list_return if list_return is not None else ([], None)
    cr = conn_repo if conn_repo is not None else _make_conn_repo()
    svc = service if service is not None else _make_service()

    stack = ExitStack()
    stack.enter_context(patch("corpmind.modules.inbox.repo.InboxConnectionRepo", return_value=cr))
    stack.enter_context(patch("corpmind.modules.inbox.service.InboxService", return_value=svc))
    stack.enter_context(
        patch(
            "corpmind.modules.inbox.gmail_client.list_inbox_messages",
            new_callable=AsyncMock,
            return_value=list_rv,
        )
    )
    if get_side_effect is not None:
        stack.enter_context(
            patch(
                "corpmind.modules.inbox.gmail_client.get_message",
                new_callable=AsyncMock,
                side_effect=get_side_effect,
            )
        )
    else:
        stack.enter_context(
            patch("corpmind.modules.inbox.gmail_client.get_message", new_callable=AsyncMock)
        )
    return stack, cr, svc


async def _sync(**kwargs) -> dict:
    """Convenience wrapper: call _run_sync with default test IDs."""
    return await _run_sync(
        connection_id=kwargs.get("connection_id", CONN_ID),
        tenant_id=kwargs.get("tenant_id", TENANT_ID),
        workspace_id=kwargs.get("workspace_id", WS_ID),
        request_id=kwargs.get("request_id", REQUEST_ID),
    )


# ── Token refresh tests ────────────────────────────────────────────────────────

class TestTokenRefresh:
    """Refresh token is exchanged for a new access token at the start of sync."""

    @pytest.mark.asyncio
    async def test_refresh_called_before_gmail_fetch(self, base_mocks):
        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ) as mock_refresh:
            with _gmail_patches()[0]:
                result = await _sync()

        mock_refresh.assert_awaited_once_with("plaintext-refresh-token")
        assert result["status"] == "synced"

    @pytest.mark.asyncio
    async def test_new_access_token_encrypted_and_persisted(self, base_mocks):
        conn_repo = _make_conn_repo()

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, cr, _ = _gmail_patches(conn_repo=conn_repo)
            with stack:
                await _sync()

        # encrypt() must have been called with the fresh access token
        base_mocks.encrypt.assert_called_with("fresh-access-token")
        # The first update call (token refresh) must set access_token_enc and status
        first_update = conn_repo.update.call_args_list[0].args[1]
        assert "access_token_enc" in first_update
        assert first_update["status"] == "active"
        assert first_update["last_error"] is None


# ── Revoked account tests ──────────────────────────────────────────────────────

class TestRevokedAccount:
    """Revoked connections must not attempt any OAuth or Gmail calls."""

    @pytest.mark.asyncio
    async def test_already_revoked_skips_immediately(self, base_mocks):
        conn = _make_connection(status="revoked")
        conn_repo = _make_conn_repo(conn=conn)

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            stack, _, _ = _gmail_patches(conn_repo=conn_repo)
            with stack:
                result = await _sync()

        mock_refresh.assert_not_awaited()
        assert result["status"] == "skipped"
        assert result["reason"] == "revoked"

    @pytest.mark.asyncio
    async def test_google_rejection_marks_status_revoked(self, base_mocks):
        from corpmind.core.exceptions import ValidationError

        conn_repo = _make_conn_repo()

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            side_effect=ValidationError("token_revoked"),
        ):
            stack, cr, _ = _gmail_patches(conn_repo=conn_repo)
            with stack:
                result = await _sync()

        assert result["status"] == "revoked"
        update_payload = conn_repo.update.call_args_list[0].args[1]
        assert update_payload["status"] == "revoked"
        assert "re-authorization" in update_payload["last_error"]

    @pytest.mark.asyncio
    async def test_google_rejection_does_not_call_gmail_api(self, base_mocks):
        from corpmind.core.exceptions import ValidationError

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            side_effect=ValidationError("token_revoked"),
        ):
            with patch(
                "corpmind.modules.inbox.gmail_client.list_inbox_messages",
                new_callable=AsyncMock,
            ) as mock_list, patch(
                "corpmind.modules.inbox.repo.InboxConnectionRepo",
                return_value=_make_conn_repo(),
            ), patch(
                "corpmind.modules.inbox.service.InboxService",
                return_value=_make_service(),
            ):
                await _sync()
                mock_list.assert_not_awaited()


# ── Deduplication tests ────────────────────────────────────────────────────────

class TestDeduplication:
    """ON CONFLICT DO NOTHING means duplicate provider_message_ids are skipped."""

    @pytest.mark.asyncio
    async def test_duplicate_messages_counted_separately(self, base_mocks):
        service = _make_service()
        # First message: new; second: already exists
        service.create_if_not_exists = AsyncMock(
            side_effect=[(True, MagicMock()), (False, MagicMock())]
        )

        summaries = [_make_summary("msg-1"), _make_summary("msg-2")]
        details = {
            "msg-1": _make_detail("msg-1"),
            "msg-2": _make_detail("msg-2"),
        }

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(
                list_return=(summaries, None),
                get_side_effect=lambda token, mid: details[mid],
                service=service,
            )
            with stack:
                result = await _sync()

        assert result["inserted"] == 1
        assert result["duplicates"] == 1
        assert result["status"] == "synced"

    @pytest.mark.asyncio
    async def test_all_duplicates_returns_zero_inserted(self, base_mocks):
        service = _make_service()
        service.create_if_not_exists = AsyncMock(
            side_effect=[(False, MagicMock()), (False, MagicMock())]
        )

        summaries = [_make_summary("msg-1"), _make_summary("msg-2")]
        details = {"msg-1": _make_detail("msg-1"), "msg-2": _make_detail("msg-2")}

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(
                list_return=(summaries, None),
                get_side_effect=lambda token, mid: details[mid],
                service=service,
            )
            with stack:
                result = await _sync()

        assert result["inserted"] == 0
        assert result["duplicates"] == 2


# ── Pagination tests ───────────────────────────────────────────────────────────

class TestPagination:
    """Sync must follow nextPageToken until exhausted or page cap reached."""

    @pytest.mark.asyncio
    async def test_two_pages_both_fetched(self, base_mocks):
        page1 = [_make_summary("msg-p1")]
        page2 = [_make_summary("msg-p2")]
        details = {
            "msg-p1": _make_detail("msg-p1"),
            "msg-p2": _make_detail("msg-p2"),
        }

        async def _list(access_token, *, page_token=None, **_kw):
            if page_token is None:
                return (page1, "next-page-token")
            return (page2, None)

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ), patch(
            "corpmind.modules.inbox.gmail_client.list_inbox_messages",
            new_callable=AsyncMock,
            side_effect=_list,
        ), patch(
            "corpmind.modules.inbox.gmail_client.get_message",
            new_callable=AsyncMock,
            side_effect=lambda token, mid: details[mid],
        ), patch(
            "corpmind.modules.inbox.repo.InboxConnectionRepo",
            return_value=_make_conn_repo(),
        ), patch(
            "corpmind.modules.inbox.service.InboxService",
            return_value=_make_service(),
        ):
            result = await _sync()

        assert result["pages"] == 2
        assert result["inserted"] == 2

    @pytest.mark.asyncio
    async def test_empty_message_list_returns_zero(self, base_mocks):
        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(list_return=([], None))
            with stack:
                result = await _sync()

        assert result["inserted"] == 0
        assert result["duplicates"] == 0
        assert result["pages"] == 1


# ── Reply matching tests ───────────────────────────────────────────────────────

class TestReplyMatching:
    """In-Reply-To header must be matched against outbound smtp_message_id."""

    @pytest.mark.asyncio
    async def test_in_reply_to_match_sets_outbound_id_and_method(self, base_mocks):
        service = _make_service()
        service.match_reply = AsyncMock(return_value=OUTBOUND_UUID)

        detail = _make_detail(in_reply_to="<outbound-smtp@domain.com>")

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(
                list_return=([_make_summary()], None),
                get_side_effect=lambda *_: detail,
                service=service,
            )
            with stack:
                await _sync()

        create_call = service.create_if_not_exists.call_args
        persisted = create_call.args[0]
        assert persisted.outbound_message_id == OUTBOUND_UUID
        assert persisted.match_method == "in_reply_to"

    @pytest.mark.asyncio
    async def test_no_match_leaves_outbound_message_id_none(self, base_mocks):
        service = _make_service()
        service.match_reply = AsyncMock(return_value=None)

        detail = _make_detail(in_reply_to="<unknown@nowhere.example>")

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(
                list_return=([_make_summary()], None),
                get_side_effect=lambda *_: detail,
                service=service,
            )
            with stack:
                await _sync()

        create_call = service.create_if_not_exists.call_args
        persisted = create_call.args[0]
        assert persisted.outbound_message_id is None
        assert persisted.match_method is None

    @pytest.mark.asyncio
    async def test_references_header_used_when_in_reply_to_absent(self, base_mocks):
        service = _make_service()
        service.match_reply = AsyncMock(return_value=OUTBOUND_UUID)

        detail = _make_detail(
            in_reply_to=None,
            references="<earlier@chain.com> <outbound-smtp@domain.com>",
        )

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, _, _ = _gmail_patches(
                list_return=([_make_summary()], None),
                get_side_effect=lambda *_: detail,
                service=service,
            )
            with stack:
                await _sync()

        # match_reply should be called with the LAST References entry
        service.match_reply.assert_awaited_once_with("<outbound-smtp@domain.com>")
        create_call = service.create_if_not_exists.call_args
        persisted = create_call.args[0]
        assert persisted.match_method == "references"


# ── Gmail API failure tests ────────────────────────────────────────────────────

class TestGmailAPIFailures:
    """Transient Gmail errors must propagate so Celery triggers a retry."""

    @pytest.mark.asyncio
    async def test_rate_limit_on_list_propagates(self, base_mocks):
        from corpmind.core.exceptions import ValidationError

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ), patch(
            "corpmind.modules.inbox.gmail_client.list_inbox_messages",
            new_callable=AsyncMock,
            side_effect=ValidationError("Gmail API rate limit exceeded"),
        ), patch(
            "corpmind.modules.inbox.repo.InboxConnectionRepo",
            return_value=_make_conn_repo(),
        ), patch(
            "corpmind.modules.inbox.service.InboxService",
            return_value=_make_service(),
        ):
            with pytest.raises(ValidationError, match="rate limit"):
                await _sync()

    @pytest.mark.asyncio
    async def test_server_error_on_get_message_propagates(self, base_mocks):
        from corpmind.core.exceptions import ValidationError

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ), patch(
            "corpmind.modules.inbox.gmail_client.list_inbox_messages",
            new_callable=AsyncMock,
            return_value=([_make_summary()], None),
        ), patch(
            "corpmind.modules.inbox.gmail_client.get_message",
            new_callable=AsyncMock,
            side_effect=ValidationError("Gmail API error on messages.get: HTTP 500"),
        ), patch(
            "corpmind.modules.inbox.repo.InboxConnectionRepo",
            return_value=_make_conn_repo(),
        ), patch(
            "corpmind.modules.inbox.service.InboxService",
            return_value=_make_service(),
        ):
            with pytest.raises(ValidationError, match="HTTP 500"):
                await _sync()


# ── Sync metadata tests ────────────────────────────────────────────────────────

class TestSyncMetadata:
    """last_sync_at must always be written after a successful sync run."""

    @pytest.mark.asyncio
    async def test_last_sync_at_written_on_success(self, base_mocks):
        conn_repo = _make_conn_repo()

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
            return_value=_make_tokens(),
        ):
            stack, cr, _ = _gmail_patches(conn_repo=conn_repo)
            with stack:
                await _sync()

        # The final update call (after the pagination loop) sets last_sync_at
        last_update = conn_repo.update.call_args_list[-1].args[1]
        assert "last_sync_at" in last_update
        assert isinstance(last_update["last_sync_at"], datetime)
        assert last_update["status"] == "active"
        assert last_update["last_error"] is None

    @pytest.mark.asyncio
    async def test_connection_not_found_returns_not_found(self, base_mocks):
        conn_repo = _make_conn_repo()
        conn_repo.find_by_id = AsyncMock(return_value=None)

        with patch(
            "corpmind.modules.inbox.oauth.refresh_google_token",
            new_callable=AsyncMock,
        ) as mock_refresh, patch(
            "corpmind.modules.inbox.repo.InboxConnectionRepo",
            return_value=conn_repo,
        ), patch(
            "corpmind.modules.inbox.service.InboxService",
            return_value=_make_service(),
        ):
            result = await _sync()

        assert result["status"] == "not_found"
        mock_refresh.assert_not_awaited()
