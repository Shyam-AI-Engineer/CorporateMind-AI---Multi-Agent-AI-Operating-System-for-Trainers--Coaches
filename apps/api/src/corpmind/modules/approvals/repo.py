"""Approval workflow repositories — Sprint 31."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.approvals.models import ApprovalRequest, ApprovalTimelineEvent


class ApprovalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, request: ApprovalRequest) -> ApprovalRequest:
        self._session.add(request)
        await self._session.flush()
        return request

    async def find_by_id(self, approval_id: uuid.UUID) -> ApprovalRequest | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, approval_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        status: str | None = None,
        priority: str | None = None,
        assigned_reviewer: str | None = None,
    ) -> tuple[list[ApprovalRequest], str | None]:
        """Cursor-paginated list, newest-first.  Filters applied when provided."""
        ctx = get_tenant_context()
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workspace_id == workspace_id,
                ApprovalRequest.tenant_id == ctx.org_id,
            )
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        )

        if status:
            stmt = stmt.where(ApprovalRequest.status == status)
        if priority:
            stmt = stmt.where(ApprovalRequest.priority == priority)
        if assigned_reviewer:
            stmt = stmt.where(ApprovalRequest.assigned_reviewer == assigned_reviewer)

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (ApprovalRequest.created_at < cursor_ts)
                    | (
                        (ApprovalRequest.created_at == cursor_ts)
                        & (ApprovalRequest.id < cursor_id)
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

    async def list_my_reviews_page(
        self,
        reviewer_user_id: str,
        workspace_id: uuid.UUID,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[ApprovalRequest], str | None]:
        """Cursor-paginated requests assigned to a specific reviewer."""
        ctx = get_tenant_context()
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.tenant_id == ctx.org_id,
                ApprovalRequest.workspace_id == workspace_id,
                ApprovalRequest.assigned_reviewer == reviewer_user_id,
            )
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        )

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (ApprovalRequest.created_at < cursor_ts)
                    | (
                        (ApprovalRequest.created_at == cursor_ts)
                        & (ApprovalRequest.id < cursor_id)
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


class ApprovalTimelineRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, event: ApprovalTimelineEvent) -> ApprovalTimelineEvent:
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_request(
        self, approval_id: uuid.UUID
    ) -> list[ApprovalTimelineEvent]:
        """Oldest-first ordering (chronological audit trail)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(ApprovalTimelineEvent)
            .where(
                ApprovalTimelineEvent.approval_request_id == approval_id,
                ApprovalTimelineEvent.tenant_id == ctx.org_id,
            )
            .order_by(ApprovalTimelineEvent.occurred_at)
        )
        return list(result.scalars().all())
