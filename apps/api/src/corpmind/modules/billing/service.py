"""Billing service — tenant provisioning and subscription lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.billing.events import (
    InvoiceCancelled,
    InvoiceCreated,
    InvoiceFullyPaid,
    InvoiceIssued,
    InvoicePaid,
    PaymentCancelled,
    PaymentConfirmed,
    PaymentRecorded,
)
from corpmind.modules.billing.models import CustomerInvoice, InvoicePayment, Subscription, UsageMeter
from corpmind.modules.billing.repo import (
    CustomerInvoiceRepo,
    InvoicePaymentRepo,
    SubscriptionRepo,
    UsageMeterRepo,
    _encode_payment_cursor,
)
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

log = structlog.get_logger(__name__)

_STARTER_BUDGET_INR = 400.0
_STARTER_AI_RUNS = 1000
_STARTER_SENDS = 500
_PERIOD_DAYS = 30


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def provision_new_tenant(self, org_id: uuid.UUID) -> None:
        """Create the initial Subscription + UsageMeter for a freshly registered org.

        Both rows are added to the caller's session and flushed (but not
        committed) so that foreign-key lookups within the same transaction
        can reference subscription.id immediately.

        Caller contract: set_rls_tenant(session, org_id) MUST be called before
        this method so that the RLS WITH CHECK policy accepts the INSERTs.
        """
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            tenant_id=org_id,
            plan_tier="starter",
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=_PERIOD_DAYS),
            ai_run_limit=_STARTER_AI_RUNS,
            outreach_send_limit=_STARTER_SENDS,
            ai_budget_inr=_STARTER_BUDGET_INR,
        )
        self._session.add(subscription)
        await self._session.flush()

        meter = UsageMeter(
            tenant_id=org_id,
            subscription_id=subscription.id,
            ai_runs_used=0,
            outreach_sends_used=0,
            ai_spend_inr=0.0,
        )
        self._session.add(meter)
        await self._session.flush()

        log.info(
            "billing.tenant_provisioned",
            org_id=str(org_id),
            subscription_id=str(subscription.id),
            budget_inr=_STARTER_BUDGET_INR,
        )

    async def get_subscription(self) -> SubscriptionOut:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        return SubscriptionOut.model_validate(sub)

    async def get_usage(self) -> UsageSummary:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        meter = await UsageMeterRepo(self._session).find_by_subscription(sub.id)
        return _build_usage_summary(sub, meter)

    async def get_summary(self) -> BillingSummaryOut:
        sub = await SubscriptionRepo(self._session).find_active()
        if sub is None:
            raise NotFoundError("No active subscription found for this tenant")
        meter = await UsageMeterRepo(self._session).find_by_subscription(sub.id)
        return BillingSummaryOut(
            subscription=SubscriptionOut.model_validate(sub),
            usage=_build_usage_summary(sub, meter),
        )


def _build_usage_summary(sub: Subscription, meter: UsageMeter | None) -> UsageSummary:
    spent = meter.ai_spend_inr if meter else 0.0
    pct = round(spent / sub.ai_budget_inr * 100, 2) if sub.ai_budget_inr > 0 else 0.0
    return UsageSummary(
        ai_runs_used=meter.ai_runs_used if meter else 0,
        ai_runs_limit=sub.ai_run_limit,
        outreach_sends_used=meter.outreach_sends_used if meter else 0,
        outreach_sends_limit=sub.outreach_send_limit,
        ai_spend_inr=spent,
        ai_budget_inr=sub.ai_budget_inr,
        budget_utilization_pct=pct,
    )


# ── Invoice cache key helpers ─────────────────────────────────────────────────

_INVOICE_LIST_TTL = 300
_INVOICE_DETAIL_TTL = 300
_INVOICE_KPIS_TTL = 300

# Status-machine constants
_ISSUEABLES = frozenset({"draft"})
_PAYABLE_FROM = frozenset({"issued"})
_CANCELLABLE_FROM = frozenset({"draft", "issued", "overdue"})


def _invoice_list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:billing:invoices:list"


def _invoice_detail_key(org_id: uuid.UUID, record_id: uuid.UUID) -> str:
    return f"t:{org_id}:billing:invoices:detail:{record_id}"


def _invoice_kpis_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:billing:invoices:kpis"


# ── CustomerInvoiceService ────────────────────────────────────────────────────

class CustomerInvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CustomerInvoiceRepo(session)

    async def create(self, req: CustomerInvoiceCreate) -> CustomerInvoiceOut:
        ctx = get_tenant_context()

        if req.invoice_number:
            existing = await self._repo.find_by_invoice_number(
                ctx.org_id, req.invoice_number
            )
            if existing:
                raise ValidationError(
                    f"Invoice number '{req.invoice_number}' already exists for this tenant"
                )

        now = datetime.now(UTC)
        record = CustomerInvoice(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            invoice_number=req.invoice_number,
            invoice_date=req.invoice_date,
            due_date=req.due_date,
            amount=req.amount,
            tax_amount=req.tax_amount,
            total_amount=req.total_amount,
            currency=req.currency,
            status="draft",
            payment_date=None,
            renewal_id=req.renewal_id,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(record)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        await self._bust_kpis_cache(ctx.org_id, req.workspace_id)

        log.info(
            "billing.invoice.created",
            invoice_id=str(record.id),
            customer_id=str(req.customer_id),
            tenant_id=str(ctx.org_id),
        )
        event = InvoiceCreated(
            invoice_id=record.id,
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            invoice_number=req.invoice_number,
        )
        log.debug("billing.invoice.event", event_type=event.__class__.__name__)
        return CustomerInvoiceOut.model_validate(record)

    async def update(
        self, record_id: uuid.UUID, req: CustomerInvoiceUpdate
    ) -> CustomerInvoiceOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Invoice {record_id} not found")
        if record.status not in {"draft"}:
            raise ValidationError(
                f"Invoice in status '{record.status}' cannot be updated; only draft invoices are editable"
            )

        if req.invoice_number and req.invoice_number != record.invoice_number:
            existing = await self._repo.find_by_invoice_number(
                ctx.org_id, req.invoice_number
            )
            if existing and existing.id != record_id:
                raise ValidationError(
                    f"Invoice number '{req.invoice_number}' already exists for this tenant"
                )

        changes: dict = {}
        if req.invoice_number is not None:
            changes["invoice_number"] = req.invoice_number
        if req.invoice_date is not None:
            changes["invoice_date"] = req.invoice_date
        if req.due_date is not None:
            changes["due_date"] = req.due_date
        if req.amount is not None:
            changes["amount"] = req.amount
        if req.tax_amount is not None:
            changes["tax_amount"] = req.tax_amount
        if req.total_amount is not None:
            changes["total_amount"] = req.total_amount
        if req.currency is not None:
            changes["currency"] = req.currency
        if req.notes is not None:
            changes["notes"] = req.notes
        changes["updated_at"] = datetime.now(UTC)

        await self._repo.update_fields(record_id, **changes)
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        log.info("billing.invoice.updated", invoice_id=str(record_id), tenant_id=str(ctx.org_id))
        return CustomerInvoiceOut.model_validate(updated)

    async def issue(self, record_id: uuid.UUID) -> CustomerInvoiceOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Invoice {record_id} not found")
        if record.status not in _ISSUEABLES:
            raise ValidationError(
                f"Invoice in status '{record.status}' cannot be issued; must be draft"
            )

        await self._repo.update_fields(
            record_id, status="issued", updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        await self._bust_kpis_cache(ctx.org_id, updated.workspace_id)

        event = InvoiceIssued(
            invoice_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
            total_amount=updated.total_amount,
        )
        log.info("billing.invoice.issued", invoice_id=str(record_id), tenant_id=str(ctx.org_id))
        log.debug("billing.invoice.event", event_type=event.__class__.__name__)
        return CustomerInvoiceOut.model_validate(updated)

    async def mark_paid(
        self, record_id: uuid.UUID, req: MarkInvoicePaid
    ) -> CustomerInvoiceOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Invoice {record_id} not found")
        if record.status not in _PAYABLE_FROM:
            raise ValidationError(
                f"Invoice in status '{record.status}' cannot be marked paid; must be issued"
            )

        await self._repo.update_fields(
            record_id,
            status="paid",
            payment_date=req.payment_date,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        await self._bust_kpis_cache(ctx.org_id, updated.workspace_id)

        event = InvoicePaid(
            invoice_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
            payment_date=req.payment_date,
            total_amount=updated.total_amount,
        )
        log.info(
            "billing.invoice.paid",
            invoice_id=str(record_id),
            payment_date=str(req.payment_date),
            tenant_id=str(ctx.org_id),
        )
        log.debug("billing.invoice.event", event_type=event.__class__.__name__)
        return CustomerInvoiceOut.model_validate(updated)

    async def cancel(self, record_id: uuid.UUID) -> CustomerInvoiceOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Invoice {record_id} not found")
        if record.status not in _CANCELLABLE_FROM:
            raise ValidationError(
                f"Invoice in status '{record.status}' cannot be cancelled"
            )

        await self._repo.update_fields(
            record_id, status="cancelled", updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        await self._bust_kpis_cache(ctx.org_id, updated.workspace_id)

        event = InvoiceCancelled(
            invoice_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
        )
        log.info("billing.invoice.cancelled", invoice_id=str(record_id), tenant_id=str(ctx.org_id))
        log.debug("billing.invoice.event", event_type=event.__class__.__name__)
        return CustomerInvoiceOut.model_validate(updated)

    async def get(self, record_id: uuid.UUID) -> CustomerInvoiceOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _invoice_detail_key(ctx.org_id, record_id)
        try:
            cached = await redis.get(key)
            if cached:
                return CustomerInvoiceOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Invoice {record_id} not found")

        out = CustomerInvoiceOut.model_validate(record)
        try:
            await redis.set(key, out.model_dump_json(), ex=_INVOICE_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def list(self, filters: CustomerInvoiceFilters) -> CustomerInvoiceListOut:
        ctx = get_tenant_context()
        redis = get_redis()

        _is_default = (
            filters.customer_id is None
            and filters.status is None
            and filters.invoice_date_from is None
            and filters.invoice_date_to is None
            and filters.due_date_from is None
            and filters.due_date_to is None
            and filters.renewal_id is None
            and filters.search is None
            and filters.cursor is None
            and filters.limit == 50
        )
        if _is_default:
            key = _invoice_list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return CustomerInvoiceListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            customer_id=filters.customer_id,
            status=filters.status,
            invoice_date_from=filters.invoice_date_from,
            invoice_date_to=filters.invoice_date_to,
            due_date_from=filters.due_date_from,
            due_date_to=filters.due_date_to,
            renewal_id=filters.renewal_id,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            customer_id=filters.customer_id,
            status=filters.status,
            invoice_date_from=filters.invoice_date_from,
            invoice_date_to=filters.invoice_date_to,
            due_date_from=filters.due_date_from,
            due_date_to=filters.due_date_to,
            renewal_id=filters.renewal_id,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )
        has_more = len(rows) > filters.limit
        page = rows[: filters.limit]

        from corpmind.modules.billing.repo import _encode_invoice_cursor
        next_cursor = (
            _encode_invoice_cursor(page[-1].created_at, page[-1].id) if has_more else None
        )

        out = CustomerInvoiceListOut(
            items=[CustomerInvoiceOut.model_validate(r) for r in page],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )
        if _is_default:
            try:
                await redis.set(key, out.model_dump_json(), ex=_INVOICE_LIST_TTL)
            except Exception:
                pass
        return out

    async def get_kpis(self, workspace_id: uuid.UUID) -> InvoiceKPIsOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _invoice_kpis_key(ctx.org_id, workspace_id)
        try:
            cached = await redis.get(key)
            if cached:
                return InvoiceKPIsOut.model_validate_json(cached)
        except Exception:
            pass

        kpis = await self._repo.fetch_kpis(workspace_id)
        try:
            await redis.set(key, kpis.model_dump_json(), ex=_INVOICE_KPIS_TTL)
        except Exception:
            pass
        return kpis

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _bust_detail_cache(self, org_id: uuid.UUID, record_id: uuid.UUID) -> None:
        redis = get_redis()
        try:
            await redis.delete(_invoice_detail_key(org_id, record_id))
        except Exception:
            pass

    async def _bust_list_cache(self, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
        redis = get_redis()
        try:
            await redis.delete(_invoice_list_key(org_id, ws_id))
        except Exception:
            pass

    async def _bust_kpis_cache(self, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
        redis = get_redis()
        try:
            await redis.delete(_invoice_kpis_key(org_id, ws_id))
        except Exception:
            pass


# ── Payment cache key helpers ─────────────────────────────────────────────────

_PAYMENT_LIST_TTL = 300
_PAYMENT_DETAIL_TTL = 300
_PAYMENT_SUMMARY_TTL = 300

_CANCELLABLE_PAYMENT_FROM = frozenset({"pending", "confirmed"})


def _payment_list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:billing:payments:list"


def _payment_detail_key(org_id: uuid.UUID, record_id: uuid.UUID) -> str:
    return f"t:{org_id}:billing:payments:detail:{record_id}"


def _payment_summary_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:billing:payments:summary"


# ── PaymentService ────────────────────────────────────────────────────────────

class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payment_repo = InvoicePaymentRepo(session)
        self._invoice_repo = CustomerInvoiceRepo(session)

    async def record_payment(self, req: InvoicePaymentCreate) -> InvoicePaymentOut:
        ctx = get_tenant_context()

        invoice = await self._invoice_repo.find_by_id(req.invoice_id)
        if not invoice:
            raise NotFoundError(f"Invoice {req.invoice_id} not found")
        if invoice.status == "cancelled":
            raise ValidationError("Cannot add payment to a cancelled invoice")
        if req.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")

        now = datetime.now(UTC)
        record = InvoicePayment(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            invoice_id=req.invoice_id,
            customer_id=req.customer_id,
            payment_date=req.payment_date,
            amount=req.amount,
            payment_method=req.payment_method,
            reference_number=req.reference_number,
            status="pending",
            notes=req.notes,
            created_by=req.created_by,
            created_at=now,
            updated_at=now,
        )
        await self._payment_repo.create(record)
        await self._session.commit()

        await self._bust_list_and_summary(ctx.org_id, req.workspace_id)

        log.info(
            "billing.payment.recorded",
            payment_id=str(record.id),
            invoice_id=str(req.invoice_id),
            amount=str(req.amount),
            tenant_id=str(ctx.org_id),
        )
        event = PaymentRecorded(
            payment_id=record.id,
            invoice_id=req.invoice_id,
            tenant_id=ctx.org_id,
            customer_id=req.customer_id,
            amount=req.amount,
        )
        log.debug("billing.payment.event", event_type=event.__class__.__name__)
        return InvoicePaymentOut.model_validate(record)

    async def update_payment(
        self, record_id: uuid.UUID, req: InvoicePaymentUpdate
    ) -> InvoicePaymentOut:
        ctx = get_tenant_context()
        record = await self._payment_repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Payment {record_id} not found")
        if record.status != "pending":
            raise ValidationError(
                f"Payment in status '{record.status}' cannot be updated; only pending payments are editable"
            )
        if req.amount is not None and req.amount <= 0:
            raise ValidationError("Payment amount must be greater than zero")

        changes: dict = {}
        if req.payment_date is not None:
            changes["payment_date"] = req.payment_date
        if req.amount is not None:
            changes["amount"] = req.amount
        if req.payment_method is not None:
            changes["payment_method"] = req.payment_method
        if req.reference_number is not None:
            changes["reference_number"] = req.reference_number
        if req.notes is not None:
            changes["notes"] = req.notes
        changes["updated_at"] = datetime.now(UTC)

        await self._payment_repo.update_fields(record_id, **changes)
        await self._session.commit()
        updated = await self._payment_repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_and_list(ctx.org_id, record.workspace_id, record_id)
        log.info(
            "billing.payment.updated",
            payment_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        return InvoicePaymentOut.model_validate(updated)

    async def confirm_payment(self, record_id: uuid.UUID) -> InvoicePaymentOut:
        ctx = get_tenant_context()
        record = await self._payment_repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Payment {record_id} not found")
        if record.status != "pending":
            raise ValidationError(
                f"Payment in status '{record.status}' cannot be confirmed; must be pending"
            )

        invoice = await self._invoice_repo.find_by_id(record.invoice_id)
        if not invoice:
            raise NotFoundError(f"Invoice {record.invoice_id} not found")
        if invoice.status == "cancelled":
            raise ValidationError("Cannot confirm payment on a cancelled invoice")

        # Overpayment guard — only when both amounts are present
        if invoice.total_amount is not None and record.amount is not None:
            total_confirmed_so_far = await self._payment_repo.sum_confirmed_for_invoice(
                record.invoice_id
            )
            if total_confirmed_so_far + record.amount > invoice.total_amount:
                raise ValidationError(
                    f"Confirming this payment would exceed the invoice total of {invoice.total_amount}"
                )

        await self._payment_repo.update_fields(
            record_id, status="confirmed", updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        updated = await self._payment_repo.find_by_id(record_id)
        assert updated is not None

        # Auto-settle invoice when fully covered
        if invoice.total_amount is not None and invoice.status in {"issued", "overdue"}:
            total_confirmed = await self._payment_repo.sum_confirmed_for_invoice(
                record.invoice_id
            )
            if total_confirmed >= invoice.total_amount:
                from datetime import date as _date
                pay_date = updated.payment_date or _date.today()
                await self._invoice_repo.update_fields(
                    invoice.id,
                    status="paid",
                    payment_date=pay_date,
                    updated_at=datetime.now(UTC),
                )
                await self._session.commit()
                await self._bust_invoice_caches(ctx.org_id, invoice.workspace_id, invoice.id)
                fully_paid_event = InvoiceFullyPaid(
                    invoice_id=invoice.id,
                    tenant_id=ctx.org_id,
                    customer_id=invoice.customer_id,
                    total_confirmed=total_confirmed,
                )
                log.info(
                    "billing.payment.invoice_fully_paid",
                    invoice_id=str(invoice.id),
                    total_confirmed=str(total_confirmed),
                    tenant_id=str(ctx.org_id),
                )
                log.debug(
                    "billing.payment.event",
                    event_type=fully_paid_event.__class__.__name__,
                )

        await self._bust_full_payment_caches(ctx.org_id, updated.workspace_id, record_id)

        event = PaymentConfirmed(
            payment_id=record_id,
            invoice_id=updated.invoice_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
            amount=updated.amount,
        )
        log.info(
            "billing.payment.confirmed",
            payment_id=str(record_id),
            invoice_id=str(updated.invoice_id),
            tenant_id=str(ctx.org_id),
        )
        log.debug("billing.payment.event", event_type=event.__class__.__name__)
        return InvoicePaymentOut.model_validate(updated)

    async def cancel_payment(self, record_id: uuid.UUID) -> InvoicePaymentOut:
        ctx = get_tenant_context()
        record = await self._payment_repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Payment {record_id} not found")
        if record.status not in _CANCELLABLE_PAYMENT_FROM:
            raise ValidationError(
                f"Payment in status '{record.status}' cannot be cancelled"
            )

        await self._payment_repo.update_fields(
            record_id, status="cancelled", updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        updated = await self._payment_repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_full_payment_caches(ctx.org_id, updated.workspace_id, record_id)

        event = PaymentCancelled(
            payment_id=record_id,
            invoice_id=updated.invoice_id,
            tenant_id=ctx.org_id,
        )
        log.info(
            "billing.payment.cancelled",
            payment_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        log.debug("billing.payment.event", event_type=event.__class__.__name__)
        return InvoicePaymentOut.model_validate(updated)

    async def get_payment(self, record_id: uuid.UUID) -> InvoicePaymentOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _payment_detail_key(ctx.org_id, record_id)
        try:
            cached = await redis.get(key)
            if cached:
                return InvoicePaymentOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._payment_repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Payment {record_id} not found")

        out = InvoicePaymentOut.model_validate(record)
        try:
            await redis.set(key, out.model_dump_json(), ex=_PAYMENT_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def list_payments(self, filters: InvoicePaymentFilters) -> InvoicePaymentListOut:
        ctx = get_tenant_context()
        redis = get_redis()

        _is_default = (
            filters.invoice_id is None
            and filters.customer_id is None
            and filters.status is None
            and filters.payment_method is None
            and filters.payment_date_from is None
            and filters.payment_date_to is None
            and filters.search is None
            and filters.cursor is None
            and filters.limit == 50
        )
        if _is_default:
            key = _payment_list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return InvoicePaymentListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._payment_repo.count(
            filters.workspace_id,
            invoice_id=filters.invoice_id,
            customer_id=filters.customer_id,
            status=filters.status,
            payment_method=filters.payment_method,
            payment_date_from=filters.payment_date_from,
            payment_date_to=filters.payment_date_to,
            search=filters.search,
        )
        rows = await self._payment_repo.list_page(
            filters.workspace_id,
            invoice_id=filters.invoice_id,
            customer_id=filters.customer_id,
            status=filters.status,
            payment_method=filters.payment_method,
            payment_date_from=filters.payment_date_from,
            payment_date_to=filters.payment_date_to,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )
        has_more = len(rows) > filters.limit
        page = rows[: filters.limit]
        next_cursor = (
            _encode_payment_cursor(page[-1].created_at, page[-1].id) if has_more else None
        )

        out = InvoicePaymentListOut(
            items=[InvoicePaymentOut.model_validate(r) for r in page],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )
        if _is_default:
            try:
                await redis.set(
                    _payment_list_key(ctx.org_id, filters.workspace_id),
                    out.model_dump_json(),
                    ex=_PAYMENT_LIST_TTL,
                )
            except Exception:
                pass
        return out

    async def list_invoice_payments(self, invoice_id: uuid.UUID) -> list[InvoicePaymentOut]:
        rows = await self._payment_repo.list_by_invoice(invoice_id)
        return [InvoicePaymentOut.model_validate(r) for r in rows]

    async def get_revenue_summary(self, workspace_id: uuid.UUID) -> RevenueSummaryOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _payment_summary_key(ctx.org_id, workspace_id)
        try:
            cached = await redis.get(key)
            if cached:
                return RevenueSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        summary = await self._payment_repo.fetch_revenue_summary(workspace_id)
        try:
            await redis.set(key, summary.model_dump_json(), ex=_PAYMENT_SUMMARY_TTL)
        except Exception:
            pass
        return summary

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _bust_list_and_summary(self, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
        redis = get_redis()
        for key in [_payment_list_key(org_id, ws_id), _payment_summary_key(org_id, ws_id)]:
            try:
                await redis.delete(key)
            except Exception:
                pass

    async def _bust_detail_and_list(
        self, org_id: uuid.UUID, ws_id: uuid.UUID, record_id: uuid.UUID
    ) -> None:
        redis = get_redis()
        for key in [
            _payment_detail_key(org_id, record_id),
            _payment_list_key(org_id, ws_id),
        ]:
            try:
                await redis.delete(key)
            except Exception:
                pass

    async def _bust_full_payment_caches(
        self, org_id: uuid.UUID, ws_id: uuid.UUID, record_id: uuid.UUID
    ) -> None:
        redis = get_redis()
        for key in [
            _payment_detail_key(org_id, record_id),
            _payment_list_key(org_id, ws_id),
            _payment_summary_key(org_id, ws_id),
        ]:
            try:
                await redis.delete(key)
            except Exception:
                pass

    async def _bust_invoice_caches(
        self, org_id: uuid.UUID, ws_id: uuid.UUID, invoice_id: uuid.UUID
    ) -> None:
        redis = get_redis()
        for key in [
            _invoice_detail_key(org_id, invoice_id),
            _invoice_list_key(org_id, ws_id),
            _invoice_kpis_key(org_id, ws_id),
        ]:
            try:
                await redis.delete(key)
            except Exception:
                pass
