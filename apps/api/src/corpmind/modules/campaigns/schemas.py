"""Campaign schemas (request / response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel: str = Field(pattern="^(email|whatsapp|telegram|instagram|facebook|linkedin)$")
    settings: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None


class CampaignOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: str
    channel: str
    recipient_count: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignListOut(BaseModel):
    items: list[CampaignOut]
    total: int
    limit: int
    offset: int


class CampaignStatusUpdate(BaseModel):
    status: str = Field(pattern="^(paused|resumed|cancelled)$")


# ── Recipient management ──────────────────────────────────────────────────────

class AddRecipientsRequest(BaseModel):
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class AddRecipientsResponse(BaseModel):
    added_count: int
    total_recipients: int


class CampaignRecipientOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    status: str
    message_id: str | None
    sent_at: datetime | None
    error_code: str | None

    model_config = {"from_attributes": True}


# ── Launch ────────────────────────────────────────────────────────────────────

class CampaignLaunchResponse(BaseModel):
    campaign_id: uuid.UUID
    status: str          # running | pending_hitl
    recipient_count: int
    hitl_required: bool
