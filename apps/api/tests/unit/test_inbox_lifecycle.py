"""Unit tests for Sprint 2C-B: Connection Lifecycle Management.

Test categories (per spec):
  A. Get connection success / not found / tenant isolation
  B. Disconnect success / wrong tenant / best-effort revocation
  C. Token refresh success / failure / revoked-token handling
  D. Connection health success / unhealthy (revoked) / unhealthy (permissions)
  E. Encrypted token persistence

All Google API calls (refresh_google_token, revoke_google_token, fetch_gmail_profile)
are patched at the service module level — no live network calls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.inbox.models import InboxConnection
from corpmind.modules.inbox.schemas import ConnectionHealthOut, InboxConnectionOut
from corpmind.modules.inbox.service import InboxService

# ── Shared constants ──────────────────────────────────────────────────────────

_ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_CONN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
_OTHER_ORG_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
_NOW = datetime(2026, 6, 6, 10, 0, 0, tzinfo=UTC)

_CTX = TenantContext(
    org_id=_ORG_ID,
    workspace_id=_WS_ID,
    user_id=_USER_ID,
    role="trainer",
    request_id="req-lifecycle-test",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_conn(
    conn_id: uuid.UUID = _CONN_ID,
    org_id: uuid.UUID = _ORG_ID,
    status: str = "active",
) -> InboxConnection:
    conn = InboxConnection(
        id=conn_id,
        tenant_id=org_id,
        workspace_id=_WS_ID,
        provider="gmail",
        email_address_enc="enc:trainer@example.com",
        refresh_token_enc="enc:raw-refresh-token",
        access_token_enc=None,
        email_address_hash="a" * 64,
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        status=status,
        last_sync_at=None,
        last_error=None,
        connected_by=_USER_ID,
    )
    conn.created_at = _NOW
    conn.updated_at = _NOW
    return conn


def _make_tokens_response(
    access_token: str = "new-access-token",
    refresh_token: str | None = None,
    expires_in: int = 3600,
) -> MagicMock:
    from corpmind.modules.inbox.oauth import GoogleTokens
    return GoogleTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope="https://www.googleapis.com/auth/gmail.readonly",
    )


def _make_profile_response(email: str = "trainer@example.com") -> MagicMock:
    from corpmind.modules.inbox.oauth import GmailProfile
    return GmailProfile(email=email, name="Test User")


# ══════════════════════════════════════════════════════════════════════════════
# A. Get workspace connection
# ══════════════════════════════════════════════════════════════════════════════

class TestGetWorkspaceConnection:
    """A. GET /api/v1/inbox/connection — fetch active connection for workspace."""

    @pytest.mark.asyncio
    async def test_get_connection_success(self) -> None:
        """Returns InboxConnectionOut with decrypted email when a connection exists."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with patch("corpmind.modules.inbox.service.decrypt", return_value="trainer@example.com"):
            svc = InboxService(session)
            svc._conn_repo.find_by_workspace = AsyncMock(return_value=[conn])

            result = await svc.get_workspace_connection()

        clear_tenant_context(token)

        assert isinstance(result, InboxConnectionOut)
        assert result.id == _CONN_ID
        assert result.email_address == "trainer@example.com"
        assert result.provider == "gmail"
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_get_connection_not_found(self) -> None:
        """Raises NotFoundError when no connections exist for the workspace."""
        token = set_tenant_context(_CTX)
        session = _mock_session()

        svc = InboxService(session)
        svc._conn_repo.find_by_workspace = AsyncMock(return_value=[])

        with pytest.raises(NotFoundError, match="No inbox connection found"):
            await svc.get_workspace_connection()

        clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_get_connection_uses_context_workspace_id(self) -> None:
        """find_by_workspace is called with the workspace_id from TenantContext."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with patch("corpmind.modules.inbox.service.decrypt", return_value="x@example.com"):
            svc = InboxService(session)
            svc._conn_repo.find_by_workspace = AsyncMock(return_value=[conn])

            await svc.get_workspace_connection()

        clear_tenant_context(token)

        svc._conn_repo.find_by_workspace.assert_awaited_once_with(_WS_ID, limit=1)


# ══════════════════════════════════════════════════════════════════════════════
# B. Disconnect connection
# ══════════════════════════════════════════════════════════════════════════════

class TestDisconnectConnection:
    """B. DELETE /api/v1/inbox/connection/{id} — revoke + delete."""

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        """Happy path: revoke and delete; session committed."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch("corpmind.modules.inbox.service.revoke_google_token", new_callable=AsyncMock) as mock_revoke,
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.delete = AsyncMock(return_value=True)

            await svc.disconnect_connection(_CONN_ID)

        clear_tenant_context(token)

        mock_revoke.assert_awaited_once_with("raw-refresh-token")
        svc._conn_repo.delete.assert_awaited_once_with(_CONN_ID)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_found_raises(self) -> None:
        """NotFoundError when connection does not exist; revoke and delete not called."""
        token = set_tenant_context(_CTX)
        session = _mock_session()

        with patch("corpmind.modules.inbox.service.revoke_google_token", new_callable=AsyncMock) as mock_revoke:
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=None)
            svc._conn_repo.delete = AsyncMock()

            with pytest.raises(NotFoundError, match=str(_CONN_ID)):
                await svc.disconnect_connection(_CONN_ID)

        clear_tenant_context(token)

        mock_revoke.assert_not_awaited()
        svc._conn_repo.delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect_wrong_tenant_raises(self) -> None:
        """find_by_id returns None for wrong-tenant connections — same 404 as not found.

        The repo filters by tenant_id; a cross-tenant request is indistinguishable
        from a missing connection.  This prevents existence leakage.
        """
        token = set_tenant_context(_CTX)
        session = _mock_session()

        svc = InboxService(session)
        # Repo returns None when tenant_id in the WHERE clause doesn't match.
        svc._conn_repo.find_by_id = AsyncMock(return_value=None)
        svc._conn_repo.delete = AsyncMock()

        with pytest.raises(NotFoundError):
            await svc.disconnect_connection(_CONN_ID)

        clear_tenant_context(token)
        svc._conn_repo.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect_revocation_failure_still_deletes(self) -> None:
        """If revoke_google_token raises, the local connection is still deleted."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.revoke_google_token",
                new_callable=AsyncMock,
                side_effect=Exception("Google unreachable"),
            ),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.delete = AsyncMock(return_value=True)

            # Should not raise even though revocation failed.
            await svc.disconnect_connection(_CONN_ID)

        clear_tenant_context(token)

        svc._conn_repo.delete.assert_awaited_once_with(_CONN_ID)
        session.commit.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# C. Token refresh
# ══════════════════════════════════════════════════════════════════════════════

class TestRefreshAccessToken:
    """C. POST /api/v1/inbox/connection/{id}/refresh — refresh + persist new token."""

    @pytest.mark.asyncio
    async def test_refresh_success_returns_updated_connection(self) -> None:
        """Happy path: new encrypted token stored, status=active, DTO returned."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        new_tokens = _make_tokens_response(access_token="brand-new-access-token")

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:brand-new-access-token"),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(side_effect=[conn, conn])
            svc._conn_repo.update = AsyncMock()

            result = await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)

        assert isinstance(result, InboxConnectionOut)
        assert result.status == "active"
        svc._conn_repo.update.assert_awaited_once()
        update_args = svc._conn_repo.update.call_args[0]
        assert update_args[0] == _CONN_ID
        assert update_args[1]["status"] == "active"
        assert update_args[1]["access_token_enc"] == "enc:brand-new-access-token"
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_refresh_failure_marks_revoked_and_reraises(self) -> None:
        """Google rejection marks status=revoked and re-raises ValidationError."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("Google token refresh failed: Token has been revoked"),
            ),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.update = AsyncMock()

            with pytest.raises(ValidationError, match="token refresh failed"):
                await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)

        svc._conn_repo.update.assert_awaited_once()
        update_args = svc._conn_repo.update.call_args[0]
        assert update_args[1]["status"] == "revoked"
        assert "re-authorization" in update_args[1]["last_error"]
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_not_found_raises(self) -> None:
        """NotFoundError when connection is absent; no Google call made."""
        token = set_tenant_context(_CTX)
        session = _mock_session()

        with patch(
            "corpmind.modules.inbox.service.refresh_google_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=None)

            with pytest.raises(NotFoundError):
                await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)
        mock_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresh_decrypts_refresh_token_before_google_call(self) -> None:
        """decrypt() is called on refresh_token_enc before refresh_google_token."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        new_tokens = _make_tokens_response()
        call_order: list[str] = []

        def _decrypt_side(val: str) -> str:
            call_order.append("decrypt")
            return "raw-refresh-token"

        async def _refresh_side(rt: str) -> object:
            call_order.append("refresh_google_token")
            return new_tokens

        with (
            patch("corpmind.modules.inbox.service.decrypt", side_effect=_decrypt_side),
            patch("corpmind.modules.inbox.service.refresh_google_token", side_effect=_refresh_side),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:x"),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(side_effect=[conn, conn])
            svc._conn_repo.update = AsyncMock()

            await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)

        # decrypt must be called before refresh_google_token
        assert call_order[0] == "decrypt"
        assert "refresh_google_token" in call_order


# ══════════════════════════════════════════════════════════════════════════════
# D. Connection health
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckConnectionHealth:
    """D. GET /api/v1/inbox/connection/{id}/health — validate and update status."""

    @pytest.mark.asyncio
    async def test_health_success(self) -> None:
        """Both token refresh and Gmail probe succeed → healthy=True, status=active."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        new_tokens = _make_tokens_response()
        profile = _make_profile_response()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch(
                "corpmind.modules.inbox.service.fetch_gmail_profile",
                new_callable=AsyncMock,
                return_value=profile,
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:new-access"),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.update = AsyncMock()

            result = await svc.check_connection_health(_CONN_ID)

        clear_tenant_context(token)

        assert isinstance(result, ConnectionHealthOut)
        assert result.healthy is True
        assert result.reason is None
        assert result.status == "active"
        svc._conn_repo.update.assert_awaited_once()
        update_payload = svc._conn_repo.update.call_args[0][1]
        assert update_payload["status"] == "active"
        assert update_payload["last_error"] is None
        assert update_payload["access_token_enc"] == "enc:new-access"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_revoked_token(self) -> None:
        """Token refresh fails → healthy=False, status=revoked, DB updated."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("Google token refresh failed: Token has been revoked"),
            ),
            patch(
                "corpmind.modules.inbox.service.fetch_gmail_profile",
                new_callable=AsyncMock,
            ) as mock_profile,
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.update = AsyncMock()

            result = await svc.check_connection_health(_CONN_ID)

        clear_tenant_context(token)

        assert result.healthy is False
        assert result.status == "revoked"
        assert "re-authorization" in result.reason
        # Gmail should not be probed when token refresh already failed
        mock_profile.assert_not_awaited()
        update_payload = svc._conn_repo.update.call_args[0][1]
        assert update_payload["status"] == "revoked"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_missing_permissions(self) -> None:
        """Token refresh OK but Gmail profile fails → healthy=False, status=needs_reauth."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        new_tokens = _make_tokens_response()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch(
                "corpmind.modules.inbox.service.fetch_gmail_profile",
                new_callable=AsyncMock,
                side_effect=ValidationError("Failed to retrieve Gmail profile from Google"),
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:new-access"),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.update = AsyncMock()

            result = await svc.check_connection_health(_CONN_ID)

        clear_tenant_context(token)

        assert result.healthy is False
        assert result.status == "needs_reauth"
        assert "permissions" in result.reason
        update_payload = svc._conn_repo.update.call_args[0][1]
        assert update_payload["status"] == "needs_reauth"
        assert update_payload["access_token_enc"] == "enc:new-access"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_connection_not_found(self) -> None:
        """NotFoundError when connection is absent or belongs to another tenant."""
        token = set_tenant_context(_CTX)
        session = _mock_session()

        with patch(
            "corpmind.modules.inbox.service.refresh_google_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=None)

            with pytest.raises(NotFoundError, match=str(_CONN_ID)):
                await svc.check_connection_health(_CONN_ID)

        clear_tenant_context(token)
        mock_refresh.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════════
# E. Encrypted token persistence
# ══════════════════════════════════════════════════════════════════════════════

class TestTokenEncryptionPersistence:
    """E. Verify tokens are never stored in plaintext."""

    @pytest.mark.asyncio
    async def test_refresh_stores_ciphertext_not_plaintext(self) -> None:
        """The access_token_enc written to DB is the encrypt() output, not the raw token."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        raw_access = "super-secret-access-token"
        enc_access = "enc:CIPHERTEXT_WOULD_BE_HERE"
        new_tokens = _make_tokens_response(access_token=raw_access)

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value=enc_access) as mock_enc,
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(side_effect=[conn, conn])
            svc._conn_repo.update = AsyncMock()

            await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)

        mock_enc.assert_called_once_with(raw_access)
        update_payload = svc._conn_repo.update.call_args[0][1]
        assert update_payload["access_token_enc"] == enc_access
        assert update_payload["access_token_enc"] != raw_access

    @pytest.mark.asyncio
    async def test_health_check_stores_ciphertext_not_plaintext(self) -> None:
        """Health check persists encrypt(new_access_token), never the raw value."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        raw_access = "raw-new-access-token"
        new_tokens = _make_tokens_response(access_token=raw_access)
        profile = _make_profile_response()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch(
                "corpmind.modules.inbox.service.fetch_gmail_profile",
                new_callable=AsyncMock,
                return_value=profile,
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:raw-new-access-token") as mock_enc,
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(return_value=conn)
            svc._conn_repo.update = AsyncMock()

            await svc.check_connection_health(_CONN_ID)

        clear_tenant_context(token)

        mock_enc.assert_called_once_with(raw_access)
        update_payload = svc._conn_repo.update.call_args[0][1]
        assert update_payload["access_token_enc"] != raw_access

    @pytest.mark.asyncio
    async def test_refresh_api_never_exposed_in_connection_out(self) -> None:
        """The returned InboxConnectionOut must not contain any token fields."""
        token = set_tenant_context(_CTX)
        session = _mock_session()
        conn = _make_conn()
        new_tokens = _make_tokens_response()

        with (
            patch("corpmind.modules.inbox.service.decrypt", return_value="raw-refresh-token"),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                return_value=new_tokens,
            ),
            patch("corpmind.modules.inbox.service.encrypt", return_value="enc:x"),
        ):
            svc = InboxService(session)
            svc._conn_repo.find_by_id = AsyncMock(side_effect=[conn, conn])
            svc._conn_repo.update = AsyncMock()

            result = await svc.refresh_access_token(_CONN_ID)

        clear_tenant_context(token)

        result_dict = result.model_dump()
        # These credential fields must never appear in the connection DTO.
        # token_expiry_at is a safe metadata field (a timestamp, not a credential).
        secret_fields = {"refresh_token", "access_token", "refresh_token_enc", "access_token_enc"}
        for field_name in secret_fields:
            assert field_name not in result_dict, f"Secret field exposed in DTO: {field_name!r}"
