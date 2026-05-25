"""Proposals schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ProposalOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    title: str
    status: str
    cloudinary_url: str | None
    sent_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class GenerateProposalRequest(BaseModel):
    contact_id: uuid.UUID
    crm_context: dict = {}
