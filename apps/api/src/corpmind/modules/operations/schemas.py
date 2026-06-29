"""Operations module schemas — Sprint 29."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator

_VALID_PRIORITIES: frozenset[str] = frozenset({"high", "medium", "low"})
_VALID_STATUSES: frozenset[str] = frozenset({"backlog", "in_progress", "blocked", "completed"})
_VALID_SOURCE_TYPES: frozenset[str] = frozenset(
    {"manual", "crm", "campaign", "proposal", "recommendation"}
)


class BusinessTaskIn(BaseModel):
    workspace_id: uuid.UUID
    title: str
    description: str | None = None
    priority: str = "medium"
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    assignee: str | None = None
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > 500:
            raise ValueError("title must not exceed 500 characters")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in _VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)}, got '{v}'")
        return v

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}, got '{v}'")
        return v


class BusinessTaskUpdate(BaseModel):
    status: str | None = None
    assignee: str | None = None
    due_date: date | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}, got '{v}'")
        return v


class BusinessTaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    source_type: str | None
    source_id: uuid.UUID | None
    title: str
    description: str | None
    priority: str
    status: str
    assignee: str | None
    assigned_user_id: uuid.UUID | None
    due_date: date | None
    completed_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class GroupedTasksOut(BaseModel):
    backlog: list[BusinessTaskOut]
    in_progress: list[BusinessTaskOut]
    blocked: list[BusinessTaskOut]
    completed: list[BusinessTaskOut]
    total: int


class WorkloadOut(BaseModel):
    total_open: int
    overdue: int
    completed_today: int
    blocked: int
    by_priority: dict[str, int]
    by_assignee: dict[str, int]
