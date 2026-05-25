"""HR discovery schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


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


class DiscoveryRequest(BaseModel):
    """Trigger HR discovery for matching companies."""
    industries: list[str]
    employee_count_ranges: list[str] = ["50-500", "500-5000"]
    cities: list[str] = []
    max_contacts: int = 100
