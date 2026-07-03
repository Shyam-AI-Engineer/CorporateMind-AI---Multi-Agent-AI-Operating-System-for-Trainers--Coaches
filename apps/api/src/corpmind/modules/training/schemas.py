"""Training Engagement Pydantic v2 schemas — Sprint 42."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator

VALID_STATUSES: set[str] = {"planned", "scheduled", "in_progress", "completed", "cancelled"}
VALID_DELIVERY_MODES: set[str] = {"onsite", "online", "hybrid"}
VALID_PRIORITIES: set[str] = {"low", "medium", "high", "urgent"}


class TrainingEngagementOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    description: Optional[str]
    training_type: str
    delivery_mode: str
    status: str
    priority: str
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    estimated_participants: Optional[int]
    actual_participants: Optional[int]
    assigned_trainer_id: Optional[uuid.UUID]
    coordinator_id: Optional[uuid.UUID]
    location: Optional[str]
    meeting_link: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class TrainingEngagementCreate(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    description: Optional[str] = None
    training_type: str
    delivery_mode: str
    status: str = "planned"
    priority: str = "medium"
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    estimated_participants: Optional[int] = None
    assigned_trainer_id: Optional[uuid.UUID] = None
    coordinator_id: Optional[uuid.UUID] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("program_name")
    @classmethod
    def program_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("program_name must not be empty")
        return v

    @field_validator("delivery_mode")
    @classmethod
    def delivery_mode_valid(cls, v: str) -> str:
        if v not in VALID_DELIVERY_MODES:
            raise ValueError(f"delivery_mode must be one of {VALID_DELIVERY_MODES}")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v

    @field_validator("estimated_participants")
    @classmethod
    def participants_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("estimated_participants must be non-negative")
        return v


class TrainingEngagementUpdate(BaseModel):
    program_name: Optional[str] = None
    description: Optional[str] = None
    training_type: Optional[str] = None
    delivery_mode: Optional[str] = None
    priority: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    estimated_participants: Optional[int] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("delivery_mode")
    @classmethod
    def delivery_mode_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_DELIVERY_MODES:
            raise ValueError(f"delivery_mode must be one of {VALID_DELIVERY_MODES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v


class TrainerAssign(BaseModel):
    assigned_trainer_id: uuid.UUID


class CoordinatorAssign(BaseModel):
    coordinator_id: uuid.UUID


class CompleteEngagement(BaseModel):
    actual_end_date: Optional[date] = None
    actual_participants: Optional[int] = None
    notes: Optional[str] = None


class CancelEngagement(BaseModel):
    notes: Optional[str] = None


class TrainingEngagementListOut(BaseModel):
    items: list[TrainingEngagementOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int


class TrainingEngagementFilters(BaseModel):
    workspace_id: uuid.UUID
    status: Optional[str] = None
    trainer_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    delivery_mode: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = 50
