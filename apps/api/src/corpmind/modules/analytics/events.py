"""Analytics domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class DailyRollupComputed:
    tenant_id: uuid.UUID
    rollup_date: date
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AnomalyDetected:
    tenant_id: uuid.UUID
    metric: str
    value: float
    threshold: float
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
