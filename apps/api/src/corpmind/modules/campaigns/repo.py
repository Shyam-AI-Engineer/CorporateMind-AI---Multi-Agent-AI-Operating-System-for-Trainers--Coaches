"""Campaign repository."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.campaigns.models import Campaign, CampaignRecipient

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
        await self._session.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id, Campaign.tenant_id == ctx.org_id)
            .values(status=status)
        )

    async def update_fields(self, campaign_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id, Campaign.tenant_id == ctx.org_id)
            .values(**values)
        )


class CampaignRecipientRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_bulk(
        self, campaign_id: uuid.UUID, contact_ids: list[uuid.UUID]
    ) -> int:
        """Add contacts as recipients; skip any already present. Returns count added."""
        ctx = get_tenant_context()
        existing_result = await self._session.execute(
            select(CampaignRecipient.contact_id).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.tenant_id == ctx.org_id,
            )
        )
        existing_ids = {row[0] for row in existing_result}
        new_ids = [cid for cid in contact_ids if cid not in existing_ids]
        for contact_id in new_ids:
            self._session.add(
                CampaignRecipient(
                    tenant_id=ctx.org_id,
                    campaign_id=campaign_id,
                    contact_id=contact_id,
                )
            )
        if new_ids:
            await self._session.flush()
        return len(new_ids)

    async def delete_recipient(
        self, campaign_id: uuid.UUID, contact_id: uuid.UUID
    ) -> bool:
        """Remove a recipient. Returns True if a row was deleted."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.contact_id == contact_id,
                CampaignRecipient.tenant_id == ctx.org_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_by_campaign(
        self,
        campaign_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CampaignRecipient]:
        ctx = get_tenant_context()
        stmt = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.tenant_id == ctx.org_id,
        )
        if status:
            stmt = stmt.where(CampaignRecipient.status == status)
        stmt = stmt.order_by(CampaignRecipient.id).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_recipients(
        self, campaign_id: uuid.UUID, *, status: str | None = None
    ) -> int:
        ctx = get_tenant_context()
        stmt = select(func.count()).select_from(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.tenant_id == ctx.org_id,
        )
        if status:
            stmt = stmt.where(CampaignRecipient.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update_recipient(
        self,
        recipient_id: uuid.UUID,
        *,
        status: str | None = None,
        message_id: str | None = None,
    ) -> None:
        ctx = get_tenant_context()
        values: dict[str, object] = {}
        if status is not None:
            values["status"] = status
        if message_id is not None:
            values["message_id"] = message_id
        if not values:
            return
        await self._session.execute(
            update(CampaignRecipient)
            .where(
                CampaignRecipient.id == recipient_id,
                CampaignRecipient.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def find_by_campaign_and_contact(
        self, campaign_id: uuid.UUID, contact_id: uuid.UUID
    ) -> CampaignRecipient | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.contact_id == contact_id,
                CampaignRecipient.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()
