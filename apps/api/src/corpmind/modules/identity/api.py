"""Identity module API routes: registration, login, token refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.config import settings
from corpmind.core.database import get_public_session, get_session
from corpmind.core.rate_limit import make_rate_limiter
from corpmind.modules.billing.service import BillingService
from corpmind.modules.identity.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
    WorkspaceBookingWebhookOut,
)
from corpmind.modules.identity.service import IdentityService

router = APIRouter()

_login_rl = make_rate_limiter(
    "login",
    max_requests=settings.RATE_LIMIT_LOGIN_MAX,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW,
)
_register_rl = make_rate_limiter(
    "register",
    max_requests=settings.RATE_LIMIT_REGISTER_MAX,
    window_seconds=settings.RATE_LIMIT_REGISTER_WINDOW,
)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    _rl: None = Depends(_register_rl),
    session: AsyncSession = Depends(get_public_session),
) -> TokenResponse:
    svc = IdentityService(session, billing_service=BillingService(session))
    return await svc.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    _rl: None = Depends(_login_rl),
    session: AsyncSession = Depends(get_public_session),
) -> TokenResponse:
    svc = IdentityService(session)
    return await svc.login(req)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    req: RefreshRequest,
    session: AsyncSession = Depends(get_public_session),
) -> TokenResponse:
    svc = IdentityService(session)
    return await svc.refresh(req.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    from corpmind.core.tenancy import get_tenant_context
    from corpmind.modules.identity.repo import UserRepo

    ctx = get_tenant_context()
    repo = UserRepo(session)
    user = await repo.find_by_id(ctx.user_id)
    if not user:
        from corpmind.core.exceptions import NotFoundError
        raise NotFoundError("User not found")
    return UserOut.model_validate(user)


# ── Sprint 14: workspace booking-webhook settings ─────────────────────────────

@router.get(
    "/workspace/booking-webhook",
    response_model=WorkspaceBookingWebhookOut,
    summary="Get the booking webhook URL and secret for this workspace",
)
async def get_booking_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceBookingWebhookOut:
    """Return the booking webhook URL and the current HMAC secret.

    The trainer copies both into their booking tool (Calendly, Cal.com, etc.).
    The secret is returned in full so the trainer can view/copy it at any time.
    Regenerate it via the /regenerate endpoint to rotate.
    """
    from corpmind.core.tenancy import get_tenant_context
    from sqlalchemy import select as sa_select

    from corpmind.modules.identity.models import Workspace

    ctx = get_tenant_context()
    result = await session.execute(
        sa_select(Workspace).where(Workspace.id == ctx.workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        from corpmind.core.exceptions import NotFoundError
        raise NotFoundError("Workspace not found")

    webhook_url = (
        f"{str(request.base_url).rstrip('/')}"
        f"/api/v1/webhooks/booking/{ctx.workspace_id}"
    )
    return WorkspaceBookingWebhookOut(
        workspace_id=ctx.workspace_id,
        webhook_url=webhook_url,
        has_secret=workspace.booking_webhook_secret is not None,
        secret=workspace.booking_webhook_secret,
    )


@router.post(
    "/workspace/booking-webhook/regenerate",
    response_model=WorkspaceBookingWebhookOut,
    summary="Rotate the booking webhook secret (invalidates any existing secret)",
)
async def regenerate_booking_webhook_secret(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceBookingWebhookOut:
    """Generate a new HMAC-SHA256 secret for the booking webhook.

    The previous secret is immediately invalidated — update your booking tool
    before regenerating if there are active webhook subscriptions.
    """
    import secrets as _secrets

    from corpmind.core.tenancy import get_tenant_context
    from sqlalchemy import select as sa_select, update as sa_update

    from corpmind.modules.identity.models import Workspace

    ctx = get_tenant_context()
    new_secret = _secrets.token_urlsafe(32)

    await session.execute(
        sa_update(Workspace)
        .where(Workspace.id == ctx.workspace_id)
        .values(booking_webhook_secret=new_secret)
    )

    # Re-fetch to confirm write before returning
    result = await session.execute(
        sa_select(Workspace).where(Workspace.id == ctx.workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        from corpmind.core.exceptions import NotFoundError
        raise NotFoundError("Workspace not found")

    webhook_url = (
        f"{str(request.base_url).rstrip('/')}"
        f"/api/v1/webhooks/booking/{ctx.workspace_id}"
    )
    return WorkspaceBookingWebhookOut(
        workspace_id=ctx.workspace_id,
        webhook_url=webhook_url,
        has_secret=True,
        secret=new_secret,
    )
