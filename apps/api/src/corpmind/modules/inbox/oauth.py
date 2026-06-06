"""Google OAuth helpers for Gmail inbox connection.

State management (CSRF protection)
────────────────────────────────────
generate_oauth_state()  → stores tenant payload in Redis; returns opaque random token
consume_oauth_state()   → atomic GETDEL (single-use); returns payload or None on miss

Google API calls
────────────────
build_authorization_url()    → constructs the Google consent-page redirect URL
exchange_code_for_tokens()   → POSTs authorization code to Google token endpoint
fetch_gmail_profile()        → GETs /userinfo to retrieve the connected email address

Security model
──────────────
The state token is a 32-byte cryptographically random URL-safe base64 string (256 bits
of entropy).  It is opaque — no tenant or user information is encoded in it.  The
payload (tenant_id, workspace_id, user_id) lives server-side only, keyed by the token
in Redis with a 10-minute TTL.  GETDEL makes the token single-use, preventing replays.

GOOGLE_CLIENT_SECRET is read from settings and used only in the server-side token
exchange — it is never included in any URL or response returned to the browser.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import structlog

from corpmind.core.config import settings
from corpmind.core.exceptions import ValidationError
from corpmind.core.redis import get_redis

log = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_STATE_KEY_PREFIX = "oauth:inbox:state:"
# 10 minutes — matches Google's authorization code validity window.
_STATE_TTL_SECONDS = 600

# Gmail scopes requested on every connect.  openid+email for the profile call;
# gmail.readonly for future inbox sync.  offline = access_type param (see URL builder).
GMAIL_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
]

_GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"
_GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"


# ── Data transfer types ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OAuthStatePayload:
    """Tenant context recovered from a valid state token."""

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID


@dataclass(frozen=True)
class GoogleTokens:
    """Tokens returned by Google's token endpoint."""

    access_token: str
    refresh_token: str | None  # None when prompt!=consent or user already authorized
    expires_in: int | None
    scope: str


@dataclass(frozen=True)
class GmailProfile:
    """Minimal profile returned by Google's userinfo endpoint."""

    email: str
    name: str | None


# ── OAuth state management ─────────────────────────────────────────────────────

async def generate_oauth_state(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """Generate a CSRF-safe state token and store its payload in Redis.

    Returns a URL-safe base64 string (32 random bytes, padding stripped).
    The payload lives server-side only — the token itself is fully opaque.
    """
    token = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    payload = json.dumps(
        {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
        }
    )
    await get_redis().set(f"{_STATE_KEY_PREFIX}{token}", payload, ex=_STATE_TTL_SECONDS)
    return token


async def consume_oauth_state(state: str) -> OAuthStatePayload | None:
    """Validate and consume a state token (single-use, atomic).

    Uses Redis GETDEL — reads and deletes in one operation so concurrent
    callback requests with the same token cannot both succeed.

    Returns None when the token is missing, expired, or already consumed.
    """
    raw = await get_redis().getdel(f"{_STATE_KEY_PREFIX}{state}")
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return OAuthStatePayload(
            tenant_id=uuid.UUID(data["tenant_id"]),
            workspace_id=uuid.UUID(data["workspace_id"]),
            user_id=uuid.UUID(data["user_id"]),
        )
    except (KeyError, ValueError, TypeError):
        # Malformed payload — treat as invalid rather than crashing
        log.error("inbox.oauth.malformed_state_payload")
        return None


# ── Authorization URL construction ────────────────────────────────────────────

def build_authorization_url(state: str) -> str:
    """Construct the Google OAuth 2.0 authorization URL.

    access_type=offline  → request a refresh_token alongside the access_token.
    prompt=consent       → always show the consent screen; without it Google may
                           skip consent on repeat authorizations and omit the
                           refresh_token, leaving us with a non-renewable connection.
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{_GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


# ── Google API calls ───────────────────────────────────────────────────────────

async def exchange_code_for_tokens(code: str) -> GoogleTokens:
    """Exchange a Google authorization code for access + refresh tokens.

    The client_secret is used here (server-side only) and never leaves this function.

    Raises:
        ValidationError: Google returned a non-200 status or an error field.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        log.warning("gmail.oauth.token_exchange_failed", http_status=resp.status_code)
        raise ValidationError(
            "Google token exchange failed — authorization code may have expired or been reused"
        )

    data = resp.json()
    if "error" in data:
        raise ValidationError(
            f"Google OAuth error: {data.get('error_description', data['error'])}"
        )

    return GoogleTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope", ""),
    )


async def fetch_gmail_profile(access_token: str) -> GmailProfile:
    """Retrieve the Gmail account email and display name via Google's userinfo endpoint.

    Raises:
        ValidationError: Request failed or the response lacked an email field.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            _GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if resp.status_code != 200:
        log.warning("gmail.oauth.userinfo_failed", http_status=resp.status_code)
        raise ValidationError("Failed to retrieve Gmail profile from Google")

    data = resp.json()
    email = data.get("email")
    if not email:
        raise ValidationError("Google userinfo response did not include an email address")

    return GmailProfile(email=email, name=data.get("name"))


async def refresh_google_token(refresh_token: str) -> GoogleTokens:
    """Exchange a refresh token for a new access token.

    Uses grant_type=refresh_token — no code or redirect_uri required.
    Google may also return a rotated refresh_token; callers should persist it
    if present.

    Raises:
        ValidationError: Google rejected the refresh token (revoked, expired, or
                         invalid — all manifest as the same HTTP 400 from Google).
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_ENDPOINT,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        data = resp.json() if resp.content else {}
        description = (
            data.get("error_description") or data.get("error") or "token refresh failed"
        )
        log.warning(
            "gmail.oauth.token_refresh_failed",
            http_status=resp.status_code,
            error=data.get("error"),
        )
        raise ValidationError(f"Google token refresh failed: {description}")

    data = resp.json()
    if "error" in data:
        raise ValidationError(
            f"Google OAuth error: {data.get('error_description', data['error'])}"
        )

    return GoogleTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),  # present only on token rotation
        expires_in=data.get("expires_in"),
        scope=data.get("scope", ""),
    )


async def revoke_google_token(token: str) -> None:
    """Revoke a Google OAuth token (best-effort, never raises).

    Called before deleting a local connection so the OAuth grant is cleaned up
    on Google's side.  Silently swallows all errors — the caller must delete
    the local connection record regardless of whether revocation succeeds.
    Google's /revoke endpoint accepts both access and refresh tokens.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_GOOGLE_REVOKE_ENDPOINT, params={"token": token})
        if resp.status_code != 200:
            log.warning("gmail.oauth.revocation_failed", http_status=resp.status_code)
    except Exception:
        log.warning("gmail.oauth.revocation_network_error")
