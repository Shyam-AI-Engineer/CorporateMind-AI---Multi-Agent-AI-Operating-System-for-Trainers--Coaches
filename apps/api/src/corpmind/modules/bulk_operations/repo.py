"""Bulk Operations repository — Sprint 59."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.bulk_operations.models import BulkOperation


class BulkOperationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Write ──────────────────────────────────────────────────────────────────

    async def create(self, record: BulkOperation) -> BulkOperation:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def update_fields(
        self, op_id: uuid.UUID, fields: dict
    ) -> BulkOperation | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(BulkOperation).where(
                BulkOperation.id == op_id,
                BulkOperation.tenant_id == ctx.org_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    # ── Read ───────────────────────────────────────────────────────────────────

    async def find_by_id(self, op_id: uuid.UUID) -> BulkOperation | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(BulkOperation).where(
                BulkOperation.id == op_id,
                BulkOperation.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[BulkOperation]:
        ctx = get_tenant_context()
        stmt = (
            select(BulkOperation)
            .where(
                BulkOperation.tenant_id == ctx.org_id,
                BulkOperation.workspace_id == workspace_id,
            )
            .order_by(BulkOperation.created_at.desc())
            .limit(limit)
        )
        if entity_type is not None:
            stmt = stmt.where(BulkOperation.entity_type == entity_type)
        if status is not None:
            stmt = stmt.where(BulkOperation.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
