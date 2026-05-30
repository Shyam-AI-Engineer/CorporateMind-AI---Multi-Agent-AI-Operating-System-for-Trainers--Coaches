"""Identity module API routes: registration, login, token refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_public_session, get_session
from corpmind.modules.billing.service import BillingService
from corpmind.modules.identity.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from corpmind.modules.identity.service import IdentityService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    session: AsyncSession = Depends(get_public_session),
) -> TokenResponse:
    svc = IdentityService(session, billing_service=BillingService(session))
    return await svc.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
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
