"""Reporting & Export Center repository — Sprint 56."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.reporting.models import ReportExport


class ReportingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Write ──────────────────────────────────────────────────────────────────

    async def create(self, record: ReportExport) -> ReportExport:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def update_fields(
        self, report_id: uuid.UUID, fields: dict
    ) -> ReportExport | None:
        ctx = get_tenant_context()
        stmt = select(ReportExport).where(
            ReportExport.id == report_id,
            ReportExport.tenant_id == ctx.org_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def delete(self, report_id: uuid.UUID) -> bool:
        ctx = get_tenant_context()
        stmt = select(ReportExport).where(
            ReportExport.id == report_id,
            ReportExport.tenant_id == ctx.org_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    # ── Read ───────────────────────────────────────────────────────────────────

    async def find_by_id(self, report_id: uuid.UUID) -> ReportExport | None:
        ctx = get_tenant_context()
        stmt = select(ReportExport).where(
            ReportExport.id == report_id,
            ReportExport.tenant_id == ctx.org_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        report_type: str | None = None,
        limit: int = 50,
    ) -> list[ReportExport]:
        ctx = get_tenant_context()
        stmt = (
            select(ReportExport)
            .where(
                ReportExport.tenant_id == ctx.org_id,
                ReportExport.workspace_id == workspace_id,
            )
            .order_by(ReportExport.created_at.desc())
            .limit(limit)
        )
        if report_type is not None:
            stmt = stmt.where(ReportExport.report_type == report_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
