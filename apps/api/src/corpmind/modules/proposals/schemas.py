"""Proposals schemas (request / response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class ProposalListOut(BaseModel):
    items: list[ProposalOut]
    total: int
    limit: int
    offset: int


class ProposalSendRequest(BaseModel):
    notes: str | None = None
