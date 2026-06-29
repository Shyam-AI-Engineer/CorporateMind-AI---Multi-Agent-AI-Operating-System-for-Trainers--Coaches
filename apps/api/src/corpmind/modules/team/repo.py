"""Team module repositories — Sprint 30."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.team.models import ActivityFeedEntry, TaskComment, WorkspaceMember


class WorkspaceMemberRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, member: WorkspaceMember) -> WorkspaceMember:
        self._session.add(member)
        await self._session.flush()
        return member

    async def find_by_id(self, member_id: uuid.UUID) -> WorkspaceMember | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == member_id,
                WorkspaceMember.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        """Return the active (not removed) membership for a user, or None."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.tenant_id == ctx.org_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.removed_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, workspace_id: uuid.UUID) -> list[WorkspaceMember]:
        """Return all non-removed members, ordered by invited_at."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.tenant_id == ctx.org_id,
                WorkspaceMember.removed_at.is_(None),
            )
            .order_by(WorkspaceMember.invited_at)
        )
        return list(result.scalars().all())

    async def update_fields(self, member_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(WorkspaceMember)
            .where(
                WorkspaceMember.id == member_id,
                WorkspaceMember.tenant_id == ctx.org_id,
            )
            .values(**values)
        )


class ActivityFeedRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: ActivityFeedEntry) -> ActivityFeedEntry:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[ActivityFeedEntry], str | None]:
        """Return (items, next_cursor). Newest-first. cursor is opaque base64."""
        ctx = get_tenant_context()
        stmt = (
            select(ActivityFeedEntry)
            .where(
                ActivityFeedEntry.workspace_id == workspace_id,
                ActivityFeedEntry.tenant_id == ctx.org_id,
            )
            .order_by(ActivityFeedEntry.created_at.desc(), ActivityFeedEntry.id.desc())
        )

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (ActivityFeedEntry.created_at < cursor_ts)
                    | (
                        (ActivityFeedEntry.created_at == cursor_ts)
                        & (ActivityFeedEntry.id < cursor_id)
                    )
                )
            except Exception:
                pass  # invalid cursor → start from beginning

        result = await self._session.execute(stmt.limit(limit + 1))
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw = f"{last.created_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return items, next_cursor


class CommentRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, comment: TaskComment) -> TaskComment:
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def find_by_id(self, comment_id: uuid.UUID) -> TaskComment | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(TaskComment).where(
                TaskComment.id == comment_id,
                TaskComment.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_task(
        self, task_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[TaskComment]:
        """Oldest-first ordering for comments (chronological thread)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(TaskComment)
            .where(
                TaskComment.task_id == task_id,
                TaskComment.workspace_id == workspace_id,
                TaskComment.tenant_id == ctx.org_id,
            )
            .order_by(TaskComment.created_at)
        )
        return list(result.scalars().all())

    async def delete(self, comment_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        comment = await self.find_by_id(comment_id)
        if comment and comment.tenant_id == ctx.org_id:
            await self._session.delete(comment)
