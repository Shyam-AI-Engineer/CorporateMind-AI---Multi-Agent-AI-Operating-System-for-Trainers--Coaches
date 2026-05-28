"""Social repository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.social.models import SocialPost


class SocialPostRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, post: SocialPost) -> SocialPost:
        self._session.add(post)
        await self._session.flush()
        return post

    async def find_by_id(self, post_id: uuid.UUID) -> SocialPost | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(SocialPost).where(
                SocialPost.id == post_id,
                SocialPost.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SocialPost]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(SocialPost)
            .where(
                SocialPost.tenant_id == ctx.org_id,
                SocialPost.workspace_id == workspace_id,
            )
            .order_by(SocialPost.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_workspace(self, workspace_id: uuid.UUID) -> int:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(func.count()).where(
                SocialPost.tenant_id == ctx.org_id,
                SocialPost.workspace_id == workspace_id,
            )
        )
        return result.scalar_one()

    async def delete(self, post_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            delete(SocialPost).where(
                SocialPost.id == post_id,
                SocialPost.tenant_id == ctx.org_id,
            )
        )
