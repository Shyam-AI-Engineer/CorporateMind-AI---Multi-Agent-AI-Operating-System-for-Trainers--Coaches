"""Outreach schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GenerateOutreachRequest(BaseModel):
    contact_id: uuid.UUID
    channel: str
    campaign_id: uuid.UUID | None = None
    ab_variant: str | None = None


class OutboundMessageOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    channel: str
    subject: str | None
    body: str
    status: str
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
