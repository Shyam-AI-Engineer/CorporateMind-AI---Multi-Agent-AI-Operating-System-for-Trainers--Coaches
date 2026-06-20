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
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
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


class GenerateFollowupRequest(BaseModel):
    """Input for OutreachService.generate_followup (ADR-0008, Sprint 8A).

    The caller (Sprint 8B cadence worker) hydrates reply/original-email context
    and passes it here.  reply_text is the decrypted inbox snippet (≤ ~500 chars);
    original_subject/body come from the outbound being replied to; lead_stage and
    days_since condition tone.  All context fields are optional — the prompt
    inputs fall back to safe placeholders when a field is missing.
    """

    contact_id: uuid.UUID
    task_type: str = Field(pattern=r"^(question_followup|out_of_office_followup)$")
    reply_text: str | None = None
    original_subject: str | None = None
    original_body: str | None = None
    lead_stage: str | None = None
    days_since: int | None = None
    campaign_id: uuid.UUID | None = None


class FollowupDraftOut(BaseModel):
    """Result of generate_followup.

    Wraps the persisted draft OutboundMessage and surfaces the HITL signal.
    `needs_human_review` is intentionally NOT a column on OutboundMessage — it
    rides on this return DTO so Sprint 8A needs no migration.  The 8B cadence
    reads it to decide auto-send vs. park-for-approval.  For question
    follow-ups it fails safe to True when the model could not answer.
    `answered` is None for nudge drafts (there is no question to answer).
    """

    message: OutboundMessageOut
    task_type: str
    needs_human_review: bool
    answered: bool | None = None
