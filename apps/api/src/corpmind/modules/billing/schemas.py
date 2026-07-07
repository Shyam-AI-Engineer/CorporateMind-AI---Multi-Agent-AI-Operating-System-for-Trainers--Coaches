"""Billing schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    plan_tier: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    ai_run_limit: int
    outreach_send_limit: int
    ai_budget_inr: float
    model_config = {"from_attributes": True}


class UsageSummary(BaseModel):
    ai_runs_used: int
    ai_runs_limit: int
    outreach_sends_used: int
    outreach_sends_limit: int
    ai_spend_inr: float
    ai_budget_inr: float
    budget_utilization_pct: float


class BillingSummaryOut(BaseModel):
    subscription: SubscriptionOut
    usage: UsageSummary


# ── Customer Invoice schemas ───────────────────────────────────────────────────

INVOICE_STATUSES = frozenset({"draft", "issued", "paid", "cancelled", "overdue"})


class CustomerInvoiceCreate(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    amount: Decimal | None = None
    tax_amount: Decimal | None = Field(default=None)
    total_amount: Decimal | None = None
    currency: str = "INR"
    notes: str | None = None
    renewal_id: uuid.UUID | None = None


class CustomerInvoiceUpdate(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    notes: str | None = None


class MarkInvoicePaid(BaseModel):
    payment_date: date


class CustomerInvoiceOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    status: str
    payment_date: date | None = None
    renewal_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CustomerInvoiceFilters(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    status: str | None = None
    invoice_date_from: date | None = None
    invoice_date_to: date | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    renewal_id: uuid.UUID | None = None
    search: str | None = None
    cursor: str | None = None
    limit: int = 50


class CustomerInvoiceListOut(BaseModel):
    items: list[CustomerInvoiceOut]
    total: int
    next_cursor: str | None = None
    has_more: bool


class InvoiceKPIsOut(BaseModel):
    total_outstanding: Decimal = Decimal("0.00")
    total_paid: Decimal = Decimal("0.00")
    total_overdue: Decimal = Decimal("0.00")
    count_draft: int = 0
    count_issued: int = 0
    count_paid: int = 0
    count_overdue: int = 0
    count_cancelled: int = 0
