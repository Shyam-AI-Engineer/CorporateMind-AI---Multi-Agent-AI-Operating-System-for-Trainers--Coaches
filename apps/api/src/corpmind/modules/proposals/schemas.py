"""Proposals schemas (request / response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class GenerateProposalRequest(BaseModel):
    lead_id: uuid.UUID
    workspace_id: uuid.UUID


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
