"""Operations repository — Sprint 29."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.operations.models import BusinessTask


class BusinessTaskRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, task: BusinessTask) -> BusinessTask:
        self._session.add(task)
        await self._session.flush()
        return task

    async def find_by_id(self, task_id: uuid.UUID) -> BusinessTask | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(BusinessTask).where(
                BusinessTask.id == task_id,
                BusinessTask.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, workspace_id: uuid.UUID) -> list[BusinessTask]:
        """Return all non-deleted tasks for a workspace, newest first."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(BusinessTask)
            .where(
                BusinessTask.workspace_id == workspace_id,
                BusinessTask.tenant_id == ctx.org_id,
                BusinessTask.status != "deleted",
            )
            .order_by(BusinessTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_completed_today(self, workspace_id: uuid.UUID) -> int:
        """Count tasks completed today (completed_at::date = today)."""
        ctx = get_tenant_context()
        today = date.today()
        result = await self._session.execute(
            select(func.count())
            .select_from(BusinessTask)
            .where(
                BusinessTask.workspace_id == workspace_id,
                BusinessTask.tenant_id == ctx.org_id,
                BusinessTask.status == "completed",
                func.date(BusinessTask.completed_at) == today,
            )
        )
        return result.scalar_one()

    async def update_fields(self, task_id: uuid.UUID, **values: Any) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(BusinessTask)
            .where(
                BusinessTask.id == task_id,
                BusinessTask.tenant_id == ctx.org_id,
            )
            .values(**values)
        )
