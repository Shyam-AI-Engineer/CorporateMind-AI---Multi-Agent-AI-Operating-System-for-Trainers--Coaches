"""Campaign service — create, launch, pause campaigns."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, PermissionDeniedError
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.campaigns.models import Campaign
from corpmind.modules.campaigns.repo import CampaignRepo
from corpmind.modules.campaigns.schemas import CampaignCreate, CampaignOut

log = structlog.get_logger(__name__)


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CampaignRepo(session)

    async def create(self, req: CampaignCreate) -> CampaignOut:
        ctx = get_tenant_context()
        campaign = Campaign(
            tenant_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            name=req.name,
            channel=req.channel,
            settings=req.settings,
            scheduled_at=req.scheduled_at,
            created_by=ctx.user_id,
        )
        await self._repo.create(campaign)
        log.info("campaign.draft_created", campaign_id=str(campaign.id))
        return CampaignOut.model_validate(campaign)

    async def get(self, campaign_id: uuid.UUID) -> CampaignOut:
        campaign = await self._repo.find_by_id(campaign_id)
        if not campaign:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        return CampaignOut.model_validate(campaign)

    async def pause(self, campaign_id: uuid.UUID) -> None:
        campaign = await self._repo.find_by_id(campaign_id)
        if not campaign:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        if campaign.status not in ("running", "approved"):
            raise PermissionDeniedError(f"Cannot pause a campaign in status '{campaign.status}'")
        await self._repo.update_status(campaign_id, "paused")
        log.info("campaign.paused", campaign_id=str(campaign_id))
