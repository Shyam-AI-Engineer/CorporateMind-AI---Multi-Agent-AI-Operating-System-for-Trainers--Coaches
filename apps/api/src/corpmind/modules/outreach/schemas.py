"""Outreach schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateOutreachRequest(BaseModel):
    contact_id: uuid.UUID
    channel: str = Field(default="email", pattern=r"^(email|whatsapp|telegram)$")
    campaign_id: uuid.UUID | None = None
    ab_variant: str | None = None


class OutboundMessageOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    campaign_id: uuid.UUID | None
    channel: str
    subject: str | None
    body: str
    prompt_version: str | None
    ab_variant: str | None
    status: str
    smtp_message_id: str | None
    provider_message_id: str | None
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OutboundMessageListOut(BaseModel):
    items: list[OutboundMessageOut]
    total: int
    limit: int
    offset: int


class SendMessageResponse(BaseModel):
    message_id: uuid.UUID
    status: str  # queued | blocked
    compliance_reason: str | None = None
