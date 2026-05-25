"""Identity service — registration, login, token refresh."""

from __future__ import annotations

import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import AuthenticationError, ConflictError
from corpmind.core.security import (
    create_access_token,
    create_refresh_token,
    generate_jti,
    hash_password,
    verify_password,
)
from corpmind.modules.identity.models import Org, User, Workspace
from corpmind.modules.identity.repo import OrgRepo, UserRepo, WorkspaceRepo
from corpmind.modules.identity.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

log = structlog.get_logger(__name__)


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepo(session)
        self._org_repo = OrgRepo(session)
        self._ws_repo = WorkspaceRepo(session)

    async def register(self, req: RegisterRequest) -> TokenResponse:
        existing = await self._user_repo.find_by_email(req.email)
        if existing:
            raise ConflictError(f"Email {req.email} is already registered")

        slug = _slugify(req.org_name)
        if await self._org_repo.find_by_slug(slug):
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        org = Org(name=req.org_name, slug=slug, plan_tier="starter")
        await self._org_repo.create(org)

        workspace = Workspace(org_id=org.id, name=req.org_name)
        await self._ws_repo.create(workspace)

        user = User(
            org_id=org.id,
            email=req.email,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
            role="OrgAdmin",
        )
        await self._user_repo.create(user)

        return self._issue_tokens(user, workspace)

    async def login(self, req: LoginRequest) -> TokenResponse:
        user = await self._user_repo.find_by_email(req.email)
        if not user or not verify_password(req.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        workspace = await self._ws_repo.find_default_for_org(user.org_id)
        if not workspace:
            raise AuthenticationError("No active workspace found")

        log.info("user.login", user_id=str(user.id))
        return self._issue_tokens(user, workspace)

    def _issue_tokens(self, user: User, workspace: Workspace) -> TokenResponse:
        from corpmind.core.config import settings

        claims = {
            "sub": str(user.id),
            "org_id": str(user.org_id),
            "workspace_id": str(workspace.id),
            "role": user.role,
            "plan_tier": "starter",
        }
        access = create_access_token(claims)
        jti = generate_jti()
        refresh = create_refresh_token(str(user.id), jti)

        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]
