"""Identity domain events published to the in-process event bus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class UserRegistered:
    user_id: uuid.UUID
    org_id: uuid.UUID
    email: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class UserLoggedIn:
    user_id: uuid.UUID
    org_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class PlanUpgraded:
    org_id: uuid.UUID
    from_tier: str
    to_tier: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
