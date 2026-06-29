"""Notification center services — Sprint 32.

Design constraints:
- No AI.  No LLM.  No Celery.  No background jobs.
- Notifications are informational only.  No email, no WhatsApp, no SMS.
- Users can only see/read/delete their own notifications (user_id scoped).
- Redis: list TTL 300s, unread-count TTL 60s.
- Cursor pagination (newest-first) on list.
- First page (no cursor, no filters) is cached; subsequent pages / filtered
  requests are not.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.notifications.models import Notification
from corpmind.modules.notifications.repo import NotificationRepo
from corpmind.modules.notifications.schemas import (
    NotificationIn,
    NotificationListPage,
    NotificationOut,
    UnreadCountOut,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300  # 5 minutes — matches default Redis TTL for lists
_COUNT_TTL = 60  # 1 minute — unread badge refreshes faster than full list


class PermissionDeniedError(Exception):
    """Raised when a user tries to access another user's notification."""


# ── Cache key helpers ─────────────────────────────────────────────────────────

def _list_key(org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:notifications:list:{user_id}"


def _count_key(org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:notifications:count:{user_id}"


# ── NotificationService ───────────────────────────────────────────────────────

class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = NotificationRepo(session)

    async def _invalidate(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Delete both list and count caches for this user's notification stream."""
        try:
            await get_redis().delete(
                _list_key(org_id, workspace_id, user_id),
                _count_key(org_id, workspace_id, user_id),
            )
        except Exception:
            pass

    async def create(self, data: NotificationIn) -> NotificationOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            user_id=data.user_id,
            notification_type=data.notification_type,
            title=data.title,
            message=data.message,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            priority=data.priority,
            is_read=False,
            read_at=None,
            extra_data=data.extra_data,
            created_at=now,
        )
        await self._repo.create(notification)
        await self._invalidate(ctx.org_id, data.workspace_id, data.user_id)

        log.info(
            "notifications.created",
            notification_id=str(notification.id),
            notification_type=data.notification_type,
            user_id=str(data.user_id),
            priority=data.priority,
        )
        return NotificationOut.model_validate(notification)

    async def mark_read(self, notification_id: uuid.UUID) -> NotificationOut:
        ctx = get_tenant_context()
        notification = await self._repo.find_by_id(notification_id)
        if notification is None:
            raise NotFoundError(f"Notification {notification_id} not found")
        if notification.user_id != ctx.user_id:
            raise PermissionDeniedError(
                "You can only mark your own notifications as read"
            )
        if notification.is_read:
            return NotificationOut.model_validate(notification)

        now = datetime.now(UTC)
        await self._repo.update_fields(notification_id, is_read=True, read_at=now)
        notification.is_read = True
        notification.read_at = now

        await self._invalidate(ctx.org_id, notification.workspace_id, ctx.user_id)
        log.info("notifications.read", notification_id=str(notification_id))
        return NotificationOut.model_validate(notification)

    async def mark_all_read(self, workspace_id: uuid.UUID) -> int:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        count = await self._repo.mark_all_read_for_user(workspace_id, ctx.user_id, now)
        await self._invalidate(ctx.org_id, workspace_id, ctx.user_id)
        log.info(
            "notifications.all_read",
            workspace_id=str(workspace_id),
            count=count,
        )
        return count

    async def delete(self, notification_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        notification = await self._repo.find_by_id(notification_id)
        if notification is None:
            raise NotFoundError(f"Notification {notification_id} not found")
        if notification.user_id != ctx.user_id:
            raise PermissionDeniedError("You can only delete your own notifications")

        workspace_id = notification.workspace_id
        await self._repo.delete_by_id(notification_id)
        await self._invalidate(ctx.org_id, workspace_id, ctx.user_id)
        log.info("notifications.deleted", notification_id=str(notification_id))

    async def unread_count(self, workspace_id: uuid.UUID) -> UnreadCountOut:
        ctx = get_tenant_context()
        key = _count_key(ctx.org_id, workspace_id, ctx.user_id)
        try:
            cached = await get_redis().get(key)
            if cached is not None:
                return UnreadCountOut(count=int(cached))
        except Exception:
            pass

        count = await self._repo.unread_count(workspace_id, ctx.user_id)
        try:
            await get_redis().set(key, str(count), ex=_COUNT_TTL)
        except Exception:
            pass
        return UnreadCountOut(count=count)

    async def list_notifications(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
        is_read: bool | None = None,
        priority: str | None = None,
        entity_type: str | None = None,
    ) -> NotificationListPage:
        ctx = get_tenant_context()
        is_first_page = (
            cursor is None
            and is_read is None
            and priority is None
            and entity_type is None
        )

        if is_first_page:
            key = _list_key(ctx.org_id, workspace_id, ctx.user_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return NotificationListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._repo.list_page(
            workspace_id, ctx.user_id, limit, cursor, is_read, priority, entity_type
        )
        result = NotificationListPage(
            items=[NotificationOut.model_validate(n) for n in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )

        if is_first_page:
            try:
                await get_redis().set(
                    _list_key(ctx.org_id, workspace_id, ctx.user_id),
                    result.model_dump_json(),
                    ex=_LIST_TTL,
                )
            except Exception:
                pass

        return result
