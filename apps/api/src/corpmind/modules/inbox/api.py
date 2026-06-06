"""Inbox module REST API — Gmail OAuth connect and callback.

Endpoint overview
─────────────────
GET /connect   Authenticated.  Generates a CSRF state token and issues a 302
               redirect to Google's consent page.  Requires a valid JWT (the
               TenantMiddleware runs for this path).

GET /callback  Public.  Receives Google's redirect with ?code=&state=.
               Validates the state token, exchanges the code for tokens,
               fetches the Gmail profile, and creates an InboxConnection via
               InboxService.  /api/v1/inbox/callback is in _PUBLIC_PREFIXES so
               TenantMiddleware is bypassed — the handler reconstructs tenant
               context from the Redis state payload instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.config import settings
from corpmind.core.database import get_public_session, get_session, set_rls_tenant
from corpmind.core.exceptions import AuthenticationError, ValidationError
from corpmind.core.tenancy import (
    TenantContext,
    clear_tenant_context,
    get_tenant_context,
    set_tenant_context,
)
from corpmind.modules.inbox.oauth import (
    OAuthStatePayload,
    build_authorization_url,
    consume_oauth_state,
    exchange_code_for_tokens,
    fetch_gmail_profile,
    generate_oauth_state,
)
from corpmind.modules.inbox.schemas import ConnectionHealthOut, InboxConnectionCreate, InboxConnectionOut
from corpmind.modules.inbox.service import InboxService

log = structlog.get_logger(__name__)

router = APIRouter()


# ── Connect ────────────────────────────────────────────────────────────────────

@router.get(
    "/connect",
    summary="Initiate Gmail inbox connection via Google OAuth",
    response_class=RedirectResponse,
    status_code=302,
)
async def connect(
    workspace_id: uuid.UUID | None = Query(default=None),
) -> RedirectResponse:
    """Generate a CSRF state token and redirect to Google's consent page.

    workspace_id selects which workspace owns the connection.
    Defaults to the caller's current workspace from the JWT.
    Raises 422 if GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI are not configured.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise ValidationError("Google OAuth is not configured on this server")

    ctx = get_tenant_context()
    ws_id = workspace_id or ctx.workspace_id
    state = await generate_oauth_state(ctx.org_id, ws_id, ctx.user_id)
    auth_url = build_authorization_url(state)

    log.info("inbox.oauth.connect_initiated", tenant_id=str(ctx.org_id), workspace_id=str(ws_id))
    return RedirectResponse(url=auth_url, status_code=302)


# ── Callback ───────────────────────────────────────────────────────────────────

@router.get(
    "/callback",
    summary="Google OAuth callback — exchange code and create inbox connection",
    response_model=InboxConnectionOut,
)
async def callback(
    request: Request,
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_public_session),
) -> InboxConnectionOut:
    """Validate state, exchange authorization code, persist encrypted connection.

    Google sends ?error=access_denied when the user cancels consent.
    Missing code is treated as a protocol error.
    Invalid or expired state raises 401 to prevent state-guessing attacks.
    """
    if error:
        raise AuthenticationError(f"Google OAuth denied: {error}")
    if not code:
        raise ValidationError("Missing authorization code in OAuth callback")

    payload = await consume_oauth_state(state)
    if payload is None:
        log.warning("inbox.oauth.invalid_state")
        raise AuthenticationError("Invalid or expired OAuth state token")

    return await _complete_connection(request, payload, code, session)


# ── Connection lifecycle ───────────────────────────────────────────────────────

@router.get(
    "/connection",
    response_model=InboxConnectionOut,
    summary="Get the active inbox connection for this workspace",
)
async def get_connection(
    session: AsyncSession = Depends(get_session),
) -> InboxConnectionOut:
    """Return the connected Gmail inbox for the caller's current workspace.

    Raises 404 when no connection exists.  Never exposes tokens or encrypted fields.
    """
    return await InboxService(session).get_workspace_connection()


@router.delete(
    "/connection/{connection_id}",
    status_code=204,
    summary="Disconnect inbox connection and revoke Google OAuth tokens",
)
async def disconnect_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke Google OAuth tokens and delete the connection.

    Token revocation is best-effort — the connection is always deleted locally.
    Raises 404 when the connection is not found for this tenant (no cross-tenant leak).
    """
    await InboxService(session).disconnect_connection(connection_id)


@router.post(
    "/connection/{connection_id}/refresh",
    response_model=InboxConnectionOut,
    summary="Refresh the Gmail access token for an inbox connection",
)
async def refresh_connection_token(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> InboxConnectionOut:
    """Obtain a new access token using the stored refresh token.

    On success returns the updated connection (with new token_expiry_at).
    Raises 422 when Google rejects the refresh token — the connection status
    is also set to revoked so the UI can surface a re-authorization prompt.
    """
    return await InboxService(session).refresh_access_token(connection_id)


@router.get(
    "/connection/{connection_id}/health",
    response_model=ConnectionHealthOut,
    summary="Check the health of an inbox connection",
)
async def check_connection_health(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ConnectionHealthOut:
    """Validate the connection by refreshing tokens and probing the Gmail API.

    Always writes the result to the DB (status, last_error, fresh access token).
    Returns healthy=True when both refresh and Gmail profile succeed.
    Raises 404 when the connection is not found for this tenant.
    """
    return await InboxService(session).check_connection_health(connection_id)


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _complete_connection(
    request: Request,
    payload: OAuthStatePayload,
    code: str,
    session: AsyncSession,
) -> InboxConnectionOut:
    """Exchange the code, fetch the profile, and persist the InboxConnection.

    Reconstructs TenantContext from the state payload (not from any URL parameter)
    and activates Postgres RLS before the first DB query.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    ctx = TenantContext(
        org_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        user_id=payload.user_id,
        role="trainer",
        request_id=request_id,
    )
    ctx_token = set_tenant_context(ctx)
    try:
        await set_rls_tenant(session, ctx.org_id)

        tokens = await exchange_code_for_tokens(code)
        if not tokens.refresh_token:
            raise ValidationError(
                "Google did not return a refresh token — "
                "re-authorize with prompt=consent to request offline access"
            )

        profile = await fetch_gmail_profile(tokens.access_token)

        token_expiry: datetime | None = None
        if tokens.expires_in is not None:
            token_expiry = datetime.now(UTC) + timedelta(seconds=tokens.expires_in)

        req = InboxConnectionCreate(
            workspace_id=ctx.workspace_id,
            provider="gmail",
            email_address=profile.email,
            refresh_token=tokens.refresh_token,
            access_token=tokens.access_token,
            scopes=tokens.scope,
            token_expiry_at=token_expiry,
            connected_by=ctx.user_id,
        )
        connection = await InboxService(session).create_connection(req)

        log.info(
            "inbox.oauth.connection_created",
            connection_id=str(connection.id),
            provider="gmail",
            tenant_id=str(ctx.org_id),
        )
        return connection
    finally:
        clear_tenant_context(ctx_token)
