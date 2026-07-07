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


# ── Invoice Payment schemas ────────────────────────────────────────────────────

PAYMENT_METHODS = frozenset({"cash", "bank_transfer", "upi", "credit_card", "cheque", "other"})
PAYMENT_STATUSES = frozenset({"pending", "confirmed", "cancelled"})


class InvoicePaymentCreate(BaseModel):
    workspace_id: uuid.UUID
    invoice_id: uuid.UUID
    customer_id: uuid.UUID
    payment_date: date | None = None
    amount: Decimal
    payment_method: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    created_by: uuid.UUID | None = None


class InvoicePaymentUpdate(BaseModel):
    payment_date: date | None = None
    amount: Decimal | None = None
    payment_method: str | None = None
    reference_number: str | None = None
    notes: str | None = None


class InvoicePaymentOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    invoice_id: uuid.UUID
    customer_id: uuid.UUID
    payment_date: date | None = None
    amount: Decimal | None = None
    payment_method: str | None = None
    reference_number: str | None = None
    status: str
    notes: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class InvoicePaymentFilters(BaseModel):
    workspace_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    status: str | None = None
    payment_method: str | None = None
    payment_date_from: date | None = None
    payment_date_to: date | None = None
    search: str | None = None
    cursor: str | None = None
    limit: int = 50


class InvoicePaymentListOut(BaseModel):
    items: list[InvoicePaymentOut]
    total: int
    next_cursor: str | None = None
    has_more: bool


class RevenueSummaryOut(BaseModel):
    total_collected: Decimal = Decimal("0.00")
    total_outstanding: Decimal = Decimal("0.00")
    total_overdue: Decimal = Decimal("0.00")
    count_pending_payments: int = 0
    count_confirmed_payments: int = 0
    count_cancelled_payments: int = 0
    partial_payment_invoices: int = 0
