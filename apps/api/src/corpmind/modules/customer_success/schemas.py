"""Customer Success Pydantic v2 schemas — Sprint 47."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator

VALID_HEALTH_STATUSES: set[str] = {"healthy", "watch", "at_risk"}
VALID_RISK_LEVELS: set[str] = {"low", "medium", "high"}


class CustomerSuccessOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    health_status: str
    health_score: Optional[int]
    risk_level: str
    owner_user_id: Optional[uuid.UUID]
    renewal_date: Optional[date]
    last_contact_date: Optional[date]
    next_followup_date: Optional[date]
    expansion_opportunity: bool
    renewal_probability: Optional[int]
    notes: Optional[str]
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CustomerSuccessCreate(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    health_status: str = "watch"
    health_score: Optional[int] = None
    risk_level: str = "medium"
    owner_user_id: Optional[uuid.UUID] = None
    renewal_date: Optional[date] = None
    last_contact_date: Optional[date] = None
    next_followup_date: Optional[date] = None
    expansion_opportunity: bool = False
    renewal_probability: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: str) -> str:
        if v not in VALID_HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {VALID_HEALTH_STATUSES}")
        return v

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        if v not in VALID_RISK_LEVELS:
            raise ValueError(f"risk_level must be one of {VALID_RISK_LEVELS}")
        return v

    @field_validator("health_score")
    @classmethod
    def validate_health_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("health_score must be 0-100")
        return v

    @field_validator("renewal_probability")
    @classmethod
    def validate_renewal_probability(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("renewal_probability must be 0-100")
        return v


class CustomerSuccessUpdate(BaseModel):
    health_status: Optional[str] = None
    health_score: Optional[int] = None
    risk_level: Optional[str] = None
    renewal_date: Optional[date] = None
    last_contact_date: Optional[date] = None
    next_followup_date: Optional[date] = None
    expansion_opportunity: Optional[bool] = None
    renewal_probability: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {VALID_HEALTH_STATUSES}")
        return v

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_RISK_LEVELS:
            raise ValueError(f"risk_level must be one of {VALID_RISK_LEVELS}")
        return v

    @field_validator("health_score")
    @classmethod
    def validate_health_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("health_score must be 0-100")
        return v

    @field_validator("renewal_probability")
    @classmethod
    def validate_renewal_probability(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("renewal_probability must be 0-100")
        return v


class AssignOwner(BaseModel):
    owner_user_id: uuid.UUID


class UpdateHealth(BaseModel):
    health_status: str
    health_score: Optional[int] = None

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: str) -> str:
        if v not in VALID_HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {VALID_HEALTH_STATUSES}")
        return v

    @field_validator("health_score")
    @classmethod
    def validate_health_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("health_score must be 0-100")
        return v


class ScheduleFollowup(BaseModel):
    next_followup_date: date


class CustomerSuccessFilters(BaseModel):
    workspace_id: uuid.UUID
    health_status: Optional[str] = None
    risk_level: Optional[str] = None
    owner_user_id: Optional[uuid.UUID] = None
    renewal_date_from: Optional[date] = None
    renewal_date_to: Optional[date] = None
    followup_due_by: Optional[date] = None
    expansion_opportunity: Optional[bool] = None
    search: Optional[str] = None
    include_archived: bool = False
    cursor: Optional[str] = None
    limit: int = 50


class CustomerSuccessListOut(BaseModel):
    items: list[CustomerSuccessOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int
