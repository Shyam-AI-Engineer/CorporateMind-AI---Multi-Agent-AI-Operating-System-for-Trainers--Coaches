"""Billing domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal


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


# ── Invoice events ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InvoiceCreated:
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class InvoiceIssued:
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    total_amount: Decimal | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class InvoicePaid:
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    payment_date: date
    total_amount: Decimal | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class InvoiceCancelled:
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
