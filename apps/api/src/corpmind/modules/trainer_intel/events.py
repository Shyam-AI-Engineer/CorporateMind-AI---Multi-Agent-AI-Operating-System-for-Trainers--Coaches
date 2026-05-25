"""Trainer intelligence domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class TrainerProfileExtracted:
    profile_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainerProfileLocked:
    profile_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
