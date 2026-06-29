"""Proposals schemas (request / response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, field_validator


class GenerateProposalRequest(BaseModel):
    lead_id: uuid.UUID
    workspace_id: uuid.UUID
    # Sprint 18A: optional pipeline value hint set at generation time
    expected_value_inr: Decimal | None = None


class ProposalOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: uuid.UUID
    title: str
    status: str
    content: dict[str, Any]
    cloudinary_url: str | None
    sent_at: datetime | None
    created_at: datetime
    # Sprint 12A approval fields
    approval_status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    rejected_reason: str | None
    # Sprint 12B delivery fields
    # outbound_message_id: set when deliver() is called; None until then.
    # delivery_status: derived from OutboundMessage.status; None until delivery initiated.
    outbound_message_id: uuid.UUID | None = None
    delivery_status: str | None = None
    # Sprint 18A revenue attribution fields (None for proposals created before Sprint 18A)
    lead_id: uuid.UUID | None = None
    expected_value_inr: Decimal | None = None
    actual_value_inr: Decimal | None = None
    client_status: str | None = None
    client_accepted_at: datetime | None = None
    client_declined_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProposalListOut(BaseModel):
    items: list[ProposalOut]
    total: int
    limit: int
    offset: int


class ProposalSendRequest(BaseModel):
    notes: str | None = None


class ProposalRejectRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v


# Sprint 18A — client-response request schemas

class AcceptProposalRequest(BaseModel):
    """Record client acceptance and the confirmed deal value."""
    actual_value_inr: Decimal
    expected_value_inr: Decimal | None = None

    @field_validator("actual_value_inr")
    @classmethod
    def value_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("actual_value_inr must be positive")
        return v


class DeclineProposalRequest(BaseModel):
    reason: str | None = None
