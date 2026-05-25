"""Compliance domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ComplianceBlocked:
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    channel: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class UnsubscribeRecorded:
    tenant_id: uuid.UUID
    contact_hash: str
    channel: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
