"""Billing module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.billing.schemas import (
    BillingSummaryOut,
    CustomerInvoiceCreate,
    CustomerInvoiceFilters,
    CustomerInvoiceListOut,
    CustomerInvoiceOut,
    CustomerInvoiceUpdate,
    InvoiceKPIsOut,
    InvoicePaymentCreate,
    InvoicePaymentFilters,
    InvoicePaymentListOut,
    InvoicePaymentOut,
    InvoicePaymentUpdate,
    MarkInvoicePaid,
    RevenueSummaryOut,
    SubscriptionOut,
    UsageSummary,
)
from corpmind.modules.billing.service import BillingService, CustomerInvoiceService, PaymentService

router = APIRouter()


def _invoice_svc(session: AsyncSession = Depends(get_session)) -> CustomerInvoiceService:
    return CustomerInvoiceService(session)


@router.get(
    "/subscription",
    response_model=SubscriptionOut,
    summary="Active subscription — plan tier, limits, and billing period",
)
async def get_subscription(
    session: AsyncSession = Depends(get_session),
) -> SubscriptionOut:
    return await BillingService(session).get_subscription()


@router.get(
    "/usage",
    response_model=UsageSummary,
    summary="Current-period usage — spend, runs, and sends consumed",
)
async def get_usage(
    session: AsyncSession = Depends(get_session),
) -> UsageSummary:
    return await BillingService(session).get_usage()


@router.get(
    "/summary",
    response_model=BillingSummaryOut,
    summary="Subscription + usage combined — the dashboard billing widget",
)
async def get_summary(
    session: AsyncSession = Depends(get_session),
) -> BillingSummaryOut:
    return await BillingService(session).get_summary()


# ── Invoice endpoints ─────────────────────────────────────────────────────────

@router.get("/invoices/kpis", response_model=InvoiceKPIsOut)
async def get_invoice_kpis(
    workspace_id: uuid.UUID = Query(...),
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> InvoiceKPIsOut:
    return await svc.get_kpis(workspace_id)


@router.post(
    "/invoices",
    response_model=CustomerInvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    body: CustomerInvoiceCreate,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.create(body)


@router.get("/invoices", response_model=CustomerInvoiceListOut)
async def list_invoices(
    workspace_id: uuid.UUID = Query(...),
    customer_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    invoice_date_from: str | None = Query(None),
    invoice_date_to: str | None = Query(None),
    due_date_from: str | None = Query(None),
    due_date_to: str | None = Query(None),
    renewal_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceListOut:
    from datetime import date as _date

    def _pd(v: str | None):  # type: ignore[return]
        return _date.fromisoformat(v) if v else None

    filters = CustomerInvoiceFilters(
        workspace_id=workspace_id,
        customer_id=customer_id,
        status=status_filter,
        invoice_date_from=_pd(invoice_date_from),
        invoice_date_to=_pd(invoice_date_to),
        due_date_from=_pd(due_date_from),
        due_date_to=_pd(due_date_to),
        renewal_id=renewal_id,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await svc.list(filters)


@router.get("/invoices/{record_id}", response_model=CustomerInvoiceOut)
async def get_invoice(
    record_id: uuid.UUID,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.get(record_id)


@router.patch("/invoices/{record_id}", response_model=CustomerInvoiceOut)
async def update_invoice(
    record_id: uuid.UUID,
    body: CustomerInvoiceUpdate,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.update(record_id, body)


@router.post("/invoices/{record_id}/issue", response_model=CustomerInvoiceOut)
async def issue_invoice(
    record_id: uuid.UUID,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.issue(record_id)


@router.post("/invoices/{record_id}/mark-paid", response_model=CustomerInvoiceOut)
async def mark_invoice_paid(
    record_id: uuid.UUID,
    body: MarkInvoicePaid,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.mark_paid(record_id, body)


@router.post("/invoices/{record_id}/cancel", response_model=CustomerInvoiceOut)
async def cancel_invoice(
    record_id: uuid.UUID,
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceOut:
    return await svc.cancel(record_id)


# ── Customer-scoped invoice sub-router ────────────────────────────────────────

customer_invoice_router = APIRouter()


@customer_invoice_router.get(
    "/{customer_id}/invoices", response_model=CustomerInvoiceListOut
)
async def get_invoices_by_customer(
    customer_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: CustomerInvoiceService = Depends(_invoice_svc),
) -> CustomerInvoiceListOut:
    filters = CustomerInvoiceFilters(
        workspace_id=workspace_id,
        customer_id=customer_id,
    )
    return await svc.list(filters)


# ── Invoice payment history sub-route (under billing router) ──────────────────

@router.get("/invoices/{record_id}/payments", response_model=list[InvoicePaymentOut])
async def list_invoice_payments(
    record_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[InvoicePaymentOut]:
    return await PaymentService(session).list_invoice_payments(record_id)


# ── Payment endpoints ─────────────────────────────────────────────────────────

def _payment_svc(session: AsyncSession = Depends(get_session)) -> PaymentService:
    return PaymentService(session)


@router.get("/revenue-summary", response_model=RevenueSummaryOut)
async def get_revenue_summary(
    workspace_id: uuid.UUID = Query(...),
    svc: PaymentService = Depends(_payment_svc),
) -> RevenueSummaryOut:
    return await svc.get_revenue_summary(workspace_id)


@router.post(
    "/payments",
    response_model=InvoicePaymentOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    body: InvoicePaymentCreate,
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentOut:
    return await svc.record_payment(body)


@router.get("/payments", response_model=InvoicePaymentListOut)
async def list_payments(
    workspace_id: uuid.UUID = Query(...),
    invoice_id: uuid.UUID | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    payment_method: str | None = Query(None),
    payment_date_from: str | None = Query(None),
    payment_date_to: str | None = Query(None),
    search: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentListOut:
    from datetime import date as _date

    def _pd(v: str | None):  # type: ignore[return]
        return _date.fromisoformat(v) if v else None

    filters = InvoicePaymentFilters(
        workspace_id=workspace_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        status=status_filter,
        payment_method=payment_method,
        payment_date_from=_pd(payment_date_from),
        payment_date_to=_pd(payment_date_to),
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await svc.list_payments(filters)


@router.get("/payments/{record_id}", response_model=InvoicePaymentOut)
async def get_payment(
    record_id: uuid.UUID,
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentOut:
    return await svc.get_payment(record_id)


@router.patch("/payments/{record_id}", response_model=InvoicePaymentOut)
async def update_payment(
    record_id: uuid.UUID,
    body: InvoicePaymentUpdate,
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentOut:
    return await svc.update_payment(record_id, body)


@router.post("/payments/{record_id}/confirm", response_model=InvoicePaymentOut)
async def confirm_payment(
    record_id: uuid.UUID,
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentOut:
    return await svc.confirm_payment(record_id)


@router.post("/payments/{record_id}/cancel", response_model=InvoicePaymentOut)
async def cancel_payment(
    record_id: uuid.UUID,
    svc: PaymentService = Depends(_payment_svc),
) -> InvoicePaymentOut:
    return await svc.cancel_payment(record_id)
