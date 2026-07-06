"""Customer Renewal Pydantic v2 schemas — Sprint 48."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

VALID_RENEWAL_TYPES: set[str] = {"annual", "quarterly", "monthly", "custom"}
VALID_RENEWAL_STATUSES: set[str] = {
    "planned",
    "in_progress",
    "negotiation",
    "won",
    "lost",
    "cancelled",
}


class CustomerRenewalOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    contract_name: Optional[str]
    contract_value: Optional[Decimal]
    renewal_type: str
    renewal_status: str
    renewal_date: Optional[date]
    owner_user_id: Optional[uuid.UUID]
    probability: Optional[int]
    expected_value: Optional[Decimal]
    proposal_id: Optional[uuid.UUID]
    notes: Optional[str]
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CustomerRenewalCreate(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    contract_name: Optional[str] = None
    contract_value: Optional[Decimal] = None
    renewal_type: str = "annual"
    renewal_status: str = "planned"
    renewal_date: Optional[date] = None
    owner_user_id: Optional[uuid.UUID] = None
    probability: Optional[int] = None
    expected_value: Optional[Decimal] = None
    proposal_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None

    @field_validator("renewal_type")
    @classmethod
    def validate_renewal_type(cls, v: str) -> str:
        if v not in VALID_RENEWAL_TYPES:
            raise ValueError(f"renewal_type must be one of {VALID_RENEWAL_TYPES}")
        return v

    @field_validator("renewal_status")
    @classmethod
    def validate_renewal_status(cls, v: str) -> str:
        if v not in VALID_RENEWAL_STATUSES:
            raise ValueError(f"renewal_status must be one of {VALID_RENEWAL_STATUSES}")
        return v

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("probability must be 0-100")
        return v


class CustomerRenewalUpdate(BaseModel):
    contract_name: Optional[str] = None
    contract_value: Optional[Decimal] = None
    renewal_type: Optional[str] = None
    renewal_date: Optional[date] = None
    owner_user_id: Optional[uuid.UUID] = None
    probability: Optional[int] = None
    expected_value: Optional[Decimal] = None
    notes: Optional[str] = None

    @field_validator("renewal_type")
    @classmethod
    def validate_renewal_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_RENEWAL_TYPES:
            raise ValueError(f"renewal_type must be one of {VALID_RENEWAL_TYPES}")
        return v

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("probability must be 0-100")
        return v


class AssignRenewalOwner(BaseModel):
    owner_user_id: uuid.UUID


class UpdateRenewalStatus(BaseModel):
    renewal_status: str

    @field_validator("renewal_status")
    @classmethod
    def validate_renewal_status(cls, v: str) -> str:
        if v not in VALID_RENEWAL_STATUSES:
            raise ValueError(f"renewal_status must be one of {VALID_RENEWAL_STATUSES}")
        return v


class AttachProposal(BaseModel):
    proposal_id: uuid.UUID


class CustomerRenewalFilters(BaseModel):
    workspace_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    renewal_type: Optional[str] = None
    renewal_status: Optional[str] = None
    owner_user_id: Optional[uuid.UUID] = None
    renewal_date_from: Optional[date] = None
    renewal_date_to: Optional[date] = None
    search: Optional[str] = None
    include_archived: bool = False
    cursor: Optional[str] = None
    limit: int = 50


class CustomerRenewalListOut(BaseModel):
    items: list[CustomerRenewalOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int
