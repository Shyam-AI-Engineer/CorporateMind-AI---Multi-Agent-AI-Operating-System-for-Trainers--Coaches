"""Trainer intelligence schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TrainerProfileOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    niche: str | None
    topics: list[str]
    tone: str | None
    pricing_min_inr: int | None
    pricing_max_inr: int | None
    usp: str | None
    target_industries: list[str]
    languages: list[str]
    is_locked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadContentRequest(BaseModel):
    """Request to extract trainer intelligence from an uploaded file."""
    cloudinary_url: str
    file_type: str  # pdf | video | image


class TrainerProfileUpdate(BaseModel):
    niche: str | None = None
    tone: str | None = None
    usp: str | None = None
    pricing_min_inr: int | None = None
    pricing_max_inr: int | None = None
