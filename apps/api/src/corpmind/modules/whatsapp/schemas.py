"""WhatsApp module schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class WhatsAppTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    category: str
    approval_status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class WhatsAppSessionOut(BaseModel):
    contact_id: uuid.UUID
    window_expires_at: datetime
    is_active: bool
    model_config = {"from_attributes": True}
