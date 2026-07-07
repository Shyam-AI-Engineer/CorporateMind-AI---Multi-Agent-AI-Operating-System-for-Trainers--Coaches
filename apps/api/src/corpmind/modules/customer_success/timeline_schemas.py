"""Timeline schemas for Customer 360 — Sprint 49.

Pure read-only DTOs. No mutation schemas needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

VALID_TIMELINE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "customer_created",
        "training_engagement_created",
        "training_session_started",
        "training_session_completed",
        "attendance_recorded",
        "certificate_issued",
        "feedback_submitted",
        "customer_health_updated",
        "renewal_created",
        "renewal_status_changed",
    }
)


class CustomerTimelineEventOut(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    title: str
    entity_type: str | None = None
    entity_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class CustomerTimelinePageOut(BaseModel):
    items: list[CustomerTimelineEventOut]
    next_cursor: str | None = None
    has_more: bool = False
    total: int = 0


class CustomerRelationshipSummaryOut(BaseModel):
    customer_id: str
    total_trainings: int = 0
    completed_trainings: int = 0
    total_certificates: int = 0
    avg_feedback_rating: float | None = None
    current_health: str | None = None
    renewal_status: str | None = None
    latest_activity_at: datetime | None = None
    days_since_last_interaction: int | None = None


class Customer360Out(BaseModel):
    customer_id: str
    summary: CustomerRelationshipSummaryOut
    recent_events: list[CustomerTimelineEventOut] = Field(default_factory=list)
