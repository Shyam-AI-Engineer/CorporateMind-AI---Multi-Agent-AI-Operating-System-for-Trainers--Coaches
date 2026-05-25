"""Identity repository — all DB access for users, orgs, workspaces."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.identity.models import Org, User, Workspace

log = structlog.get_logger(__name__)


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        log.info("user.created", user_id=str(user.id), email=user.email)
        return user


class OrgRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, org_id: uuid.UUID) -> Org | None:
        result = await self._session.execute(select(Org).where(Org.id == org_id))
        return result.scalar_one_or_none()

    async def find_by_slug(self, slug: str) -> Org | None:
        result = await self._session.execute(select(Org).where(Org.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, org: Org) -> Org:
        self._session.add(org)
        await self._session.flush()
        log.info("org.created", org_id=str(org.id), slug=org.slug)
        return org


class WorkspaceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_default_for_org(self, org_id: uuid.UUID) -> Workspace | None:
        result = await self._session.execute(
            select(Workspace).where(Workspace.org_id == org_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, workspace: Workspace) -> Workspace:
        self._session.add(workspace)
        await self._session.flush()
        return workspace
