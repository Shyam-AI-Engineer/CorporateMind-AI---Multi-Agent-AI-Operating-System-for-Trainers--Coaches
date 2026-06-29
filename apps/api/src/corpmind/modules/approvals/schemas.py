"""Approval workflow schemas — Sprint 31."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

_VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "in_review", "approved", "rejected", "cancelled"}
)
_VALID_DECISIONS: frozenset[str] = frozenset({"approve", "reject", "none"})
_VALID_PRIORITIES: frozenset[str] = frozenset({"low", "medium", "high", "urgent"})
_VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {"task", "recommendation", "campaign", "proposal"}
)


# ── Input schemas ─────────────────────────────────────────────────────────────

class ApprovalRequestIn(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None = None
    priority: str = "medium"
    comments: str | None = None
    due_date: date | None = None
    assigned_reviewer: str | None = None

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in _VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(_VALID_ENTITY_TYPES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in _VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)}")
        return v

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) > 4000:
                raise ValueError("comments cannot exceed 4000 characters")
        return v or None


class ApprovalAssignIn(BaseModel):
    assigned_reviewer: str

    @field_validator("assigned_reviewer")
    @classmethod
    def validate_reviewer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("assigned_reviewer cannot be empty")
        return v


class ApprovalDecisionIn(BaseModel):
    comments: str | None = None

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) > 4000:
                raise ValueError("comments cannot exceed 4000 characters")
        return v or None


# ── Output schemas ────────────────────────────────────────────────────────────

class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    requested_by: str
    assigned_reviewer: str | None
    priority: str
    status: str
    decision: str
    comments: str | None
    due_date: date | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalListPage(BaseModel):
    items: list[ApprovalRequestOut]
    next_cursor: str | None
    has_more: bool


class ApprovalTimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    approval_request_id: uuid.UUID
    event_type: str
    actor_user_id: str
    notes: str | None
    occurred_at: datetime
