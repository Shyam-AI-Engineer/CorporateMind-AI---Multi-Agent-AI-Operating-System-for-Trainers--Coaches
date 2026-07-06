"""Customer Success domain events — Sprint 47."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CustomerSuccessCreated:
    success_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    health_status: str
    risk_level: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerSuccessUpdated:
    success_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerHealthChanged:
    success_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    previous_health: str
    new_health: str
    health_score: int | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FollowupScheduled:
    success_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    next_followup_date: str  # ISO date string
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
