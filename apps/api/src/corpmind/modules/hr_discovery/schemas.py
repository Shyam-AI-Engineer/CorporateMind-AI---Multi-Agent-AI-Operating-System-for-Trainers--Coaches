"""HR discovery schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class HRContactOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    full_name: str
    title: str | None
    email: str | None
    email_deliverable: bool
    preferred_language: str | None
    source_type: str
    is_contactable: bool
    opted_in_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    employee_count_range: str | None
    city: str | None
    country: str | None

    model_config = {"from_attributes": True}


# ── Import / enrichment ───────────────────────────────────────────────────────

class ContactImportItem(BaseModel):
    """One contact to import.

    Contacts with opted_in_at + opt_in_evidence set are marked is_contactable=True
    and can receive outreach. Contacts missing either field are persisted as
    is_contactable=False and excluded from all send segments.
    """
    raw_data: str = Field(
        min_length=10,
        max_length=5_000,
        description="Raw text about the contact (scraped bio, vCard, CSV row, etc.)",
    )
    source: str = Field(description="URL or system that produced this contact.")
    source_type: str = Field(
        pattern="^(webinar_registration|company_website|public_directory|referral|event_badge)$",
        description="One of the allowed opt-in source types.",
    )
    opted_in_at: datetime | None = Field(default=None, description="When the contact gave consent. Omit to import as non-contactable.")
    opt_in_evidence: str | None = Field(default=None, min_length=5, description="URL, screenshot ref, or consent record ID. Omit to import as non-contactable.")
    company_name: str = Field(min_length=1, max_length=500)
    company_industry: str | None = None
    company_city: str | None = None
    company_country: str | None = None


class ContactBatchImportRequest(BaseModel):
    contacts: list[ContactImportItem] = Field(min_length=1, max_length=200)


class HRContactEnrichment(BaseModel):
    """Structured extraction the LLM must return for a single contact."""
    full_name: str | None = None
    title: str | None = None
    title_normalized: str | None = None
    seniority: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    company_name: str | None = None
    preferred_language: str | None = None


class ContactBatchImportResponse(BaseModel):
    imported: int
    non_contactable: int
    failed: int
    contact_ids: list[uuid.UUID]


# ── List / detail ─────────────────────────────────────────────────────────────

class ContactListResponse(BaseModel):
    items: list[HRContactOut]
    total: int
    limit: int
    offset: int


# ── Ranking ───────────────────────────────────────────────────────────────────

class RankContactsRequest(BaseModel):
    """Caller supplies both the contact IDs and the trainer profile snapshot.

    Profile fields come from GET /trainer/profile — passing them here avoids
    a cross-module repo dependency (CLAUDE.md inter-module rule).
    """
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    trainer_niche: str
    trainer_topics: list[str]
    trainer_target_industries: list[str]


class RankedContactOut(BaseModel):
    contact_id: uuid.UUID
    score: int = Field(ge=1, le=10)
    reason: str
    contact: HRContactOut


class RankContactsResponse(BaseModel):
    rankings: list[RankedContactOut]
