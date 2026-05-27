"""CRM repository."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.models import Lead

log = structlog.get_logger(__name__)


class LeadRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, lead: Lead) -> Lead:
        self._session.add(lead)
        await self._session.flush()
        log.info("crm.lead_row_created", lead_id=str(lead.id))
        return lead

    async def find_by_id(self, lead_id: uuid.UUID) -> Lead | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead).where(
                Lead.id == lead_id,
                Lead.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_contact(
        self, contact_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Lead | None:
        """Return the most recent non-terminal lead for this contact in this workspace."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.workspace_id == workspace_id,
                Lead.tenant_id == ctx.org_id,
                Lead.stage.not_in(("booked", "lost")),
            )
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_pipeline(
        self,
        workspace_id: uuid.UUID,
        *,
        stage: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        ctx = get_tenant_context()
        stmt = select(Lead).where(
            Lead.workspace_id == workspace_id,
            Lead.tenant_id == ctx.org_id,
        )
        if stage:
            stmt = stmt.where(Lead.stage == stage)
        stmt = stmt.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_stage(self, workspace_id: uuid.UUID) -> dict[str, int]:
        """Return a mapping of stage → count for all leads in a workspace."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead.stage, func.count().label("cnt"))
            .where(Lead.workspace_id == workspace_id, Lead.tenant_id == ctx.org_id)
            .group_by(Lead.stage)
        )
        return {row[0]: row[1] for row in result}

    async def update_fields(self, lead_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == ctx.org_id)
            .values(**values)
        )
