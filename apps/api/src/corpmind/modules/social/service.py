"""Social service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.social.models import SocialPost
from corpmind.modules.social.repo import SocialPostRepo
from corpmind.modules.social.schemas import (
    SocialPostCreate,
    SocialPostListOut,
    SocialPostOut,
)

log = structlog.get_logger(__name__)

_DELETABLE_STATUSES = frozenset({"draft", "scheduled"})


class SocialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SocialPostRepo(session)

    async def schedule_post(self, req: SocialPostCreate) -> SocialPostOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        status = "scheduled" if req.scheduled_at and req.scheduled_at > now else "draft"

        post = SocialPost(
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            channel=req.channel,
            content=req.content,
            hashtags=req.hashtags,
            status=status,
            scheduled_at=req.scheduled_at,
        )
        post = await self._repo.create(post)
        await self._session.commit()

        log.info(
            "social.post.created",
            post_id=str(post.id),
            channel=post.channel,
            status=post.status,
            tenant_id=str(ctx.org_id),
        )
        return SocialPostOut.model_validate(post)

    async def list_posts(
        self,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> SocialPostListOut:
        posts = await self._repo.list_by_workspace(workspace_id, limit=limit, offset=offset)
        total = await self._repo.count_by_workspace(workspace_id)
        return SocialPostListOut(
            items=[SocialPostOut.model_validate(p) for p in posts],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def delete_post(self, post_id: uuid.UUID) -> None:
        post = await self._repo.find_by_id(post_id)
        if not post:
            raise NotFoundError(f"Social post {post_id} not found")
        if post.status not in _DELETABLE_STATUSES:
            raise ConflictError(
                f"Cannot delete a post with status '{post.status}'"
            )
        await self._repo.delete(post_id)
        await self._session.commit()
        log.info("social.post.deleted", post_id=str(post_id))
