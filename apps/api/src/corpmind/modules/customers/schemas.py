"""Customer Pydantic v2 schemas — Sprint 41."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

# ── Enum literals ─────────────────────────────────────────────────────────────

CustomerStatus = Literal["active", "inactive", "prospect", "former"]
CustomerHealthStatus = Literal["healthy", "attention", "at_risk", "inactive"]

VALID_STATUSES: set[str] = {"active", "inactive", "prospect", "former"}
VALID_HEALTH_STATUSES: set[str] = {"healthy", "attention", "at_risk", "inactive"}

# ── Core DTO ──────────────────────────────────────────────────────────────────


class CustomerOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    company_name: str
    display_name: str
    industry: str | None
    website: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    postal_code: str | None
    company_size: str | None
    annual_revenue_inr: Decimal | None
    status: str
    health_status: str
    relationship_owner_id: uuid.UUID | None
    primary_contact_name: str | None
    primary_contact_email: str | None
    primary_contact_phone: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Write DTOs ────────────────────────────────────────────────────────────────


class CustomerCreate(BaseModel):
    workspace_id: uuid.UUID
    company_name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=128)
    website: str | None = Field(default=None, max_length=512)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = None
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue_inr: Decimal | None = Field(default=None, ge=0)
    status: str = Field(default="active")
    health_status: str = Field(default="healthy")
    relationship_owner_id: uuid.UUID | None = None
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: str | None = Field(default=None, max_length=255)
    primary_contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: str) -> str:
        if v not in VALID_HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {sorted(VALID_HEALTH_STATUSES)}")
        return v


class CustomerUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=128)
    website: str | None = Field(default=None, max_length=512)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = None
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue_inr: Decimal | None = Field(default=None, ge=0)
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: str | None = Field(default=None, max_length=255)
    primary_contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class CustomerHealthUpdate(BaseModel):
    health_status: str

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: str) -> str:
        if v not in VALID_HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {sorted(VALID_HEALTH_STATUSES)}")
        return v


class CustomerOwnerAssign(BaseModel):
    relationship_owner_id: uuid.UUID


# ── List / pagination DTOs ────────────────────────────────────────────────────


class CustomerListOut(BaseModel):
    items: list[CustomerOut]
    next_cursor: str | None
    has_more: bool
    total: int


# ── Filter / search ───────────────────────────────────────────────────────────


class CustomerFilters(BaseModel):
    workspace_id: uuid.UUID
    status: str | None = None
    industry: str | None = None
    health_status: str | None = None
    owner_id: uuid.UUID | None = None
    search: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
