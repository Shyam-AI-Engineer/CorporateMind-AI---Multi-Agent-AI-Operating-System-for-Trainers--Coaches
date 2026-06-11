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


# ── Read-only activity + follow-up DTOs (Sprint 5 prerequisite layer) ─────────

class ActivityOut(BaseModel):
    """A single CRM activity row (Activity timeline view)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    lead_id: uuid.UUID | None
    contact_id: uuid.UUID
    type: str
    summary: str
    source_inbox_message_id: uuid.UUID | None
    source_outbound_message_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int


class FollowUpTaskOut(BaseModel):
    """A single follow-up task row (Follow-Up Queue view)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    lead_id: uuid.UUID | None
    contact_id: uuid.UUID
    type: str
    status: str
    scheduled_for: datetime | None
    source_inbox_message_id: uuid.UUID
    source_outbound_message_id: uuid.UUID | None
    # Sprint 8B/8C: the draft this follow-up produced (set when parked/sent).
    # Surfaced so the approval UI can locate the draft to review.
    result_outbound_message_id: uuid.UUID | None = None
    attempts: int = 0
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FollowUpTaskListOut(BaseModel):
    items: list[FollowUpTaskOut]
    total: int
    limit: int
    offset: int


# ── Sprint 8C: HITL approval surface for awaiting_approval follow-ups ──────────

class FollowupDraftView(BaseModel):
    """The draft outbound message a follow-up produced, for human review."""

    id: uuid.UUID
    subject: str | None
    body: str
    status: str


class FollowupReplyView(BaseModel):
    """The inbound reply that triggered the follow-up (decrypted snippet).

    Counterparty content within the tenant boundary — returned only in an
    authenticated, tenant-scoped response and never written to logs.
    """

    from_address: str | None
    subject: str | None
    snippet: str | None
    received_at: datetime | None


class FollowupReviewOut(BaseModel):
    """Consolidated review payload: reply ↔ draft + context, one round trip."""

    task: FollowUpTaskOut
    draft: FollowupDraftView | None
    reply: FollowupReplyView | None
    original_subject: str | None
    lead_stage: str | None


class FollowupEditRequest(BaseModel):
    """Edit the draft body/subject before approval (only while awaiting_approval)."""

    subject: str | None = None
    body: str = Field(min_length=1)


class FollowupRejectRequest(BaseModel):
    reason: str | None = None


class FollowupApproveResponse(BaseModel):
    task_id: uuid.UUID
    status: str  # done | blocked
    compliance_reason: str | None = None
