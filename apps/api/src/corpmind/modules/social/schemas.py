"""Social module schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SocialPostOut(BaseModel):
    id: uuid.UUID
    channel: str
    content: str
    status: str
    scheduled_at: datetime | None
    published_at: datetime | None
    model_config = {"from_attributes": True}


class SocialPostCreate(BaseModel):
    channel: str
    content: str
    hashtags: list[str] = []
    scheduled_at: datetime | None = None
