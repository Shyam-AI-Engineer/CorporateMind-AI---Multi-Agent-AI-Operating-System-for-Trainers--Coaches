"""Training Engagement domain events — Sprint 42."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class TrainingEngagementCreated:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingStarted:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingCompleted:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingCancelled:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainerAssigned:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    trainer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CoordinatorAssigned:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    coordinator_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
