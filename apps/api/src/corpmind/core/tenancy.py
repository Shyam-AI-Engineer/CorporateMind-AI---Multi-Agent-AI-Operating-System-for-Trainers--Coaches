"""Tenant context isolation.

Every authenticated request flows through TenantMiddleware, which:
1. Decodes the JWT and extracts org_id + workspace_id.
2. Sets TenantContext (a contextvars.ContextVar) — used by repos and services.
3. After the DB session is acquired, fires SET LOCAL app.tenant_id = <id>
   so Postgres RLS can enforce row-level isolation.

Services and repos MUST NOT accept tenant_id as a parameter.
They read it from get_tenant_context().
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from corpmind.core.exceptions import AuthenticationError

log = structlog.get_logger(__name__)

_tenant_ctx: contextvars.ContextVar["TenantContext | None"] = contextvars.ContextVar(
    "_tenant_ctx", default=None
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    request_id: str
    ai_budget_inr: float = 400.0
    plan_tier: str = "starter"  # starter | growth | enterprise

    @property
    def tenant_id(self) -> uuid.UUID:
        """Alias for org_id — used in RLS and Redis key prefixes."""
        return self.org_id


def get_tenant_context() -> TenantContext:
    """Return the current request's tenant context.

    Raises AuthenticationError if called outside a tenant-bound request.
    """
    ctx = _tenant_ctx.get()
    if ctx is None:
        raise AuthenticationError("No tenant context — is this request authenticated?")
    return ctx


def set_tenant_context(ctx: TenantContext) -> contextvars.Token["TenantContext | None"]:
    return _tenant_ctx.set(ctx)


def clear_tenant_context(token: contextvars.Token["TenantContext | None"]) -> None:
    _tenant_ctx.reset(token)


# ── Public-path bypass ────────────────────────────────────────────────────────
_PUBLIC_PREFIXES = (
    "/healthz",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/identity/login",
    "/api/v1/identity/register",
    "/api/v1/identity/refresh",
    "/api/v1/identity/oauth",
    # Inbound webhooks verify their own HMAC before parsing
    "/api/v1/webhooks/",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant context from JWT and bind it for the request lifetime."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for public paths
        if any(request.url.path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        try:
            ctx = await _extract_context(request)
        except AuthenticationError as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"code": "unauthenticated", "message": str(exc), "request_id": ""},
            )

        token = set_tenant_context(ctx)
        request.state.request_id = ctx.request_id  # available to exception handlers
        structlog.contextvars.bind_contextvars(
            tenant_id=str(ctx.org_id),
            request_id=ctx.request_id,
            user_id=str(ctx.user_id),
        )

        try:
            response = await call_next(request)
        finally:
            clear_tenant_context(token)
            structlog.contextvars.clear_contextvars()

        return response


async def _extract_context(request: Request) -> TenantContext:
    """Decode JWT from Authorization header and build TenantContext."""
    from corpmind.core.security import decode_access_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or malformed Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()
    claims = decode_access_token(token)

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    return TenantContext(
        org_id=uuid.UUID(claims["org_id"]),
        workspace_id=uuid.UUID(claims["workspace_id"]),
        user_id=uuid.UUID(claims["sub"]),
        role=claims.get("role", "trainer"),
        request_id=request_id,
        ai_budget_inr=float(claims.get("ai_budget_inr", 400.0)),
        plan_tier=claims.get("plan_tier", "starter"),
    )
