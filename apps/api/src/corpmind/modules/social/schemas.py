"""Social module schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SocialPostOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    channel: str
    content: str
    hashtags: list[str]
    status: str  # draft | scheduled | published | failed
    scheduled_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class SocialPostCreate(BaseModel):
    workspace_id: uuid.UUID
    channel: str
    content: str
    hashtags: list[str] = []
    scheduled_at: datetime | None = None


class SocialPostListOut(BaseModel):
    items: list[SocialPostOut]
    total: int
    limit: int
    offset: int
