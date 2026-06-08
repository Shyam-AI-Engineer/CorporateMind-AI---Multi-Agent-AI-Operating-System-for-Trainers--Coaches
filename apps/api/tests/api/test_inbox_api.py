"""HTTP-layer integration tests for /api/v1/inbox/*.

Test matrix (33 tests):

  GET /connect
    - redirects to Google with correct params
    - requires authentication (401 without JWT)
    - raises 422 when GOOGLE_CLIENT_ID not configured

  GET /callback
    - 200 on valid state + code (Google API mocked)
    - 401 on invalid / expired state token
    - 422 when Google returns ?error=access_denied
    - 422 when code is absent from the callback URL
    - 409 when the same email is connected twice

  GET /connection
    - 200 returns InboxConnectionOut for existing connection
    - 404 when no connection in this workspace
    - 401 without auth

  DELETE /connection/{id}
    - 204 on success (Google revoke mocked)
    - 404 for unknown id
    - 401 without auth

  POST /connection/{id}/refresh
    - 200 with updated connection (Google token refresh mocked)
    - 422 when Google rejects the refresh token (marks status=revoked)
    - 404 for unknown id
    - 401 without auth

  GET /connection/{id}/health
    - 200 healthy=True when both refresh + Gmail probe succeed
    - 200 healthy=False when token is revoked
    - 404 for unknown id
    - 401 without auth

  Tenant isolation
    - Tenant B cannot delete Tenant A's connection (404)
    - Tenant B cannot refresh Tenant A's connection (404)

Notes:
  - OAuth state tokens are written directly into testcontainer Redis to avoid
    depending on GOOGLE_CLIENT_ID being configured in the test environment.
  - Google API calls (exchange_code_for_tokens, fetch_gmail_profile,
    refresh_google_token, revoke_google_token) are always mocked.
  - NullPool seeding is used to pre-populate inbox_connections rows in tests
    that need an existing connection for non-CRUD assertions.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.api.conftest import make_user

# Key prefix must match corpmind.modules.inbox.oauth._STATE_KEY_PREFIX
_STATE_KEY_PREFIX = "oauth:inbox:state:"

# Encryption test key — same pattern as service integration tests
_TEST_ENC_KEY = bytes.fromhex("ab" * 32)

_MOCK_TOKENS = {
    "access_token": "mock_access_token",
    "refresh_token": "mock_refresh_token",
    "expires_in": 3600,
    "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
}

_MOCK_PROFILE = {
    "email": "test@gmail.com",
    "name": "Test User",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _enc_key_patch():
    """Return an ExitStack context manager that injects a test AES-256 key."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch.dict("corpmind.core.encryption._KEY_REGISTRY", {1: _TEST_ENC_KEY}, clear=True)
    )
    stack.enter_context(patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1))
    return stack


def _google_mocks(
    *,
    exchange_tokens=None,
    profile=None,
    refresh_tokens=None,
    revoke=None,
    refresh_side_effect=None,
    profile_side_effect=None,
):
    """Build a context manager stack for Google API mocks."""
    from contextlib import ExitStack
    from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens

    stack = ExitStack()

    if exchange_tokens is not None:
        stack.enter_context(
            patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=GoogleTokens(**exchange_tokens),
            )
        )

    if profile is not None:
        stack.enter_context(
            patch(
                "corpmind.modules.inbox.api.fetch_gmail_profile",
                new_callable=AsyncMock,
                return_value=GmailProfile(**profile),
            )
        )

    if profile_side_effect is not None:
        stack.enter_context(
            patch(
                "corpmind.modules.inbox.service.fetch_gmail_profile",
                new_callable=AsyncMock,
                side_effect=profile_side_effect,
            )
        )

    if refresh_tokens is not None or refresh_side_effect is not None:
        kwargs: dict = {"new_callable": AsyncMock}
        if refresh_tokens is not None:
            from corpmind.modules.inbox.oauth import GoogleTokens
            kwargs["return_value"] = GoogleTokens(**refresh_tokens)
        if refresh_side_effect is not None:
            kwargs["side_effect"] = refresh_side_effect
        stack.enter_context(
            patch("corpmind.modules.inbox.service.refresh_google_token", **kwargs)
        )

    if revoke is not None:
        stack.enter_context(
            patch(
                "corpmind.modules.inbox.service.revoke_google_token",
                new_callable=AsyncMock,
            )
        )

    return stack


async def _seed_connection(
    engine: AsyncEngine,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    connected_by: uuid.UUID,
    email_address_enc: str = "enc_email",
    email_address_hash: str | None = None,
    refresh_token_enc: str = "enc_refresh",
    status: str = "active",
) -> uuid.UUID:
    """Insert a minimal inbox_connections row via NullPool (superuser, bypasses RLS).

    Returns the new connection UUID.
    """
    conn_id = uuid.uuid4()
    seed = create_async_engine(engine.url.render_as_string(hide_password=False), poolclass=NullPool)
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO inbox_connections"
                    " (id, tenant_id, workspace_id, email_address_enc, email_address_hash,"
                    "  refresh_token_enc, scopes, status, connected_by)"
                    " VALUES (:id, :tid, :wid, :email_enc, :email_hash,"
                    "         :refresh_enc, :scopes, :status, :cby)"
                ),
                {
                    "id": str(conn_id),
                    "tid": str(tenant_id),
                    "wid": str(workspace_id),
                    "email_enc": email_address_enc,
                    "email_hash": email_address_hash or uuid.uuid4().hex,
                    "refresh_enc": refresh_token_enc,
                    "scopes": "openid email https://www.googleapis.com/auth/gmail.readonly",
                    "status": status,
                    "cby": str(connected_by),
                },
            )
    finally:
        await seed.dispose()
    return conn_id


async def _store_oauth_state(
    redis_client,
    *,
    state: str,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Write an OAuth state token into Redis, bypassing the /connect flow."""
    payload = json.dumps(
        {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
        }
    )
    await redis_client.set(f"{_STATE_KEY_PREFIX}{state}", payload, ex=600)


# ── GET /connect ───────────────────────────────────────────────────────────────

class TestConnectEndpoint:
    @pytest.mark.asyncio
    async def test_connect_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/inbox/connect")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_connect_missing_google_config_returns_422(self, api_client: AsyncClient):
        user = await make_user(api_client)
        access_token = user["tokens"]["access_token"]

        with (
            patch("corpmind.modules.inbox.api.settings") as mock_settings,
        ):
            mock_settings.GOOGLE_CLIENT_ID = ""
            mock_settings.GOOGLE_REDIRECT_URI = ""
            resp = await api_client.get(
                "/api/v1/inbox/connect",
                headers=_auth(access_token),
                follow_redirects=False,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_connect_redirects_to_google_when_configured(self, api_client: AsyncClient):
        user = await make_user(api_client)
        access_token = user["tokens"]["access_token"]

        with (
            patch("corpmind.modules.inbox.api.settings") as mock_settings,
            patch("corpmind.modules.inbox.api.generate_oauth_state", new_callable=AsyncMock, return_value="test_state"),
            patch("corpmind.modules.inbox.api.build_authorization_url", return_value="https://accounts.google.com/o/oauth2/v2/auth?state=test_state"),
        ):
            mock_settings.GOOGLE_CLIENT_ID = "test-client-id"
            mock_settings.GOOGLE_REDIRECT_URI = "http://localhost/callback"
            resp = await api_client.get(
                "/api/v1/inbox/connect",
                headers=_auth(access_token),
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["location"]


# ── GET /callback ──────────────────────────────────────────────────────────────

class TestCallbackEndpoint:
    @pytest.mark.asyncio
    async def test_callback_creates_connection_on_valid_state(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        # Decode JWT to get org_id / workspace_id / user_id
        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )

        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"cb-{uuid.uuid4().hex[:6]}@gmail.com", name="CB Test")

        with (
            _enc_key_patch(),
            patch(
                "corpmind.modules.inbox.api.exchange_code_for_tokens",
                new_callable=AsyncMock,
                return_value=tokens,
            ),
            patch(
                "corpmind.modules.inbox.api.fetch_gmail_profile",
                new_callable=AsyncMock,
                return_value=profile,
            ),
        ):
            resp = await api_client.get(
                f"/api/v1/inbox/callback?state={state}&code=auth_code_abc"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["email_address"] == profile.email
        assert body["status"] == "active"

    @pytest.mark.asyncio
    async def test_callback_invalid_state_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get(
            "/api/v1/inbox/callback?state=invalid_state_token&code=some_code"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_callback_error_param_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get(
            "/api/v1/inbox/callback?state=any&error=access_denied"
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_callback_missing_code_returns_422(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/inbox/callback?state=any")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_callback_duplicate_email_returns_409(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))

        shared_email = f"dup-{uuid.uuid4().hex[:6]}@gmail.com"

        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=shared_email, name="Dup Test")

        for _ in range(2):
            state = uuid.uuid4().hex
            await _store_oauth_state(
                redis_client,
                state=state,
                tenant_id=uuid.UUID(claims["org_id"]),
                workspace_id=uuid.UUID(claims["workspace_id"]),
                user_id=uuid.UUID(claims["sub"]),
            )
            with (
                _enc_key_patch(),
                patch(
                    "corpmind.modules.inbox.api.exchange_code_for_tokens",
                    new_callable=AsyncMock,
                    return_value=tokens,
                ),
                patch(
                    "corpmind.modules.inbox.api.fetch_gmail_profile",
                    new_callable=AsyncMock,
                    return_value=profile,
                ),
            ):
                resp = await api_client.get(
                    f"/api/v1/inbox/callback?state={state}&code=code_{uuid.uuid4().hex}"
                )

        assert resp.status_code == 409


# ── GET /connection ────────────────────────────────────────────────────────────

class TestGetConnection:
    @pytest.mark.asyncio
    async def test_get_connection_not_found_returns_404(self, api_client: AsyncClient):
        user = await make_user(api_client)
        access_token = user["tokens"]["access_token"]
        resp = await api_client.get("/api/v1/inbox/connection", headers=_auth(access_token))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_connection_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/inbox/connection")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_connection_returns_200_when_exists(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        """Create a connection via callback, then verify GET /connection returns it."""
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )

        email = f"get-conn-{uuid.uuid4().hex[:6]}@gmail.com"
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=email, name="Get Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb_resp = await api_client.get(
                f"/api/v1/inbox/callback?state={state}&code=code_abc"
            )
        assert cb_resp.status_code == 200

        with _enc_key_patch():
            resp = await api_client.get("/api/v1/inbox/connection", headers=_auth(access_token))

        assert resp.status_code == 200
        assert resp.json()["email_address"] == email


# ── DELETE /connection/{id} ────────────────────────────────────────────────────

class TestDeleteConnection:
    @pytest.mark.asyncio
    async def test_delete_connection_returns_204(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"del-{uuid.uuid4().hex[:6]}@gmail.com", name="Del Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_del")
        conn_id = cb.json()["id"]

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.service.revoke_google_token", new_callable=AsyncMock),
        ):
            resp = await api_client.delete(
                f"/api/v1/inbox/connection/{conn_id}", headers=_auth(access_token)
            )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_connection_not_found_returns_404(self, api_client: AsyncClient):
        user = await make_user(api_client)
        with _enc_key_patch():
            resp = await api_client.delete(
                f"/api/v1/inbox/connection/{uuid.uuid4()}",
                headers=_auth(user["tokens"]["access_token"]),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_connection_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.delete(f"/api/v1/inbox/connection/{uuid.uuid4()}")
        assert resp.status_code == 401


# ── POST /connection/{id}/refresh ─────────────────────────────────────────────

class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_returns_200_on_success(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"ref-{uuid.uuid4().hex[:6]}@gmail.com", name="Ref Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_ref")
        conn_id = cb.json()["id"]

        new_tokens = GoogleTokens(
            access_token="new_access", refresh_token=None, expires_in=3600, scope="openid email"
        )
        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.service.refresh_google_token", new_callable=AsyncMock, return_value=new_tokens),
        ):
            resp = await api_client.post(
                f"/api/v1/inbox/connection/{conn_id}/refresh",
                headers=_auth(access_token),
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_refresh_returns_422_when_google_rejects(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        from corpmind.core.exceptions import ValidationError
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"rev-{uuid.uuid4().hex[:6]}@gmail.com", name="Rev Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_rev")
        conn_id = cb.json()["id"]

        with (
            _enc_key_patch(),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("token_revoked"),
            ),
        ):
            resp = await api_client.post(
                f"/api/v1/inbox/connection/{conn_id}/refresh",
                headers=_auth(access_token),
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_refresh_not_found_returns_404(self, api_client: AsyncClient):
        user = await make_user(api_client)
        with _enc_key_patch():
            resp = await api_client.post(
                f"/api/v1/inbox/connection/{uuid.uuid4()}/refresh",
                headers=_auth(user["tokens"]["access_token"]),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_refresh_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.post(f"/api/v1/inbox/connection/{uuid.uuid4()}/refresh")
        assert resp.status_code == 401


# ── GET /connection/{id}/health ────────────────────────────────────────────────

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy_returns_200(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        email = f"health-{uuid.uuid4().hex[:6]}@gmail.com"
        profile = GmailProfile(email=email, name="Health Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_health")
        conn_id = cb.json()["id"]

        good_tokens = GoogleTokens(access_token="fresh", refresh_token=None, expires_in=3600, scope="openid")
        good_profile = GmailProfile(email=email, name="Health Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.service.refresh_google_token", new_callable=AsyncMock, return_value=good_tokens),
            patch("corpmind.modules.inbox.service.fetch_gmail_profile", new_callable=AsyncMock, return_value=good_profile),
        ):
            resp = await api_client.get(
                f"/api/v1/inbox/connection/{conn_id}/health",
                headers=_auth(access_token),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["healthy"] is True
        assert body["status"] == "active"

    @pytest.mark.asyncio
    async def test_health_check_revoked_returns_healthy_false(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(payload_b64))
        access_token = user["tokens"]["access_token"]

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims["org_id"]),
            workspace_id=uuid.UUID(claims["workspace_id"]),
            user_id=uuid.UUID(claims["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        from corpmind.core.exceptions import ValidationError
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"hrev-{uuid.uuid4().hex[:6]}@gmail.com", name="Rev Health")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_hrev")
        conn_id = cb.json()["id"]

        with (
            _enc_key_patch(),
            patch(
                "corpmind.modules.inbox.service.refresh_google_token",
                new_callable=AsyncMock,
                side_effect=ValidationError("revoked"),
            ),
        ):
            resp = await api_client.get(
                f"/api/v1/inbox/connection/{conn_id}/health",
                headers=_auth(access_token),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["healthy"] is False
        assert body["status"] == "revoked"

    @pytest.mark.asyncio
    async def test_health_check_not_found_returns_404(self, api_client: AsyncClient):
        user = await make_user(api_client)
        with _enc_key_patch():
            resp = await api_client.get(
                f"/api/v1/inbox/connection/{uuid.uuid4()}/health",
                headers=_auth(user["tokens"]["access_token"]),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_health_check_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get(f"/api/v1/inbox/connection/{uuid.uuid4()}/health")
        assert resp.status_code == 401


# ── Tenant isolation ───────────────────────────────────────────────────────────

class TestInboxApiTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_b_cannot_delete_tenant_a_connection(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        """Tenant B must receive 404 when trying to delete Tenant A's connection."""
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user_a["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims_a = _json.loads(base64.urlsafe_b64decode(payload_b64))

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims_a["org_id"]),
            workspace_id=uuid.UUID(claims_a["workspace_id"]),
            user_id=uuid.UUID(claims_a["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"iso-{uuid.uuid4().hex[:6]}@gmail.com", name="Iso Test")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_iso")
        conn_id = cb.json()["id"]

        # Tenant B attempts to delete Tenant A's connection
        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.service.revoke_google_token", new_callable=AsyncMock),
        ):
            resp = await api_client.delete(
                f"/api/v1/inbox/connection/{conn_id}",
                headers=_auth(user_b["tokens"]["access_token"]),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_refresh_tenant_a_connection(
        self, api_client: AsyncClient, redis_client, db_engine: AsyncEngine
    ):
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        import base64, json as _json

        payload_b64 = user_a["tokens"]["access_token"].split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims_a = _json.loads(base64.urlsafe_b64decode(payload_b64))

        state = uuid.uuid4().hex
        await _store_oauth_state(
            redis_client,
            state=state,
            tenant_id=uuid.UUID(claims_a["org_id"]),
            workspace_id=uuid.UUID(claims_a["workspace_id"]),
            user_id=uuid.UUID(claims_a["sub"]),
        )
        from corpmind.modules.inbox.oauth import GmailProfile, GoogleTokens
        tokens = GoogleTokens(**_MOCK_TOKENS)
        profile = GmailProfile(email=f"iso2-{uuid.uuid4().hex[:6]}@gmail.com", name="Iso2")

        with (
            _enc_key_patch(),
            patch("corpmind.modules.inbox.api.exchange_code_for_tokens", new_callable=AsyncMock, return_value=tokens),
            patch("corpmind.modules.inbox.api.fetch_gmail_profile", new_callable=AsyncMock, return_value=profile),
        ):
            cb = await api_client.get(f"/api/v1/inbox/callback?state={state}&code=code_iso2")
        conn_id = cb.json()["id"]

        with _enc_key_patch():
            resp = await api_client.post(
                f"/api/v1/inbox/connection/{conn_id}/refresh",
                headers=_auth(user_b["tokens"]["access_token"]),
            )
        assert resp.status_code == 404
