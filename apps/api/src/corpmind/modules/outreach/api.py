"""Outreach module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.outreach.schemas import (
    GenerateOutreachRequest,
    OutboundMessageOut,
    SendMessageResponse,
)
from corpmind.modules.outreach.service import OutreachService

router = APIRouter()


@router.post(
    "/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=OutboundMessageOut,
    summary="Generate personalized outreach copy",
)
async def generate_message(
    req: GenerateOutreachRequest,
    session: AsyncSession = Depends(get_session),
) -> OutboundMessageOut:
    """Personalize outreach copy for a single contact and save it as a draft.

    Runs opt-in compliance check before the LLM call.
    Returns 422 if the contact is not contactable.
    """
    svc = OutreachService(session)
    return await svc.generate_message(req)


@router.post(
    "/{message_id}/send",
    response_model=SendMessageResponse,
    summary="Send a draft message",
)
async def send_message(
    message_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SendMessageResponse:
    """Run full compliance checks and enqueue the message for delivery.

    Returns status='queued' on success, or status='blocked' with compliance_reason
    if a compliance check fails.  The message status is persisted either way.
    """
    svc = OutreachService(session)
    return await svc.send_message(message_id)


@router.get(
    "/{message_id}",
    response_model=OutboundMessageOut,
    summary="Get a single outbound message",
)
async def get_message(
    message_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> OutboundMessageOut:
    svc = OutreachService(session)
    return await svc.get_message(message_id)
