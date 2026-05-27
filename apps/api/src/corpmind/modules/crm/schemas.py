"""CRM schemas (request / response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    contact_id: uuid.UUID
    workspace_id: uuid.UUID
    score: int = Field(default=0, ge=0, le=100)
    notes: str | None = None


class LeadOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: uuid.UUID
    stage: str
    score: int
    notes: str | None
    extra: dict[str, Any]
    meeting_scheduled_at: datetime | None
    booked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadListOut(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int


class LeadStageUpdate(BaseModel):
    """Body for /advance and /lost endpoints — carries optional notes."""
    notes: str | None = None


class LeadScoreUpdate(BaseModel):
    score: int = Field(ge=0, le=100)


class LeadNoteUpdate(BaseModel):
    notes: str = Field(min_length=1)


class MeetingScheduleRequest(BaseModel):
    meeting_at: datetime


# ── Stage advance response ─────────────────────────────────────────────────────

class StageAdvanceResponse(BaseModel):
    lead_id: uuid.UUID
    from_stage: str
    to_stage: str


# ── Pipeline stats (funnel view) ───────────────────────────────────────────────

class PipelineStageCount(BaseModel):
    stage: str
    count: int


class PipelineStats(BaseModel):
    workspace_id: uuid.UUID
    stages: list[PipelineStageCount]
    total: int
