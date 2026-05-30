"""Trainer intelligence schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TrainerProfileOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    niche: str | None
    topics: list[str]
    tone: str | None
    pricing_min_inr: int | None
    pricing_max_inr: int | None
    bio: str | None
    usp: str | None
    target_industries: list[str]
    languages: list[str]
    is_locked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractFromTextRequest(BaseModel):
    """Phase 1: extract profile from raw pasted text (bio, LinkedIn About, brochure body).

    File-upload + OCR/transcription paths arrive in Phase 2 via the ingestion module.
    """
    content: str = Field(min_length=20, max_length=20_000)


class TrainerProfileExtraction(BaseModel):
    """The structured contract we require the LLM to honor.

    Used to validate the model's JSON output before persistence. Fields use
    explicit defaults so a model that omits a key still validates.
    """
    niche: str | None = None
    topics: list[str] = Field(default_factory=list)
    tone: str | None = None
    pricing_min_inr: int | None = None
    pricing_max_inr: int | None = None
    bio: str | None = None
    usp: str | None = None
    target_industries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class TrainerProfileUpdate(BaseModel):
    niche: str | None = None
    bio: str | None = None
    topics: list[str] | None = None
    tone: str | None = None
    usp: str | None = None
    target_industries: list[str] | None = None
    languages: list[str] | None = None
    pricing_min_inr: int | None = None
    pricing_max_inr: int | None = None


class UploadRequest(BaseModel):
    """Enqueue an uploaded file for async extraction."""
    cloudinary_url: str = Field(
        description="Signed Cloudinary URL — must be hosted on res.cloudinary.com."
    )
    file_type: str = Field(
        description="One of: pdf | image | video",
        pattern="^(pdf|image|video)$",
    )


class UploadEnqueuedResponse(BaseModel):
    task_id: str
    status: str = "queued"


class UploadStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
