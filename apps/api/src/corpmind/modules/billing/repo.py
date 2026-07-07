"""Billing repository."""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.billing.models import CustomerInvoice, InvoicePayment, Subscription, UsageMeter
from corpmind.modules.billing.schemas import InvoiceKPIsOut, RevenueSummaryOut


class SubscriptionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active(self) -> Subscription | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.tenant_id == ctx.org_id,
                Subscription.status == "active",
            )
        )
        return result.scalar_one_or_none()


class UsageMeterRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_subscription(self, subscription_id: uuid.UUID) -> UsageMeter | None:
        result = await self._session.execute(
            select(UsageMeter).where(UsageMeter.subscription_id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def increment_ai_spend(self, subscription_id: uuid.UUID, amount_inr: float) -> None:
        """Upsert the UsageMeter row for the given subscription.

        INSERT on first call (brand-new tenant), UPDATE on every subsequent call.
        Uses ON CONFLICT on the named unique constraint so the operation is
        atomic — no race condition between concurrent LLM calls for the same tenant.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        ctx = get_tenant_context()
        stmt = (
            pg_insert(UsageMeter)
            .values(
                id=uuid.uuid4(),
                subscription_id=subscription_id,
                tenant_id=ctx.org_id,
                ai_spend_inr=amount_inr,
                ai_runs_used=1,
                outreach_sends_used=0,
            )
            .on_conflict_do_update(
                constraint="uq_usage_meters_subscription_id",
                set_={
                    "ai_spend_inr": UsageMeter.ai_spend_inr + amount_inr,
                    "ai_runs_used": UsageMeter.ai_runs_used + 1,
                },
            )
        )
        await self._session.execute(stmt)

    async def increment_outreach_sends(self, subscription_id: uuid.UUID) -> None:
        """Increment the outreach send counter by 1 for the given subscription.

        Same upsert pattern as increment_ai_spend — atomic, idempotency-safe.
        Called by the Celery send task after a successful channel dispatch.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        ctx = get_tenant_context()
        stmt = (
            pg_insert(UsageMeter)
            .values(
                id=uuid.uuid4(),
                subscription_id=subscription_id,
                tenant_id=ctx.org_id,
                ai_spend_inr=0.0,
                ai_runs_used=0,
                outreach_sends_used=1,
            )
            .on_conflict_do_update(
                constraint="uq_usage_meters_subscription_id",
                set_={
                    "outreach_sends_used": UsageMeter.outreach_sends_used + 1,
                },
            )
        )
        await self._session.execute(stmt)


# ── Cursor helpers ────────────────────────────────────────────────────────────

def _encode_invoice_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_invoice_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


# ── CustomerInvoiceRepo ───────────────────────────────────────────────────────

class CustomerInvoiceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: CustomerInvoice) -> CustomerInvoice:
        self._session.add(record)
        return record

    async def find_by_id(self, record_id: uuid.UUID) -> Optional[CustomerInvoice]:
        result = await self._session.execute(
            select(CustomerInvoice).where(CustomerInvoice.id == record_id)
        )
        return result.scalar_one_or_none()

    async def find_by_invoice_number(
        self, tenant_id: uuid.UUID, invoice_number: str
    ) -> Optional[CustomerInvoice]:
        result = await self._session.execute(
            select(CustomerInvoice).where(
                CustomerInvoice.tenant_id == tenant_id,
                CustomerInvoice.invoice_number == invoice_number,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_customer_id(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerInvoice]:
        result = await self._session.execute(
            select(CustomerInvoice)
            .where(
                CustomerInvoice.workspace_id == workspace_id,
                CustomerInvoice.customer_id == customer_id,
            )
            .order_by(CustomerInvoice.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_fields(self, record_id: uuid.UUID, **values: Any) -> None:
        record = await self.find_by_id(record_id)
        if record:
            for key, value in values.items():
                setattr(record, key, value)

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        customer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        invoice_date_from: Optional[date] = None,
        invoice_date_to: Optional[date] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
        renewal_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(CustomerInvoice).where(
            CustomerInvoice.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, customer_id, status, invoice_date_from, invoice_date_to,
            due_date_from, due_date_to, renewal_id, search,
        )
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        customer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        invoice_date_from: Optional[date] = None,
        invoice_date_to: Optional[date] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
        renewal_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[CustomerInvoice]:
        q = select(CustomerInvoice).where(
            CustomerInvoice.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, customer_id, status, invoice_date_from, invoice_date_to,
            due_date_from, due_date_to, renewal_id, search,
        )
        if cursor:
            cur_ts, cur_id = _decode_invoice_cursor(cursor)
            q = q.where(
                (CustomerInvoice.created_at < cur_ts)
                | (
                    (CustomerInvoice.created_at == cur_ts)
                    & (CustomerInvoice.id < cur_id)
                )
            )
        q = q.order_by(
            CustomerInvoice.created_at.desc(), CustomerInvoice.id.desc()
        ).limit(limit + 1)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def fetch_kpis(self, workspace_id: uuid.UUID) -> InvoiceKPIsOut:
        """Single aggregation query for KPI card totals."""
        rows = await self._session.execute(
            text(
                "SELECT status, "
                "  COUNT(*) AS cnt, "
                "  COALESCE(SUM(total_amount), 0) AS total "
                "FROM customer_invoices "
                "WHERE workspace_id = :ws "
                "GROUP BY status"
            ),
            {"ws": str(workspace_id)},
        )
        count_map: dict[str, int] = {}
        amount_map: dict[str, Decimal] = {}
        for row in rows:
            count_map[row.status] = int(row.cnt)
            amount_map[row.status] = Decimal(str(row.total))

        outstanding_statuses = {"issued", "overdue"}
        total_outstanding = sum(
            amount_map.get(s, Decimal("0")) for s in outstanding_statuses
        )
        return InvoiceKPIsOut(
            total_outstanding=total_outstanding,
            total_paid=amount_map.get("paid", Decimal("0")),
            total_overdue=amount_map.get("overdue", Decimal("0")),
            count_draft=count_map.get("draft", 0),
            count_issued=count_map.get("issued", 0),
            count_paid=count_map.get("paid", 0),
            count_overdue=count_map.get("overdue", 0),
            count_cancelled=count_map.get("cancelled", 0),
        )

    def _apply_filters(
        self,
        q: Any,
        customer_id: Optional[uuid.UUID],
        status: Optional[str],
        invoice_date_from: Optional[date],
        invoice_date_to: Optional[date],
        due_date_from: Optional[date],
        due_date_to: Optional[date],
        renewal_id: Optional[uuid.UUID],
        search: Optional[str],
    ) -> Any:
        if customer_id:
            q = q.where(CustomerInvoice.customer_id == customer_id)
        if status:
            q = q.where(CustomerInvoice.status == status)
        if invoice_date_from:
            q = q.where(CustomerInvoice.invoice_date >= invoice_date_from)
        if invoice_date_to:
            q = q.where(CustomerInvoice.invoice_date <= invoice_date_to)
        if due_date_from:
            q = q.where(CustomerInvoice.due_date >= due_date_from)
        if due_date_to:
            q = q.where(CustomerInvoice.due_date <= due_date_to)
        if renewal_id:
            q = q.where(CustomerInvoice.renewal_id == renewal_id)
        if search:
            q = q.where(
                or_(
                    CustomerInvoice.invoice_number.ilike(f"%{search}%"),
                    CustomerInvoice.notes.ilike(f"%{search}%"),
                )
            )
        return q


# ── Payment cursor helpers ─────────────────────────────────────────────────────

def _encode_payment_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_payment_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


# ── InvoicePaymentRepo ────────────────────────────────────────────────────────

class InvoicePaymentRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: InvoicePayment) -> InvoicePayment:
        self._session.add(record)
        return record

    async def find_by_id(self, record_id: uuid.UUID) -> Optional[InvoicePayment]:
        result = await self._session.execute(
            select(InvoicePayment).where(InvoicePayment.id == record_id)
        )
        return result.scalar_one_or_none()

    async def update_fields(self, record_id: uuid.UUID, **values: Any) -> None:
        record = await self.find_by_id(record_id)
        if record:
            for key, value in values.items():
                setattr(record, key, value)

    async def list_by_invoice(self, invoice_id: uuid.UUID) -> list[InvoicePayment]:
        result = await self._session.execute(
            select(InvoicePayment)
            .where(InvoicePayment.invoice_id == invoice_id)
            .order_by(InvoicePayment.created_at.desc())
        )
        return list(result.scalars().all())

    async def sum_confirmed_for_invoice(self, invoice_id: uuid.UUID) -> Decimal:
        """Sum of amount for all confirmed payments on this invoice."""
        result = await self._session.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) FROM invoice_payments "
                "WHERE invoice_id = :invoice_id AND status = 'confirmed'"
            ),
            {"invoice_id": str(invoice_id)},
        )
        return Decimal(str(result.scalar_one()))

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        invoice_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        payment_method: Optional[str] = None,
        payment_date_from: Optional[date] = None,
        payment_date_to: Optional[date] = None,
        search: Optional[str] = None,
    ) -> int:
        q = select(func.count()).select_from(InvoicePayment).where(
            InvoicePayment.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, invoice_id, customer_id, status, payment_method,
            payment_date_from, payment_date_to, search,
        )
        result = await self._session.execute(q)
        return result.scalar_one()

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        invoice_id: Optional[uuid.UUID] = None,
        customer_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        payment_method: Optional[str] = None,
        payment_date_from: Optional[date] = None,
        payment_date_to: Optional[date] = None,
        search: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> list[InvoicePayment]:
        q = select(InvoicePayment).where(
            InvoicePayment.workspace_id == workspace_id
        )
        q = self._apply_filters(
            q, invoice_id, customer_id, status, payment_method,
            payment_date_from, payment_date_to, search,
        )
        if cursor:
            cur_ts, cur_id = _decode_payment_cursor(cursor)
            q = q.where(
                (InvoicePayment.created_at < cur_ts)
                | (
                    (InvoicePayment.created_at == cur_ts)
                    & (InvoicePayment.id < cur_id)
                )
            )
        q = q.order_by(
            InvoicePayment.created_at.desc(), InvoicePayment.id.desc()
        ).limit(limit + 1)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def fetch_revenue_summary(self, workspace_id: uuid.UUID) -> RevenueSummaryOut:
        """Revenue summary aggregation: payment counts/sums + outstanding invoice totals."""
        payment_rows = await self._session.execute(
            text(
                "SELECT status, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total "
                "FROM invoice_payments WHERE workspace_id = :ws GROUP BY status"
            ),
            {"ws": str(workspace_id)},
        )
        pcnt: dict[str, int] = {}
        pamt: dict[str, Decimal] = {}
        for row in payment_rows:
            pcnt[row.status] = int(row.cnt)
            pamt[row.status] = Decimal(str(row.total))

        invoice_rows = await self._session.execute(
            text(
                "SELECT status, COALESCE(SUM(total_amount), 0) AS total "
                "FROM customer_invoices "
                "WHERE workspace_id = :ws AND status IN ('issued', 'overdue') "
                "GROUP BY status"
            ),
            {"ws": str(workspace_id)},
        )
        iamt: dict[str, Decimal] = {}
        for row in invoice_rows:
            iamt[row.status] = Decimal(str(row.total))

        partial_row = await self._session.execute(
            text(
                "SELECT COUNT(DISTINCT ip.invoice_id) "
                "FROM invoice_payments ip "
                "JOIN customer_invoices ci ON ip.invoice_id = ci.id "
                "WHERE ip.workspace_id = :ws AND ip.status = 'confirmed' "
                "AND ci.status != 'paid'"
            ),
            {"ws": str(workspace_id)},
        )
        partial_count = int(partial_row.scalar_one() or 0)

        return RevenueSummaryOut(
            total_collected=pamt.get("confirmed", Decimal("0.00")),
            total_outstanding=iamt.get("issued", Decimal("0.00")) + iamt.get("overdue", Decimal("0.00")),
            total_overdue=iamt.get("overdue", Decimal("0.00")),
            count_pending_payments=pcnt.get("pending", 0),
            count_confirmed_payments=pcnt.get("confirmed", 0),
            count_cancelled_payments=pcnt.get("cancelled", 0),
            partial_payment_invoices=partial_count,
        )

    def _apply_filters(
        self,
        q: Any,
        invoice_id: Optional[uuid.UUID],
        customer_id: Optional[uuid.UUID],
        status: Optional[str],
        payment_method: Optional[str],
        payment_date_from: Optional[date],
        payment_date_to: Optional[date],
        search: Optional[str],
    ) -> Any:
        if invoice_id:
            q = q.where(InvoicePayment.invoice_id == invoice_id)
        if customer_id:
            q = q.where(InvoicePayment.customer_id == customer_id)
        if status:
            q = q.where(InvoicePayment.status == status)
        if payment_method:
            q = q.where(InvoicePayment.payment_method == payment_method)
        if payment_date_from:
            q = q.where(InvoicePayment.payment_date >= payment_date_from)
        if payment_date_to:
            q = q.where(InvoicePayment.payment_date <= payment_date_to)
        if search:
            q = q.where(
                or_(
                    InvoicePayment.reference_number.ilike(f"%{search}%"),
                    InvoicePayment.notes.ilike(f"%{search}%"),
                )
            )
        return q
