"""Campaigns module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.campaigns.schemas import (
    AddRecipientsRequest,
    AddRecipientsResponse,
    CampaignCreate,
    CampaignLaunchResponse,
    CampaignListOut,
    CampaignOut,
    CampaignRecipientOut,
    CampaignStatusUpdate,
)
from corpmind.modules.campaigns.service import CampaignService

router = APIRouter()


@router.post(
    "/",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign draft",
)
async def create_campaign(
    req: CampaignCreate,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    return await CampaignService(session).create(req)


@router.get(
    "/",
    response_model=CampaignListOut,
    summary="List campaigns for a workspace",
)
async def list_campaigns(
    workspace_id: uuid.UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> CampaignListOut:
    return await CampaignService(session).list_for_workspace(
        workspace_id, limit=limit, offset=offset
    )


@router.get(
    "/{campaign_id}",
    response_model=CampaignOut,
    summary="Get a campaign",
)
async def get_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    return await CampaignService(session).get(campaign_id)


@router.patch(
    "/{campaign_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Pause, resume, or cancel a campaign",
)
async def update_campaign_status(
    campaign_id: uuid.UUID,
    req: CampaignStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = CampaignService(session)
    if req.status == "paused":
        await svc.pause(campaign_id)
    elif req.status == "resumed":
        await svc.resume(campaign_id)
    elif req.status == "cancelled":
        await svc.cancel(campaign_id)


# ── Recipient management ──────────────────────────────────────────────────────

@router.post(
    "/{campaign_id}/recipients",
    response_model=AddRecipientsResponse,
    status_code=status.HTTP_200_OK,
    summary="Add contacts as campaign recipients",
)
async def add_recipients(
    campaign_id: uuid.UUID,
    req: AddRecipientsRequest,
    session: AsyncSession = Depends(get_session),
) -> AddRecipientsResponse:
    return await CampaignService(session).add_recipients(campaign_id, req)


@router.delete(
    "/{campaign_id}/recipients/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a contact from a draft campaign",
)
async def remove_recipient(
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await CampaignService(session).remove_recipient(campaign_id, contact_id)


@router.get(
    "/{campaign_id}/recipients",
    response_model=list[CampaignRecipientOut],
    summary="List campaign recipients",
)
async def list_recipients(
    campaign_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[CampaignRecipientOut]:
    return await CampaignService(session).get_recipients(
        campaign_id, status=status_filter, limit=limit, offset=offset
    )


# ── State transitions ─────────────────────────────────────────────────────────

@router.post(
    "/{campaign_id}/lock",
    response_model=CampaignOut,
    summary="Lock a campaign — freezes the recipient list",
)
async def lock_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    return await CampaignService(session).lock(campaign_id)


@router.post(
    "/{campaign_id}/launch",
    response_model=CampaignLaunchResponse,
    summary="Launch a locked campaign",
)
async def launch_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CampaignLaunchResponse:
    """Enqueue the send pipeline for all recipients.

    Returns status='running' if launched immediately, or status='pending_hitl'
    if the recipient count exceeds the HITL threshold and manual approval is
    required before messages are sent.
    """
    return await CampaignService(session).launch(campaign_id)


@router.post(
    "/{campaign_id}/approve",
    response_model=CampaignLaunchResponse,
    summary="Approve a HITL-gated campaign",
)
async def approve_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CampaignLaunchResponse:
    """Approve and immediately launch a campaign that is pending HITL review.

    Transitions pending_hitl → approved → running and enqueues the send
    pipeline.  Returns the same shape as /launch.
    """
    return await CampaignService(session).approve(campaign_id)
