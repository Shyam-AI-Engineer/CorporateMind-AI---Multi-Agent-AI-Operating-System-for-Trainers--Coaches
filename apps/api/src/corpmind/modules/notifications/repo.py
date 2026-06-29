"""Notification center repositories — Sprint 32."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.notifications.models import Notification


class NotificationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def find_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, notification_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def mark_all_read_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        read_at: datetime,
    ) -> int:
        ctx = get_tenant_context()
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.tenant_id == ctx.org_id,
                Notification.workspace_id == workspace_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=read_at)
            .returning(Notification.id)
        )
        return len(result.fetchall())

    async def delete_by_id(self, notification_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            delete(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == ctx.org_id,
            )
        )

    async def unread_count(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(func.count()).where(
                Notification.tenant_id == ctx.org_id,
                Notification.workspace_id == workspace_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return result.scalar() or 0

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        is_read: bool | None = None,
        priority: str | None = None,
        entity_type: str | None = None,
    ) -> tuple[list[Notification], str | None]:
        """Cursor-paginated list, newest-first."""
        ctx = get_tenant_context()
        stmt = (
            select(Notification)
            .where(
                Notification.tenant_id == ctx.org_id,
                Notification.workspace_id == workspace_id,
                Notification.user_id == user_id,
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        )

        if is_read is not None:
            stmt = stmt.where(Notification.is_read == is_read)
        if priority:
            stmt = stmt.where(Notification.priority == priority)
        if entity_type:
            stmt = stmt.where(Notification.entity_type == entity_type)

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (Notification.created_at < cursor_ts)
                    | (
                        (Notification.created_at == cursor_ts)
                        & (Notification.id < cursor_id)
                    )
                )
            except Exception:
                pass

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
