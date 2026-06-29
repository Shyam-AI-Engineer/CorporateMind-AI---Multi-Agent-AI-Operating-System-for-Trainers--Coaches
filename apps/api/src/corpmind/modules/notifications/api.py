"""Notification center API — Sprint 32.

Endpoints:
  GET  /notifications                — list current user's notifications
  GET  /notifications/unread-count   — unread count for current user
  POST /notifications                — create notification (internal observer API)
  PATCH /notifications/read-all      — mark all as read for workspace
  PATCH /notifications/{id}/read     — mark a single notification as read
  DELETE /notifications/{id}         — delete a notification

NOTE: static routes (/unread-count, /read-all) are registered before the
parameterized route (/{id}/read, /{id}) so FastAPI matches static segments first.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.notifications.schemas import (
    NotificationIn,
    NotificationListPage,
    NotificationOut,
    UnreadCountOut,
)
from corpmind.modules.notifications.service import (
    NotificationService,
    PermissionDeniedError,
)

router = APIRouter()


def _raise_permission(exc: PermissionDeniedError) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _raise_not_found(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/unread-count", response_model=UnreadCountOut)
async def get_unread_count(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> UnreadCountOut:
    """Return the unread notification count for the current user."""
    return await NotificationService(session).unread_count(workspace_id)


@router.patch("/read-all", response_model=dict)
async def mark_all_read(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mark all unread notifications for the current user as read."""
    count = await NotificationService(session).mark_all_read(workspace_id)
    return {"updated": count}


@router.get("", response_model=NotificationListPage)
async def list_notifications(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    is_read: bool | None = Query(default=None),
    priority: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> NotificationListPage:
    """Return cursor-paginated notifications for the current user, newest-first."""
    return await NotificationService(session).list_notifications(
        workspace_id, cursor, limit, is_read, priority, entity_type
    )


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
async def create_notification(
    data: NotificationIn,
    session: AsyncSession = Depends(get_session),
) -> NotificationOut:
    """Create a notification (called by event observers when domain events fire)."""
    return await NotificationService(session).create(data)


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> NotificationOut:
    """Mark a single notification as read."""
    try:
        return await NotificationService(session).mark_read(notification_id)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except Exception as exc:
        _raise_not_found(exc)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a notification (ownership enforced)."""
    try:
        await NotificationService(session).delete(notification_id)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except Exception as exc:
        _raise_not_found(exc)
