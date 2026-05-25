"""Campaign repository."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.campaigns.models import Campaign

log = structlog.get_logger(__name__)


class CampaignRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, campaign_id: uuid.UUID) -> Campaign | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self, workspace_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Campaign]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Campaign)
            .where(
                Campaign.tenant_id == ctx.org_id,
                Campaign.workspace_id == workspace_id,
            )
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, campaign: Campaign) -> Campaign:
        self._session.add(campaign)
        await self._session.flush()
        log.info("campaign.created", campaign_id=str(campaign.id), channel=campaign.channel)
        return campaign

    async def update_status(self, campaign_id: uuid.UUID, status: str) -> None:
        ctx = get_tenant_context()
        from sqlalchemy import update
        await self._session.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id, Campaign.tenant_id == ctx.org_id)
            .values(status=status)
        )
