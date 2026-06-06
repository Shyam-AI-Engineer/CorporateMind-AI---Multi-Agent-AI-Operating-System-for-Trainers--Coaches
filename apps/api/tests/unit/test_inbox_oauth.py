"""Unit tests for inbox OAuth: state management, connect, and callback.

All external dependencies (Redis, Google APIs, InboxService) are mocked.
No database or network I/O occurs.

Test categories (per Sprint 2C-A spec):
  A. State generation
  B. State validation
  C. Expired state
  D. Invalid state
  E. Callback success
  F. Duplicate connection
  G. Token encryption (plaintext passed to InboxService; service encrypts)
  H. Tenant isolation
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import AuthenticationError, ConflictError, ValidationError
from corpmind.core.tenancy import TenantContext
from corpmind.modules.inbox.oauth import (
    GmailProfile,
    GoogleTokens,
    OAuthStatePayload,
    build_authorization_url,
    consume_oauth_state,
    exchange_code_for_tokens,
    fetch_gmail_profile,
    generate_oauth_state,
)
from corpmind.modules.inbox.schemas import InboxConnectionOut

# ── Shared fixtures ────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_CONN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
_NOW = datetime(2026, 6, 6, 10, 0, 0, tzinfo=UTC)


def _make_ctx(
    tenant_id: uuid.UUID = _TENANT_ID,
    workspace_id: uuid.UUID = _WORKSPACE_ID,
    user_id: uuid.UUID = _USER_ID,
) -> TenantContext:
    return TenantContext(
        org_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        role="trainer",
        request_id="test-request-id",
    )


def _make_state_payload(
    tenant_id: uuid.UUID = _TENANT_ID,
    workspace_id: uuid.UUID = _WORKSPACE_ID,
    user_id: uuid.UUID = _USER_ID,
) -> OAuthStatePayload:
    return OAuthStatePayload(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
    )


def _make_tokens(
    access_token: str = "acc-token",
    refresh_token: str | None = "ref-token",
    expires_in: int = 3600,
) -> GoogleTokens:
    return GoogleTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope="openid email https://www.googleapis.com/auth/gmail.readonly",
    )


def _make_profile(email: str = "user@example.com", name: str = "Test User") -> GmailProfile:
    return GmailProfile(email=email, name=name)


def _make_connection_out(email: str = "user@example.com") -> InboxConnectionOut:
    return InboxConnectionOut(
        id=_CONN_ID,
        workspace_id=_WORKSPACE_ID,
        provider="gmail",
        email_address=email,
        scopes="openid email https://www.googleapis.com/auth/gmail.readonly",
        token_expiry_at=None,
        status="active",
        last_sync_at=None,
        last_error=None,
        connected_by=_USER_ID,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mock_redis(*, stored_value: str | None = None) -> MagicMock:
    """Return an async Redis mock where getdel returns stored_value."""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.getdel = AsyncMock(return_value=stored_value)
    return redis


def _mock_request(request_id: str = "req-test") -> MagicMock:
    req = MagicMock()
    req.headers = {"X-Request-ID": request_id}
    return req


# ══════════════════════════════════════════════════════════════════════════════
# A. State generation
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateOAuthState:
    """A. State generation — opaque, random, stored in Redis with TTL."""

    @pytest.mark.asyncio
    async def test_returns_url_safe_ascii_string(self) -> None:
        """Generated token must be safe to include directly in a URL query param."""
        redis = _mock_redis()
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            token = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)

        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in token), f"Non-URL-safe chars in token: {token!r}"

    @pytest.mark.asyncio
    async def test_each_call_returns_unique_token(self) -> None:
        """Token uniqueness — 32 bytes of entropy means collision probability ≈ 0."""
        redis = _mock_redis()
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            t1 = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)
            t2 = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)

        assert t1 != t2

    @pytest.mark.asyncio
    async def test_payload_stored_in_redis_with_ttl(self) -> None:
        """Redis SET must be called with ex=600 and the correct JSON payload."""
        redis = _mock_redis()
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            token = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)

        assert redis.set.await_count == 1
        _key, payload_raw = redis.set.call_args.args
        assert token in _key

        stored = json.loads(payload_raw)
        assert stored["tenant_id"] == str(_TENANT_ID)
        assert stored["workspace_id"] == str(_WORKSPACE_ID)
        assert stored["user_id"] == str(_USER_ID)

        # TTL must be 600 seconds
        assert redis.set.call_args.kwargs.get("ex") == 600

    @pytest.mark.asyncio
    async def test_token_encodes_32_bytes_of_entropy(self) -> None:
        """Decoded token must be 32 bytes — the base64url representation without padding."""
        redis = _mock_redis()
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            token = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)

        # Restore padding before decoding
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
        assert len(raw) == 32


# ══════════════════════════════════════════════════════════════════════════════
# B. State validation
# ══════════════════════════════════════════════════════════════════════════════

class TestConsumeOAuthStateValid:
    """B. State validation — valid token returns correct payload."""

    def _stored_payload(
        self,
        tenant_id: uuid.UUID = _TENANT_ID,
        workspace_id: uuid.UUID = _WORKSPACE_ID,
        user_id: uuid.UUID = _USER_ID,
    ) -> str:
        return json.dumps(
            {
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
            }
        )

    @pytest.mark.asyncio
    async def test_valid_state_returns_correct_payload(self) -> None:
        redis = _mock_redis(stored_value=self._stored_payload())
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("valid-state-token")

        assert result is not None
        assert result.tenant_id == _TENANT_ID
        assert result.workspace_id == _WORKSPACE_ID
        assert result.user_id == _USER_ID

    @pytest.mark.asyncio
    async def test_valid_state_deletes_key_atomically(self) -> None:
        """GETDEL is called — not GET + DEL — ensuring atomicity."""
        redis = _mock_redis(stored_value=self._stored_payload())
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            await consume_oauth_state("the-state")

        redis.getdel.assert_awaited_once()
        # The key must contain the state token
        assert "the-state" in redis.getdel.call_args.args[0]


# ══════════════════════════════════════════════════════════════════════════════
# C. Expired state
# ══════════════════════════════════════════════════════════════════════════════

class TestConsumeOAuthStateExpired:
    """C. Expired state — Redis GETDEL returns None when the key has expired."""

    @pytest.mark.asyncio
    async def test_expired_state_returns_none(self) -> None:
        """Redis returns None for expired keys — same as a missing key."""
        redis = _mock_redis(stored_value=None)
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("expired-state")

        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# D. Invalid state
# ══════════════════════════════════════════════════════════════════════════════

class TestConsumeOAuthStateInvalid:
    """D. Invalid state — missing or malformed tokens return None without raising."""

    @pytest.mark.asyncio
    async def test_missing_state_returns_none(self) -> None:
        redis = _mock_redis(stored_value=None)
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("nonexistent-state")

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none(self) -> None:
        """Corrupted Redis value must not crash — return None gracefully."""
        redis = _mock_redis(stored_value="not-valid-json{{{")
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("state-with-bad-payload")

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_fields_in_payload_returns_none(self) -> None:
        """Payload with missing keys must return None, not KeyError."""
        partial = json.dumps({"tenant_id": str(_TENANT_ID)})  # workspace_id + user_id absent
        redis = _mock_redis(stored_value=partial)
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("partial-payload")

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_uuid_in_payload_returns_none(self) -> None:
        bad = json.dumps(
            {"tenant_id": "not-a-uuid", "workspace_id": str(_WORKSPACE_ID), "user_id": str(_USER_ID)}
        )
        redis = _mock_redis(stored_value=bad)
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            result = await consume_oauth_state("bad-uuid-state")

        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Connect endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestConnectEndpoint:
    """Connect endpoint — redirects to Google with correct params."""

    @pytest.mark.asyncio
    async def test_redirects_to_google_auth_url(self) -> None:
        from fastapi.responses import RedirectResponse

        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="test-state-tok",
            ):
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "test-client-id"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/callback"

                    response = await connect()

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        location = response.headers["location"]
        assert "accounts.google.com/o/oauth2/v2/auth" in location

    @pytest.mark.asyncio
    async def test_redirect_includes_gmail_readonly_scope(self) -> None:
        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="s",
            ):
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "cid"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

                    response = await connect()

        location = response.headers["location"]
        assert "gmail.readonly" in location

    @pytest.mark.asyncio
    async def test_redirect_requests_offline_access(self) -> None:
        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="s",
            ):
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "cid"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

                    response = await connect()

        location = response.headers["location"]
        assert "access_type=offline" in location

    @pytest.mark.asyncio
    async def test_redirect_includes_prompt_consent(self) -> None:
        """prompt=consent forces Google to always return a refresh_token."""
        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="s",
            ):
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "cid"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

                    response = await connect()

        assert "prompt=consent" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_redirect_embeds_state_param(self) -> None:
        """The CSRF state token must appear in the redirect URL."""
        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="unique-state-xyz",
            ):
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "cid"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

                    response = await connect()

        assert "state=unique-state-xyz" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_connect_uses_workspace_id_from_query_param(self) -> None:
        """When workspace_id query param is provided it overrides the JWT workspace."""
        from corpmind.modules.inbox.api import connect

        custom_ws = uuid.uuid4()
        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx) as mock_ctx:
            with patch(
                "corpmind.modules.inbox.api.generate_oauth_state",
                new_callable=AsyncMock,
                return_value="s",
            ) as mock_gen:
                with patch("corpmind.modules.inbox.api.settings") as mock_s:
                    mock_s.GOOGLE_CLIENT_ID = "cid"
                    mock_s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

                    await connect(workspace_id=custom_ws)

        mock_gen.assert_awaited_once_with(ctx.org_id, custom_ws, ctx.user_id)

    @pytest.mark.asyncio
    async def test_connect_raises_validation_error_when_not_configured(self) -> None:
        """Empty GOOGLE_CLIENT_ID must produce a 422, not a redirect to a broken URL."""
        from corpmind.modules.inbox.api import connect

        ctx = _make_ctx()
        with patch("corpmind.modules.inbox.api.get_tenant_context", return_value=ctx):
            with patch("corpmind.modules.inbox.api.settings") as mock_s:
                mock_s.GOOGLE_CLIENT_ID = ""
                mock_s.GOOGLE_REDIRECT_URI = ""

                with pytest.raises(ValidationError, match="not configured"):
                    await connect()


# ══════════════════════════════════════════════════════════════════════════════
# E. Callback success
# ══════════════════════════════════════════════════════════════════════════════

class TestCallbackSuccess:
    """E. Callback success — full happy path creates an InboxConnection."""

    @pytest.mark.asyncio
    async def test_callback_success_returns_connection_out(self) -> None:
        from corpmind.modules.inbox.api import _complete_connection

        expected = _make_connection_out()
        session = AsyncMock()
        request = _mock_request()

        with patch(
            "corpmind.modules.inbox.api.set_rls_tenant", new_callable=AsyncMock
        ):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=_make_tokens(),
            ):
                with patch(
                    "corpmind.modules.inbox.api.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=_make_profile(),
                ):
                    with patch(
                        "corpmind.modules.inbox.api.InboxService"
                    ) as MockSvc:
                        MockSvc.return_value.create_connection = AsyncMock(return_value=expected)

                        result = await _complete_connection(
                            request, _make_state_payload(), "auth-code", session
                        )

        assert result == expected

    @pytest.mark.asyncio
    async def test_callback_error_param_raises_auth_error(self) -> None:
        """?error=access_denied must raise AuthenticationError (401), not 500."""
        from corpmind.modules.inbox.api import callback

        session = AsyncMock()
        request = _mock_request()

        with pytest.raises(AuthenticationError, match="access_denied"):
            await callback(
                request=request,
                state="some-state",
                code=None,
                error="access_denied",
                session=session,
            )

    @pytest.mark.asyncio
    async def test_callback_missing_code_raises_validation_error(self) -> None:
        """Missing ?code param with no ?error means a malformed callback."""
        from corpmind.modules.inbox.api import callback

        session = AsyncMock()
        request = _mock_request()

        with pytest.raises(ValidationError, match="Missing authorization code"):
            await callback(
                request=request,
                state="some-state",
                code=None,
                error=None,
                session=session,
            )

    @pytest.mark.asyncio
    async def test_callback_invalid_state_raises_auth_error(self) -> None:
        from corpmind.modules.inbox.api import callback

        session = AsyncMock()
        request = _mock_request()

        with patch(
            "corpmind.modules.inbox.api.consume_oauth_state",
            new_callable=AsyncMock,
            return_value=None,  # state not found / expired
        ):
            with pytest.raises(AuthenticationError, match="Invalid or expired"):
                await callback(
                    request=request,
                    state="bad-state",
                    code="some-code",
                    error=None,
                    session=session,
                )

    @pytest.mark.asyncio
    async def test_no_refresh_token_raises_validation_error(self) -> None:
        """Google omitting the refresh_token (e.g., no prompt=consent) must fail early."""
        from corpmind.modules.inbox.api import _complete_connection

        session = AsyncMock()
        request = _mock_request()
        tokens_without_refresh = _make_tokens(refresh_token=None)

        with patch("corpmind.modules.inbox.api.set_rls_tenant", new_callable=AsyncMock):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=tokens_without_refresh,
            ):
                with pytest.raises(ValidationError, match="refresh token"):
                    await _complete_connection(
                        request, _make_state_payload(), "code", session
                    )


# ══════════════════════════════════════════════════════════════════════════════
# F. Duplicate connection
# ══════════════════════════════════════════════════════════════════════════════

class TestDuplicateConnection:
    """F. Duplicate connection — ConflictError propagates from InboxService."""

    @pytest.mark.asyncio
    async def test_duplicate_email_propagates_conflict_error(self) -> None:
        """InboxService.create_connection raises ConflictError on duplicate email.
        The callback must propagate it (→ 409) rather than catching it."""
        from corpmind.modules.inbox.api import _complete_connection

        session = AsyncMock()
        request = _mock_request()

        with patch("corpmind.modules.inbox.api.set_rls_tenant", new_callable=AsyncMock):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=_make_tokens(),
            ):
                with patch(
                    "corpmind.modules.inbox.api.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=_make_profile(),
                ):
                    with patch("corpmind.modules.inbox.api.InboxService") as MockSvc:
                        MockSvc.return_value.create_connection = AsyncMock(
                            side_effect=ConflictError(
                                "An inbox connection for this email address already exists"
                            )
                        )

                        with pytest.raises(ConflictError):
                            await _complete_connection(
                                request, _make_state_payload(), "code", session
                            )


# ══════════════════════════════════════════════════════════════════════════════
# G. Token encryption
# ══════════════════════════════════════════════════════════════════════════════

class TestTokenEncryption:
    """G. Token encryption — plaintext tokens passed to InboxService; service encrypts.

    The callback handler must NOT call encrypt() itself.  InboxService.create_connection
    owns encryption.  We verify the DTO passed to the service carries plaintext values.
    """

    @pytest.mark.asyncio
    async def test_plaintext_tokens_passed_to_inbox_service(self) -> None:
        from corpmind.modules.inbox.api import _complete_connection

        session = AsyncMock()
        request = _mock_request()
        raw_access = "raw-access-token-plaintext"
        raw_refresh = "raw-refresh-token-plaintext"

        with patch("corpmind.modules.inbox.api.set_rls_tenant", new_callable=AsyncMock):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=_make_tokens(access_token=raw_access, refresh_token=raw_refresh),
            ):
                with patch(
                    "corpmind.modules.inbox.api.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=_make_profile(),
                ):
                    with patch("corpmind.modules.inbox.api.InboxService") as MockSvc:
                        MockSvc.return_value.create_connection = AsyncMock(
                            return_value=_make_connection_out()
                        )

                        await _complete_connection(
                            request, _make_state_payload(), "code", session
                        )

                        call_args = MockSvc.return_value.create_connection.call_args
                        req_dto = call_args.args[0]

        # Verify plaintext (not ciphertext) was handed to the service
        assert req_dto.access_token == raw_access
        assert req_dto.refresh_token == raw_refresh

    @pytest.mark.asyncio
    async def test_handler_does_not_call_encrypt_directly(self) -> None:
        """The api.py module must never import or call encrypt() — that belongs to InboxService."""
        # If encrypt were imported in api.py, this patch would succeed and be called.
        # If it raises AttributeError, the import isn't there (which is correct).
        import corpmind.modules.inbox.api as api_module

        assert not hasattr(api_module, "encrypt"), (
            "api.py must not import encrypt() — encryption is InboxService's responsibility"
        )


# ══════════════════════════════════════════════════════════════════════════════
# H. Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    """H. Tenant isolation — state token embeds no tenant info; payload is server-side only."""

    @pytest.mark.asyncio
    async def test_state_token_is_opaque(self) -> None:
        """Decoding the state token must NOT reveal tenant_id, workspace_id, or user_id."""
        redis = _mock_redis()
        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            token = await generate_oauth_state(_TENANT_ID, _WORKSPACE_ID, _USER_ID)

        # The raw token bytes (base64url-decoded) should not contain any UUID strings
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode("latin-1")
        assert str(_TENANT_ID) not in raw
        assert str(_WORKSPACE_ID) not in raw
        assert str(_USER_ID) not in raw

    @pytest.mark.asyncio
    async def test_state_is_single_use(self) -> None:
        """After a successful consume, the same state returns None (key deleted)."""
        stored = json.dumps(
            {
                "tenant_id": str(_TENANT_ID),
                "workspace_id": str(_WORKSPACE_ID),
                "user_id": str(_USER_ID),
            }
        )
        # First call returns the payload; second call returns None (key gone)
        redis = MagicMock()
        redis.getdel = AsyncMock(side_effect=[stored, None])

        with patch("corpmind.modules.inbox.oauth.get_redis", return_value=redis):
            first = await consume_oauth_state("once-only-state")
            second = await consume_oauth_state("once-only-state")

        assert first is not None
        assert second is None

    @pytest.mark.asyncio
    async def test_tenant_context_set_from_state_payload_not_url(self) -> None:
        """_complete_connection must use tenant_id from state payload, never from the URL.

        We use a distinct tenant in the state and verify that InboxService is called
        with that tenant's workspace — not with any externally supplied value.
        """
        from corpmind.modules.inbox.api import _complete_connection

        other_tenant_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        other_workspace_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        other_user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        payload = _make_state_payload(
            tenant_id=other_tenant_id,
            workspace_id=other_workspace_id,
            user_id=other_user_id,
        )
        session = AsyncMock()
        request = _mock_request()

        captured_rls_tenant: list[uuid.UUID] = []

        async def _capture_rls(sess: object, tid: uuid.UUID) -> None:
            captured_rls_tenant.append(tid)

        with patch("corpmind.modules.inbox.api.set_rls_tenant", side_effect=_capture_rls):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=_make_tokens(),
            ):
                with patch(
                    "corpmind.modules.inbox.api.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=_make_profile(),
                ):
                    with patch("corpmind.modules.inbox.api.InboxService") as MockSvc:
                        MockSvc.return_value.create_connection = AsyncMock(
                            return_value=_make_connection_out()
                        )

                        await _complete_connection(request, payload, "code", session)

                        call_args = MockSvc.return_value.create_connection.call_args
                        req_dto = call_args.args[0]

        # RLS was activated with the tenant from the state payload
        assert captured_rls_tenant[0] == other_tenant_id
        # InboxConnectionCreate.workspace_id came from the state payload
        assert req_dto.workspace_id == other_workspace_id

    @pytest.mark.asyncio
    async def test_tenant_context_cleared_on_exception(self) -> None:
        """TenantContext must be cleared even when _complete_connection raises."""
        from corpmind.modules.inbox.api import _complete_connection
        from corpmind.core.tenancy import _tenant_ctx

        session = AsyncMock()
        request = _mock_request()

        with patch("corpmind.modules.inbox.api.set_rls_tenant", new_callable=AsyncMock):
            with patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                side_effect=ValidationError("token exchange failed"),
            ):
                with pytest.raises(ValidationError):
                    await _complete_connection(
                        request, _make_state_payload(), "code", session
                    )

        # ContextVar must be None after the handler finishes — no context leak
        assert _tenant_ctx.get() is None


# ══════════════════════════════════════════════════════════════════════════════
# Build authorization URL (unit)
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildAuthorizationUrl:
    """build_authorization_url — URL construction correctness."""

    def test_contains_google_auth_endpoint(self) -> None:
        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "my-client-id"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"
            url = build_authorization_url("my-state")

        assert "accounts.google.com/o/oauth2/v2/auth" in url

    def test_contains_all_gmail_scopes(self) -> None:
        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"
            url = build_authorization_url("st")

        assert "gmail.readonly" in url
        assert "openid" in url
        assert "email" in url

    def test_contains_offline_access_type(self) -> None:
        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"
            url = build_authorization_url("st")

        assert "access_type=offline" in url

    def test_contains_prompt_consent(self) -> None:
        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"
            url = build_authorization_url("st")

        assert "prompt=consent" in url

    def test_state_embedded_in_url(self) -> None:
        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"
            url = build_authorization_url("my-csrf-state")

        assert "my-csrf-state" in url


# ══════════════════════════════════════════════════════════════════════════════
# Google API calls (httpx mocked via respx)
# ══════════════════════════════════════════════════════════════════════════════

class TestExchangeCodeForTokens:
    """exchange_code_for_tokens — covers the httpx POST to Google's token endpoint."""

    @pytest.mark.asyncio
    async def test_success_returns_tokens(self) -> None:
        import respx
        import httpx

        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_CLIENT_SECRET = "secret"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

            with respx.mock:
                respx.post("https://oauth2.googleapis.com/token").mock(
                    return_value=httpx.Response(
                        200,
                        json={
                            "access_token": "acc",
                            "refresh_token": "ref",
                            "expires_in": 3600,
                            "scope": "openid email",
                        },
                    )
                )
                result = await exchange_code_for_tokens("auth-code")

        assert result.access_token == "acc"
        assert result.refresh_token == "ref"
        assert result.expires_in == 3600

    @pytest.mark.asyncio
    async def test_non_200_raises_validation_error(self) -> None:
        import respx
        import httpx

        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_CLIENT_SECRET = "secret"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

            with respx.mock:
                respx.post("https://oauth2.googleapis.com/token").mock(
                    return_value=httpx.Response(400, json={"error": "invalid_grant"})
                )
                with pytest.raises(ValidationError, match="token exchange failed"):
                    await exchange_code_for_tokens("bad-code")

    @pytest.mark.asyncio
    async def test_error_field_in_200_response_raises_validation_error(self) -> None:
        import respx
        import httpx

        with patch("corpmind.modules.inbox.oauth.settings") as s:
            s.GOOGLE_CLIENT_ID = "cid"
            s.GOOGLE_CLIENT_SECRET = "secret"
            s.GOOGLE_REDIRECT_URI = "http://localhost/cb"

            with respx.mock:
                respx.post("https://oauth2.googleapis.com/token").mock(
                    return_value=httpx.Response(
                        200,
                        json={
                            "error": "invalid_client",
                            "error_description": "The OAuth client was not found.",
                        },
                    )
                )
                with pytest.raises(ValidationError, match="The OAuth client was not found"):
                    await exchange_code_for_tokens("code")


class TestFetchGmailProfile:
    """fetch_gmail_profile — covers the httpx GET to Google's userinfo endpoint."""

    @pytest.mark.asyncio
    async def test_success_returns_profile(self) -> None:
        import respx
        import httpx

        with respx.mock:
            respx.get("https://www.googleapis.com/oauth2/v1/userinfo").mock(
                return_value=httpx.Response(
                    200, json={"email": "jane@example.com", "name": "Jane Doe"}
                )
            )
            result = await fetch_gmail_profile("access-tok")

        assert result.email == "jane@example.com"
        assert result.name == "Jane Doe"

    @pytest.mark.asyncio
    async def test_non_200_raises_validation_error(self) -> None:
        import respx
        import httpx

        with respx.mock:
            respx.get("https://www.googleapis.com/oauth2/v1/userinfo").mock(
                return_value=httpx.Response(401, json={"error": "invalid_token"})
            )
            with pytest.raises(ValidationError, match="Gmail profile"):
                await fetch_gmail_profile("bad-token")

    @pytest.mark.asyncio
    async def test_missing_email_raises_validation_error(self) -> None:
        import respx
        import httpx

        with respx.mock:
            respx.get("https://www.googleapis.com/oauth2/v1/userinfo").mock(
                return_value=httpx.Response(200, json={"name": "No Email User"})
            )
            with pytest.raises(ValidationError, match="email address"):
                await fetch_gmail_profile("token")
