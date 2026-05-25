"""Campaigns module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.campaigns.schemas import CampaignCreate, CampaignOut, CampaignStatusUpdate
from corpmind.modules.campaigns.service import CampaignService

router = APIRouter()


@router.post("/", response_model=CampaignOut, status_code=201)
async def create_campaign(
    req: CampaignCreate,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    return await CampaignService(session).create(req)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    return await CampaignService(session).get(campaign_id)


@router.patch("/{campaign_id}/status", status_code=204)
async def update_campaign_status(
    campaign_id: uuid.UUID,
    req: CampaignStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = CampaignService(session)
    if req.status == "paused":
        await svc.pause(campaign_id)
