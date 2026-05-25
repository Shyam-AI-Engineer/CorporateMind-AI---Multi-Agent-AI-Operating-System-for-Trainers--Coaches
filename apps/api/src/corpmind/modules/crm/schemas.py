"""CRM schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class LeadOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    stage: str
    score: int
    meeting_scheduled_at: datetime | None
    booked_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class LeadStageUpdate(BaseModel):
    stage: str
    notes: str | None = None
