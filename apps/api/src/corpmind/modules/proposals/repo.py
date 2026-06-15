"""Proposals repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.proposals.models import Proposal


class ProposalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, proposal: Proposal) -> Proposal:
        self._session.add(proposal)
        await self._session.flush()
        return proposal

    async def find_by_id(self, proposal_id: uuid.UUID) -> Proposal | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Proposal).where(
                Proposal.id == proposal_id,
                Proposal.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_id_for_update(self, proposal_id: uuid.UUID) -> Proposal | None:
        """SELECT … FOR UPDATE — acquires a row-level lock for atomic state transitions."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Proposal)
            .where(
                Proposal.id == proposal_id,
                Proposal.tenant_id == ctx.org_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        approval_status: str | None = None,
    ) -> list[Proposal]:
        ctx = get_tenant_context()
        stmt = (
            select(Proposal)
            .where(
                Proposal.workspace_id == workspace_id,
                Proposal.tenant_id == ctx.org_id,
            )
            .order_by(Proposal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if approval_status is not None:
            stmt = stmt.where(Proposal.approval_status == approval_status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        approval_status: str | None = None,
    ) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(Proposal)
            .where(
                Proposal.workspace_id == workspace_id,
                Proposal.tenant_id == ctx.org_id,
            )
        )
        if approval_status is not None:
            stmt = stmt.where(Proposal.approval_status == approval_status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update_fields(self, proposal_id: uuid.UUID, **values: Any) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Proposal)
            .where(
                Proposal.id == proposal_id,
                Proposal.tenant_id == ctx.org_id,
            )
            .values(**values)
        )
