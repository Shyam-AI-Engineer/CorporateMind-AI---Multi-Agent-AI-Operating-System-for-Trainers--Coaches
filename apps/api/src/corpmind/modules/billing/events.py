"""Billing domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class BudgetThresholdReached:
    tenant_id: uuid.UUID
    threshold_pct: int  # 70 | 85 | 95 | 100
    spend_inr: float
    budget_inr: float
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SubscriptionRenewed:
    tenant_id: uuid.UUID
    plan_tier: str
    new_period_end: datetime
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
