"""Notification center schemas — Sprint 32."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

_VALID_NOTIFICATION_TYPES: frozenset[str] = frozenset({
    "approval_assigned",
    "approval_completed",
    "task_assigned",
    "task_completed",
    "recommendation_created",
    "recommendation_accepted",
    "recommendation_completed",
    "campaign_launched",
    "proposal_accepted",
    "team_invited",
    "comment_added",
    # Sprint 34: workflow execution notifications
    "workflow_started",
    "workflow_cancelled",
    "workflow_completed",
    "workflow_step_completed",
})

_VALID_PRIORITIES: frozenset[str] = frozenset({"low", "medium", "high", "urgent"})


# ── Input schemas ─────────────────────────────────────────────────────────────

class NotificationIn(BaseModel):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    priority: str = "medium"
    extra_data: dict[str, Any] | None = None

    @field_validator("notification_type")
    @classmethod
    def validate_notification_type(cls, v: str) -> str:
        if v not in _VALID_NOTIFICATION_TYPES:
            raise ValueError(
                f"notification_type must be one of {sorted(_VALID_NOTIFICATION_TYPES)}"
            )
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in _VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)}")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be empty")
        return v


# ── Output schemas ────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    title: str
    message: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    priority: str
    is_read: bool
    read_at: datetime | None
    extra_data: dict[str, Any] | None
    created_at: datetime


class NotificationListPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None
    has_more: bool


class UnreadCountOut(BaseModel):
    count: int
