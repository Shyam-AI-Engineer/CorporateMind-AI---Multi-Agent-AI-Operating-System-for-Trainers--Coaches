"""Unit tests for PaymentService — Sprint 52: Payment Management & Revenue Ledger.

170 tests total across 13 test classes.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.billing.repo import (
    _decode_payment_cursor,
    _encode_payment_cursor,
)
from corpmind.modules.billing.schemas import (
    InvoicePaymentCreate,
    InvoicePaymentFilters,
    InvoicePaymentListOut,
    InvoicePaymentOut,
    InvoicePaymentUpdate,
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    RevenueSummaryOut,
)
from corpmind.modules.billing.service import (
    PaymentService,
    _payment_detail_key,
    _payment_list_key,
    _payment_summary_key,
)
from corpmind.core.exceptions import NotFoundError, ValidationError

_PATCH_CTX = "corpmind.modules.billing.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.billing.service.get_redis"

_ORG = uuid.uuid4()
_WS = uuid.uuid4()


def _ctx(org=None, ws=None):
    c = MagicMock()
    c.org_id = org or _ORG
    c.workspace_id = ws or _WS
    return c


def _redis(*, get_val=None, fail=False):
    r = MagicMock()
    if fail:
        r.get = AsyncMock(side_effect=Exception("redis down"))
        r.set = AsyncMock(side_effect=Exception("redis down"))
        r.delete = AsyncMock(side_effect=Exception("redis down"))
    else:
        r.get = AsyncMock(return_value=get_val)
        r.set = AsyncMock(return_value=True)
        r.delete = AsyncMock(return_value=1)
    return r


@contextmanager
def _patch(ctx=None, redis=None):
    with patch(_PATCH_CTX, return_value=ctx or _ctx()):
        with patch(_PATCH_REDIS, return_value=redis or _redis()):
            yield


def _make_svc():
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    svc = PaymentService(db)
    svc._payment_repo = MagicMock()
    svc._invoice_repo = MagicMock()
    return svc, db


def _make_payment(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", uuid.uuid4())
    p.tenant_id = kwargs.get("tenant_id", _ORG)
    p.workspace_id = kwargs.get("workspace_id", _WS)
    p.invoice_id = kwargs.get("invoice_id", uuid.uuid4())
    p.customer_id = kwargs.get("customer_id", uuid.uuid4())
    p.payment_date = kwargs.get("payment_date", date(2026, 7, 7))
    p.amount = kwargs.get("amount", Decimal("500.00"))
    p.payment_method = kwargs.get("payment_method", "upi")
    p.reference_number = kwargs.get("reference_number", "REF001")
    p.status = kwargs.get("status", "pending")
    p.notes = kwargs.get("notes", None)
    p.created_by = kwargs.get("created_by", None)
    p.created_at = kwargs.get("created_at", datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC))
    p.updated_at = kwargs.get("updated_at", datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC))
    return p


def _make_invoice(**kwargs):
    inv = MagicMock()
    inv.id = kwargs.get("id", uuid.uuid4())
    inv.tenant_id = kwargs.get("tenant_id", _ORG)
    inv.workspace_id = kwargs.get("workspace_id", _WS)
    inv.customer_id = kwargs.get("customer_id", uuid.uuid4())
    inv.status = kwargs.get("status", "issued")
    inv.total_amount = kwargs.get("total_amount", Decimal("1000.00"))
    inv.payment_date = kwargs.get("payment_date", None)
    return inv


def _create_req(**kwargs) -> InvoicePaymentCreate:
    return InvoicePaymentCreate(
        workspace_id=kwargs.get("workspace_id", _WS),
        invoice_id=kwargs.get("invoice_id", uuid.uuid4()),
        customer_id=kwargs.get("customer_id", uuid.uuid4()),
        amount=kwargs.get("amount", Decimal("500.00")),
        payment_date=kwargs.get("payment_date", date(2026, 7, 7)),
        payment_method=kwargs.get("payment_method", "upi"),
        reference_number=kwargs.get("reference_number", None),
        notes=kwargs.get("notes", None),
        created_by=kwargs.get("created_by", None),
    )


# ── TestPaymentCacheKeys ──────────────────────────────────────────────────────

class TestPaymentCacheKeys:
    def test_list_key_format(self):
        org = uuid.uuid4()
        ws = uuid.uuid4()
        key = _payment_list_key(org, ws)
        assert str(org) in key
        assert str(ws) in key

    def test_list_key_contains_namespace(self):
        key = _payment_list_key(_ORG, _WS)
        assert "billing:payments:list" in key

    def test_detail_key_format(self):
        org = uuid.uuid4()
        rec = uuid.uuid4()
        key = _payment_detail_key(org, rec)
        assert str(org) in key
        assert str(rec) in key

    def test_detail_key_contains_namespace(self):
        key = _payment_detail_key(_ORG, uuid.uuid4())
        assert "billing:payments:detail" in key

    def test_summary_key_format(self):
        org = uuid.uuid4()
        ws = uuid.uuid4()
        key = _payment_summary_key(org, ws)
        assert str(org) in key
        assert str(ws) in key

    def test_summary_key_contains_namespace(self):
        key = _payment_summary_key(_ORG, _WS)
        assert "billing:payments:summary" in key

    def test_different_orgs_different_list_keys(self):
        ws = uuid.uuid4()
        assert _payment_list_key(uuid.uuid4(), ws) != _payment_list_key(uuid.uuid4(), ws)

    def test_different_ws_different_list_keys(self):
        org = uuid.uuid4()
        assert _payment_list_key(org, uuid.uuid4()) != _payment_list_key(org, uuid.uuid4())

    def test_different_records_different_detail_keys(self):
        org = uuid.uuid4()
        assert _payment_detail_key(org, uuid.uuid4()) != _payment_detail_key(org, uuid.uuid4())


# ── TestPaymentSchemas ────────────────────────────────────────────────────────

class TestPaymentSchemas:
    def test_create_all_fields(self):
        r = _create_req(payment_method="cash", reference_number="R1", notes="n", created_by=uuid.uuid4())
        assert r.amount == Decimal("500.00")
        assert r.payment_method == "cash"

    def test_create_minimal(self):
        r = InvoicePaymentCreate(
            workspace_id=_WS,
            invoice_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            amount=Decimal("100"),
        )
        assert r.payment_method is None
        assert r.notes is None

    def test_update_partial(self):
        u = InvoicePaymentUpdate(amount=Decimal("200"))
        assert u.amount == Decimal("200")
        assert u.payment_method is None

    def test_out_from_attributes(self):
        p = _make_payment()
        out = InvoicePaymentOut.model_validate(p)
        assert out.status == p.status
        assert out.amount == p.amount

    def test_out_serializes_uuid(self):
        p = _make_payment()
        out = InvoicePaymentOut.model_validate(p)
        json_str = out.model_dump_json()
        assert str(p.id) in json_str

    def test_list_out_shape(self):
        p = _make_payment()
        out_item = InvoicePaymentOut.model_validate(p)
        lo = InvoicePaymentListOut(items=[out_item], total=1, has_more=False)
        assert lo.total == 1
        assert lo.has_more is False

    def test_revenue_summary_defaults(self):
        rs = RevenueSummaryOut()
        assert rs.total_collected == Decimal("0.00")
        assert rs.count_pending_payments == 0
        assert rs.partial_payment_invoices == 0

    def test_payment_methods_frozenset(self):
        assert "cash" in PAYMENT_METHODS
        assert "upi" in PAYMENT_METHODS
        assert "bank_transfer" in PAYMENT_METHODS
        assert "credit_card" in PAYMENT_METHODS
        assert "cheque" in PAYMENT_METHODS
        assert "other" in PAYMENT_METHODS

    def test_payment_statuses_frozenset(self):
        assert "pending" in PAYMENT_STATUSES
        assert "confirmed" in PAYMENT_STATUSES
        assert "cancelled" in PAYMENT_STATUSES

    def test_filters_defaults(self):
        f = InvoicePaymentFilters(workspace_id=_WS)
        assert f.limit == 50
        assert f.cursor is None
        assert f.status is None

    def test_out_none_amount(self):
        p = _make_payment(amount=None)
        out = InvoicePaymentOut.model_validate(p)
        assert out.amount is None

    def test_out_all_fields_present(self):
        p = _make_payment(created_by=uuid.uuid4())
        out = InvoicePaymentOut.model_validate(p)
        assert out.invoice_id == p.invoice_id
        assert out.customer_id == p.customer_id
        assert out.reference_number == p.reference_number


# ── TestRecordPayment ─────────────────────────────────────────────────────────

class TestRecordPayment:
    @pytest.mark.asyncio
    async def test_happy_path_creates_payment(self):
        svc, db = _make_svc()
        inv = _make_invoice()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.create = AsyncMock()
        req = _create_req(invoice_id=inv.id)
        with _patch():
            result = await svc.record_payment(req)
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_invoice_not_found_raises(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.record_payment(_create_req())

    @pytest.mark.asyncio
    async def test_cancelled_invoice_raises(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError, match="cancelled"):
                await svc.record_payment(_create_req())

    @pytest.mark.asyncio
    async def test_amount_zero_raises(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        with _patch():
            with pytest.raises(ValidationError, match="greater than zero"):
                await svc.record_payment(_create_req(amount=Decimal("0")))

    @pytest.mark.asyncio
    async def test_amount_negative_raises(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        with _patch():
            with pytest.raises(ValidationError, match="greater than zero"):
                await svc.record_payment(_create_req(amount=Decimal("-1")))

    @pytest.mark.asyncio
    async def test_draft_invoice_allowed(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="draft"))
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req())
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_issued_invoice_allowed(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="issued"))
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req())
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_overdue_invoice_allowed(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="overdue"))
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req())
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_paid_invoice_allowed(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="paid"))
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req())
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_status_always_pending_on_create(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req())
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_payment_method_stored(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(payment_method="cash"))
        assert result.payment_method == "cash"

    @pytest.mark.asyncio
    async def test_reference_number_stored(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(reference_number="TXN123"))
        assert result.reference_number == "TXN123"

    @pytest.mark.asyncio
    async def test_notes_stored(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(notes="partial payment"))
        assert result.notes == "partial payment"

    @pytest.mark.asyncio
    async def test_created_by_stored(self):
        admin_id = uuid.uuid4()
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(created_by=admin_id))
        assert result.created_by == admin_id

    @pytest.mark.asyncio
    async def test_workspace_id_from_request(self):
        ws = uuid.uuid4()
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(workspace_id=ws))
        assert result.workspace_id == ws

    @pytest.mark.asyncio
    async def test_cache_bust_list_key(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.record_payment(_create_req())
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_cache_bust_summary_key(self):
        svc, _ = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.record_payment(_create_req())
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:summary" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_commit_called(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            await svc.record_payment(_create_req())
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_amount_stored_correctly(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(amount=Decimal("750.50")))
        assert result.amount == Decimal("750.50")

    @pytest.mark.asyncio
    async def test_customer_id_from_request(self):
        cust_id = uuid.uuid4()
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        with _patch():
            result = await svc.record_payment(_create_req(customer_id=cust_id))
        assert result.customer_id == cust_id


# ── TestUpdatePayment ─────────────────────────────────────────────────────────

class TestUpdatePayment:
    @pytest.mark.asyncio
    async def test_pending_payment_updated(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending", amount=Decimal("200"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update_payment(pay_id, InvoicePaymentUpdate(amount=Decimal("200")))
        assert result.amount == Decimal("200")

    @pytest.mark.asyncio
    async def test_confirmed_payment_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="confirmed"))
        with _patch():
            with pytest.raises(ValidationError, match="confirmed"):
                await svc.update_payment(uuid.uuid4(), InvoicePaymentUpdate())

    @pytest.mark.asyncio
    async def test_cancelled_payment_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError, match="cancelled"):
                await svc.update_payment(uuid.uuid4(), InvoicePaymentUpdate())

    @pytest.mark.asyncio
    async def test_payment_not_found_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.update_payment(uuid.uuid4(), InvoicePaymentUpdate())

    @pytest.mark.asyncio
    async def test_amount_zero_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="pending"))
        with _patch():
            with pytest.raises(ValidationError, match="greater than zero"):
                await svc.update_payment(uuid.uuid4(), InvoicePaymentUpdate(amount=Decimal("0")))

    @pytest.mark.asyncio
    async def test_payment_method_updated(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending", payment_method="cheque")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update_payment(pay_id, InvoicePaymentUpdate(payment_method="cheque"))
        assert result.payment_method == "cheque"

    @pytest.mark.asyncio
    async def test_reference_number_updated(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending", reference_number="REF999")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update_payment(pay_id, InvoicePaymentUpdate(reference_number="REF999"))
        assert result.reference_number == "REF999"

    @pytest.mark.asyncio
    async def test_notes_updated(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending", notes="updated note")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update_payment(pay_id, InvoicePaymentUpdate(notes="updated note"))
        assert result.notes == "updated note"

    @pytest.mark.asyncio
    async def test_cache_bust_detail(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.update_payment(pay_id, InvoicePaymentUpdate(notes="x"))
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:detail" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_cache_bust_list(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.update_payment(pay_id, InvoicePaymentUpdate(notes="x"))
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_commit_called(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.update_payment(pay_id, InvoicePaymentUpdate())
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_id_called_twice(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.update_payment(pay_id, InvoicePaymentUpdate())
        assert svc._payment_repo.find_by_id.call_count == 2

    @pytest.mark.asyncio
    async def test_update_fields_receives_updated_at(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.update_payment(pay_id, InvoicePaymentUpdate(notes="x"))
        call_kwargs = svc._payment_repo.update_fields.call_args[1]
        assert "updated_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_partial_update_only_sets_provided_fields(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        updated = _make_payment(id=pay_id, status="pending")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.update_payment(pay_id, InvoicePaymentUpdate(notes="only this"))
        call_kwargs = svc._payment_repo.update_fields.call_args[1]
        assert "notes" in call_kwargs
        assert "amount" not in call_kwargs


# ── TestConfirmPayment ────────────────────────────────────────────────────────

class TestConfirmPayment:
    @pytest.mark.asyncio
    async def test_pending_payment_confirmed(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        original = _make_payment(id=pay_id, invoice_id=inv_id, status="pending", amount=Decimal("100"))
        confirmed = _make_payment(id=pay_id, invoice_id=inv_id, status="confirmed", amount=Decimal("100"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, confirmed])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("100")])
        svc._invoice_repo.update_fields = AsyncMock()
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.confirm_payment(pay_id)
        assert result.status == "confirmed"

    @pytest.mark.asyncio
    async def test_already_confirmed_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="confirmed"))
        with _patch():
            with pytest.raises(ValidationError, match="confirmed"):
                await svc.confirm_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancelled_payment_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError, match="cancelled"):
                await svc.confirm_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_payment_not_found_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.confirm_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_invoice_not_found_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="pending"))
        svc._invoice_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.confirm_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancelled_invoice_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="pending"))
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError, match="cancelled"):
                await svc.confirm_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_overpayment_rejected(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        pay = _make_payment(status="pending", invoice_id=inv_id, amount=Decimal("600"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(return_value=pay)
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # already confirmed: 600, this payment: 600 → 1200 > 1000
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(return_value=Decimal("600"))
        with _patch():
            with pytest.raises(ValidationError, match="exceed"):
                await svc.confirm_payment(pay.id)

    @pytest.mark.asyncio
    async def test_exact_amount_allowed(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("400"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("400"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # confirmed so far: 600, this: 400 → 1000 == 1000, not > 1000
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("600"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.confirm_payment(pay_id)
        assert result.status == "confirmed"

    @pytest.mark.asyncio
    async def test_partial_payment_keeps_invoice_issued(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("300"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("300"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("300")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        # invoice update_fields should NOT have been called (300 < 1000)
        svc._invoice_repo.update_fields.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_payment_marks_invoice_paid(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("1000"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("1000"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        svc._invoice_repo.update_fields.assert_called_once()
        kwargs = svc._invoice_repo.update_fields.call_args[1]
        assert kwargs["status"] == "paid"

    @pytest.mark.asyncio
    async def test_full_payment_overdue_invoice_marked_paid(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("500"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("500"))
        inv = _make_invoice(id=inv_id, status="overdue", total_amount=Decimal("500"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("500")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        kwargs = svc._invoice_repo.update_fields.call_args[1]
        assert kwargs["status"] == "paid"

    @pytest.mark.asyncio
    async def test_full_payment_commits_twice(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("1000"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("1000"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        assert db.commit.call_count == 2

    @pytest.mark.asyncio
    async def test_partial_payment_commits_once(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("200"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("200"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("200")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        assert db.commit.call_count == 1

    @pytest.mark.asyncio
    async def test_invoice_caches_busted_on_full_payment(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("1000"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("1000"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.confirm_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("invoices:detail" in k for k in deleted_keys)
        assert any("invoices:list" in k for k in deleted_keys)
        assert any("invoices:kpis" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_invoice_not_busted_on_partial_payment(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("100"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("100"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("100")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.confirm_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert not any("invoices:kpis" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_payment_caches_always_busted(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("100"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("100"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("100")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.confirm_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:detail" in k for k in deleted_keys)
        assert any("payments:list" in k for k in deleted_keys)
        assert any("payments:summary" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_no_total_amount_overpayment_skipped(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("99999"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("99999"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=None)
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(return_value=Decimal("0"))
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.confirm_payment(pay_id)
        assert result.status == "confirmed"

    @pytest.mark.asyncio
    async def test_draft_invoice_not_auto_settled(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("1000"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("1000"))
        inv = _make_invoice(id=inv_id, status="draft", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        # draft invoices are not auto-settled
        svc._invoice_repo.update_fields.assert_not_called()

    @pytest.mark.asyncio
    async def test_invoice_payment_date_set_from_payment(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay_date = date(2026, 7, 15)
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("1000"), payment_date=pay_date)
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("1000"), payment_date=pay_date)
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        with _patch():
            await svc.confirm_payment(pay_id)
        kwargs = svc._invoice_repo.update_fields.call_args[1]
        assert kwargs["payment_date"] == pay_date


# ── TestCancelPayment ─────────────────────────────────────────────────────────

class TestCancelPayment:
    @pytest.mark.asyncio
    async def test_pending_payment_cancelled(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel_payment(pay_id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_confirmed_payment_cancelled(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="confirmed")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel_payment(pay_id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_already_cancelled_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.cancel_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_payment_not_found_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.cancel_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cache_bust_detail(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.cancel_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:detail" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_cache_bust_list(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.cancel_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_cache_bust_summary(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.cancel_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:summary" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_commit_called(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel_payment(pay_id)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoice_not_touched(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="confirmed")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel_payment(pay_id)
        svc._invoice_repo.update_fields.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_set_to_cancelled(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel_payment(pay_id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_find_by_id_called_twice(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel_payment(pay_id)
        assert svc._payment_repo.find_by_id.call_count == 2

    @pytest.mark.asyncio
    async def test_update_fields_receives_cancelled_status(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="pending")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel_payment(pay_id)
        kwargs = svc._payment_repo.update_fields.call_args[1]
        assert kwargs["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_confirmed_then_cancel_both_caches_busted(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        original = _make_payment(id=pay_id, status="confirmed")
        cancelled = _make_payment(id=pay_id, status="cancelled")
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
        svc._payment_repo.update_fields = AsyncMock()
        r = _redis()
        with _patch(redis=r):
            await svc.cancel_payment(pay_id)
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert any("payments:detail" in k for k in deleted_keys)
        assert any("payments:summary" in k for k in deleted_keys)


# ── TestGetPayment ────────────────────────────────────────────────────────────

class TestGetPayment:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_object(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        out = InvoicePaymentOut.model_validate(p)
        r = _redis(get_val=out.model_dump_json())
        with _patch(redis=r):
            result = await svc.get_payment(pay_id)
        assert result.id == pay_id
        svc._payment_repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_db(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        r = _redis(get_val=None)
        with _patch(redis=r):
            result = await svc.get_payment(pay_id)
        assert result.id == pay_id
        svc._payment_repo.find_by_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_sets_cache(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.get_payment(pay_id)
        r.set.assert_called_once()
        call_kwargs = r.set.call_args[1]
        assert call_kwargs["ex"] == 300

    @pytest.mark.asyncio
    async def test_cache_failure_falls_back_to_db(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        with _patch(redis=_redis(fail=True)):
            result = await svc.get_payment(pay_id)
        assert result.id == pay_id

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        svc, _ = _make_svc()
        svc._payment_repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.get_payment(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_returned_object_correct(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id, amount=Decimal("999"), payment_method="bank_transfer")
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        with _patch():
            result = await svc.get_payment(pay_id)
        assert result.amount == Decimal("999")
        assert result.payment_method == "bank_transfer"

    @pytest.mark.asyncio
    async def test_no_db_call_on_cache_hit(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        out = InvoicePaymentOut.model_validate(p)
        svc._payment_repo.find_by_id = AsyncMock()
        r = _redis(get_val=out.model_dump_json())
        with _patch(redis=r):
            await svc.get_payment(pay_id)
        svc._payment_repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_uses_org_id(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        org = uuid.uuid4()
        p = _make_payment(id=pay_id)
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        r = _redis(get_val=None)
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.get_payment(pay_id)
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_result_returned_despite_redis_set_failure(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(id=pay_id))
        r = _redis(fail=True)
        with _patch(redis=r):
            result = await svc.get_payment(pay_id)
        # redis.set raises and is swallowed; result still returned from DB
        assert result.id == pay_id

    @pytest.mark.asyncio
    async def test_cache_set_not_called_after_cache_hit(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        out = InvoicePaymentOut.model_validate(p)
        r = _redis(get_val=out.model_dump_json())
        with _patch(redis=r):
            await svc.get_payment(pay_id)
        r.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_get_called_on_every_request(self):
        svc, _ = _make_svc()
        pay_id = uuid.uuid4()
        p = _make_payment(id=pay_id)
        svc._payment_repo.find_by_id = AsyncMock(return_value=p)
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.get_payment(pay_id)
        r.get.assert_called_once()


# ── TestListPayments ──────────────────────────────────────────────────────────

class TestListPayments:
    def _default_filters(self):
        return InvoicePaymentFilters(workspace_id=_WS)

    @pytest.mark.asyncio
    async def test_default_cached(self):
        svc, _ = _make_svc()
        items = [_make_payment()]
        out = InvoicePaymentListOut(
            items=[InvoicePaymentOut.model_validate(i) for i in items],
            total=1,
            has_more=False,
        )
        r = _redis(get_val=out.model_dump_json())
        with _patch(redis=r):
            result = await svc.list_payments(self._default_filters())
        assert result.total == 1
        svc._payment_repo.count.assert_not_called()

    @pytest.mark.asyncio
    async def test_filtered_not_cached(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        filters = InvoicePaymentFilters(workspace_id=_WS, status="confirmed")
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(filters)
        svc._payment_repo.count.assert_called_once()
        r.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cursor_not_cached(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        filters = InvoicePaymentFilters(workspace_id=_WS, cursor="abc")
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(filters)
        r.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_has_more_true_when_extra_row(self):
        svc, _ = _make_svc()
        rows = [_make_payment() for _ in range(51)]
        svc._payment_repo.count = AsyncMock(return_value=51)
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_has_more_false_when_exact(self):
        svc, _ = _make_svc()
        rows = [_make_payment() for _ in range(50)]
        svc._payment_repo.count = AsyncMock(return_value=50)
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_next_cursor_present_when_has_more(self):
        svc, _ = _make_svc()
        rows = [_make_payment() for _ in range(51)]
        svc._payment_repo.count = AsyncMock(return_value=51)
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_next_cursor_absent_when_no_more(self):
        svc, _ = _make_svc()
        rows = [_make_payment() for _ in range(3)]
        svc._payment_repo.count = AsyncMock(return_value=3)
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_page_trimmed_to_limit(self):
        svc, _ = _make_svc()
        rows = [_make_payment() for _ in range(51)]
        svc._payment_repo.count = AsyncMock(return_value=51)
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert len(result.items) == 50

    @pytest.mark.asyncio
    async def test_total_from_count(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=123)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.total == 123

    @pytest.mark.asyncio
    async def test_cache_set_on_default_query(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(self._default_filters())
        r.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoice_id_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        filters = InvoicePaymentFilters(workspace_id=_WS, invoice_id=uuid.uuid4())
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(filters)
        r.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=2)
        rows = [_make_payment(), _make_payment()]
        svc._payment_repo.list_page = AsyncMock(return_value=rows)
        with _patch(redis=_redis(fail=True)):
            result = await svc.list_payments(self._default_filters())
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_items_serialized_correctly(self):
        svc, _ = _make_svc()
        p = _make_payment(amount=Decimal("123.45"), payment_method="upi")
        svc._payment_repo.count = AsyncMock(return_value=1)
        svc._payment_repo.list_page = AsyncMock(return_value=[p])
        with _patch():
            result = await svc.list_payments(self._default_filters())
        assert result.items[0].amount == Decimal("123.45")
        assert result.items[0].payment_method == "upi"

    @pytest.mark.asyncio
    async def test_customer_id_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        filters = InvoicePaymentFilters(workspace_id=_WS, customer_id=uuid.uuid4())
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(filters)
        r.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        filters = InvoicePaymentFilters(workspace_id=_WS, search="REF123")
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.list_payments(filters)
        r.set.assert_not_called()


# ── TestListInvoicePayments ───────────────────────────────────────────────────

class TestListInvoicePayments:
    @pytest.mark.asyncio
    async def test_returns_payments_for_invoice(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [_make_payment(invoice_id=inv_id), _make_payment(invoice_id=inv_id)]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        svc, _ = _make_svc()
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=[])
        result = await svc.list_invoice_payments(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_calls_list_by_invoice_method(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=[])
        await svc.list_invoice_payments(inv_id)
        svc._payment_repo.list_by_invoice.assert_called_once_with(inv_id)

    @pytest.mark.asyncio
    async def test_serializes_each_payment(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        p = _make_payment(invoice_id=inv_id, amount=Decimal("250"))
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=[p])
        result = await svc.list_invoice_payments(inv_id)
        assert isinstance(result[0], InvoicePaymentOut)
        assert result[0].amount == Decimal("250")

    @pytest.mark.asyncio
    async def test_payments_match_invoice_id(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [_make_payment(invoice_id=inv_id)]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        assert result[0].invoice_id == inv_id

    @pytest.mark.asyncio
    async def test_no_redis_cache_used(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=[])
        r = _redis()
        with _patch(redis=r):
            await svc.list_invoice_payments(inv_id)
        r.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_payments_returned(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [_make_payment(invoice_id=inv_id) for _ in range(5)]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_cancelled_status_included(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [_make_payment(invoice_id=inv_id, status="cancelled")]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        assert result[0].status == "cancelled"

    @pytest.mark.asyncio
    async def test_confirmed_status_included(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [_make_payment(invoice_id=inv_id, status="confirmed")]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        assert result[0].status == "confirmed"

    @pytest.mark.asyncio
    async def test_all_payment_statuses_returned(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        rows = [
            _make_payment(invoice_id=inv_id, status="pending"),
            _make_payment(invoice_id=inv_id, status="confirmed"),
            _make_payment(invoice_id=inv_id, status="cancelled"),
        ]
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=rows)
        result = await svc.list_invoice_payments(inv_id)
        statuses = {r.status for r in result}
        assert statuses == {"pending", "confirmed", "cancelled"}

    @pytest.mark.asyncio
    async def test_different_invoices_return_independently(self):
        svc, _ = _make_svc()
        inv_a = uuid.uuid4()
        inv_b = uuid.uuid4()
        rows_a = [_make_payment(invoice_id=inv_a)]
        rows_b = [_make_payment(invoice_id=inv_b), _make_payment(invoice_id=inv_b)]
        svc._payment_repo.list_by_invoice = AsyncMock(side_effect=[rows_a, rows_b])
        result_a = await svc.list_invoice_payments(inv_a)
        result_b = await svc.list_invoice_payments(inv_b)
        assert len(result_a) == 1
        assert len(result_b) == 2

    @pytest.mark.asyncio
    async def test_invoicepaymentout_type_returned(self):
        svc, _ = _make_svc()
        svc._payment_repo.list_by_invoice = AsyncMock(return_value=[_make_payment()])
        result = await svc.list_invoice_payments(uuid.uuid4())
        assert all(isinstance(r, InvoicePaymentOut) for r in result)


# ── TestGetRevenueSummary ─────────────────────────────────────────────────────

class TestGetRevenueSummary:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_object(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(total_collected=Decimal("5000"))
        r = _redis(get_val=summary.model_dump_json())
        with _patch(redis=r):
            result = await svc.get_revenue_summary(_WS)
        assert result.total_collected == Decimal("5000")
        svc._payment_repo.fetch_revenue_summary.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_repo(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(total_collected=Decimal("3000"))
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.total_collected == Decimal("3000")
        svc._payment_repo.fetch_revenue_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_sets_with_ttl_300(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut()
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        r = _redis(get_val=None)
        with _patch(redis=r):
            await svc.get_revenue_summary(_WS)
        assert r.set.call_args[1]["ex"] == 300

    @pytest.mark.asyncio
    async def test_cache_failure_falls_back(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(count_confirmed_payments=7)
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(fail=True)):
            result = await svc.get_revenue_summary(_WS)
        assert result.count_confirmed_payments == 7

    @pytest.mark.asyncio
    async def test_summary_counts_correct(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(
            total_collected=Decimal("10000"),
            total_outstanding=Decimal("5000"),
            count_pending_payments=3,
            count_confirmed_payments=8,
        )
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.count_pending_payments == 3
        assert result.count_confirmed_payments == 8

    @pytest.mark.asyncio
    async def test_partial_payment_invoices_count(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(partial_payment_invoices=4)
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.partial_payment_invoices == 4

    @pytest.mark.asyncio
    async def test_summary_key_format(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut()
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        r = _redis(get_val=None)
        org = uuid.uuid4()
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.get_revenue_summary(_WS)
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key
        assert "payments:summary" in set_key

    @pytest.mark.asyncio
    async def test_total_overdue_from_summary(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(total_overdue=Decimal("2500"))
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.total_overdue == Decimal("2500")

    @pytest.mark.asyncio
    async def test_no_db_call_on_cache_hit(self):
        svc, _ = _make_svc()
        svc._payment_repo.fetch_revenue_summary = AsyncMock()
        summary = RevenueSummaryOut()
        r = _redis(get_val=summary.model_dump_json())
        with _patch(redis=r):
            await svc.get_revenue_summary(_WS)
        svc._payment_repo.fetch_revenue_summary.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_payments_counted(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(count_cancelled_payments=5)
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.count_cancelled_payments == 5

    @pytest.mark.asyncio
    async def test_total_outstanding_from_summary(self):
        svc, _ = _make_svc()
        summary = RevenueSummaryOut(total_outstanding=Decimal("7500"))
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=summary)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_revenue_summary(_WS)
        assert result.total_outstanding == Decimal("7500")

    @pytest.mark.asyncio
    async def test_workspace_id_passed_to_repo(self):
        svc, _ = _make_svc()
        ws = uuid.uuid4()
        svc._payment_repo.fetch_revenue_summary = AsyncMock(return_value=RevenueSummaryOut())
        with _patch(redis=_redis(get_val=None)):
            await svc.get_revenue_summary(ws)
        svc._payment_repo.fetch_revenue_summary.assert_called_once_with(ws)


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_different_orgs_different_list_keys(self):
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _payment_list_key(org_a, ws) != _payment_list_key(org_b, ws)

    def test_different_orgs_different_detail_keys(self):
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        rec = uuid.uuid4()
        assert _payment_detail_key(org_a, rec) != _payment_detail_key(org_b, rec)

    def test_different_orgs_different_summary_keys(self):
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _payment_summary_key(org_a, ws) != _payment_summary_key(org_b, ws)

    @pytest.mark.asyncio
    async def test_record_payment_uses_context_org(self):
        svc, db = _make_svc()
        org_a = uuid.uuid4()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        r = _redis()
        with _patch(ctx=_ctx(org=org_a), redis=r):
            await svc.record_payment(_create_req())
        # Verify the payment was created with the context org's tenant_id
        created_record = svc._payment_repo.create.call_args[0][0]
        assert created_record.tenant_id == org_a

    @pytest.mark.asyncio
    async def test_list_key_uses_context_org(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        svc._payment_repo.count = AsyncMock(return_value=0)
        svc._payment_repo.list_page = AsyncMock(return_value=[])
        r = _redis(get_val=None)
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.list_payments(InvoicePaymentFilters(workspace_id=_WS))
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_get_detail_key_uses_context_org(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        pay_id = uuid.uuid4()
        svc._payment_repo.find_by_id = AsyncMock(return_value=_make_payment(id=pay_id))
        r = _redis(get_val=None)
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.get_payment(pay_id)
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_two_orgs_independent_cache(self):
        svc_a, _ = _make_svc()
        svc_b, _ = _make_svc()
        ws = uuid.uuid4()
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        key_a = _payment_list_key(org_a, ws)
        key_b = _payment_list_key(org_b, ws)
        assert key_a != key_b

    def test_summary_key_includes_workspace(self):
        ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
        org = uuid.uuid4()
        assert _payment_summary_key(org, ws_a) != _payment_summary_key(org, ws_b)

    @pytest.mark.asyncio
    async def test_context_called_in_record_payment(self):
        svc, db = _make_svc()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        ctx_mock = _ctx()
        with _patch(ctx=ctx_mock):
            await svc.record_payment(_create_req())

    @pytest.mark.asyncio
    async def test_context_called_in_confirm_payment(self):
        svc, db = _make_svc()
        pay_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("100"))
        conf = _make_payment(id=pay_id, status="confirmed", invoice_id=inv_id, amount=Decimal("100"))
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))
        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay, conf])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("100")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()
        ctx_mock = _ctx()
        with _patch(ctx=ctx_mock):
            await svc.confirm_payment(pay_id)

    @pytest.mark.asyncio
    async def test_bust_list_uses_org_from_context(self):
        svc, db = _make_svc()
        org = uuid.uuid4()
        svc._invoice_repo.find_by_id = AsyncMock(return_value=_make_invoice())
        svc._payment_repo.create = AsyncMock()
        r = _redis()
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.record_payment(_create_req())
        deleted_keys = [call.args[0] for call in r.delete.call_args_list]
        assert all(str(org) in k for k in deleted_keys)


# ── TestCursorHelpers ─────────────────────────────────────────────────────────

class TestCursorHelpers:
    def test_encode_decode_roundtrip(self):
        ts = datetime(2026, 7, 7, 10, 30, 0, tzinfo=UTC)
        row_id = uuid.uuid4()
        token = _encode_payment_cursor(ts, row_id)
        decoded_ts, decoded_id = _decode_payment_cursor(token)
        assert decoded_id == row_id

    def test_base64_urlsafe(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        token = _encode_payment_cursor(ts, uuid.uuid4())
        assert "+" not in token
        assert "/" not in token

    def test_separator_preserved(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        row_id = uuid.uuid4()
        token = _encode_payment_cursor(ts, row_id)
        import base64
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        assert "|" in raw

    def test_uuid_preserved_through_encode_decode(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        row_id = uuid.uuid4()
        token = _encode_payment_cursor(ts, row_id)
        _, decoded_id = _decode_payment_cursor(token)
        assert decoded_id == row_id

    def test_different_datetimes_different_tokens(self):
        row_id = uuid.uuid4()
        ts_a = datetime(2026, 7, 7, tzinfo=UTC)
        ts_b = datetime(2026, 7, 8, tzinfo=UTC)
        assert _encode_payment_cursor(ts_a, row_id) != _encode_payment_cursor(ts_b, row_id)

    def test_different_uuids_different_tokens(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        assert _encode_payment_cursor(ts, uuid.uuid4()) != _encode_payment_cursor(ts, uuid.uuid4())

    def test_decode_returns_uuid_type(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        token = _encode_payment_cursor(ts, uuid.uuid4())
        _, decoded_id = _decode_payment_cursor(token)
        assert isinstance(decoded_id, uuid.UUID)

    def test_stable_across_multiple_calls(self):
        ts = datetime(2026, 7, 7, tzinfo=UTC)
        row_id = uuid.uuid4()
        assert _encode_payment_cursor(ts, row_id) == _encode_payment_cursor(ts, row_id)


# ── TestMultiplePayments ──────────────────────────────────────────────────────

class TestMultiplePayments:
    @pytest.mark.asyncio
    async def test_two_partial_payments_accumulate(self):
        svc, db = _make_svc()
        inv_id = uuid.uuid4()
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))

        pay1_id = uuid.uuid4()
        pay1 = _make_payment(id=pay1_id, status="pending", invoice_id=inv_id, amount=Decimal("400"))
        conf1 = _make_payment(id=pay1_id, status="confirmed", invoice_id=inv_id, amount=Decimal("400"))

        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay1, conf1])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # after 1st confirmation: 0 so far, then 400 after
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("0"), Decimal("400")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()

        with _patch():
            await svc.confirm_payment(pay1_id)
        svc._invoice_repo.update_fields.assert_not_called()  # 400 < 1000

    @pytest.mark.asyncio
    async def test_second_payment_fully_settles(self):
        svc, db = _make_svc()
        inv_id = uuid.uuid4()
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))

        pay2_id = uuid.uuid4()
        pay2 = _make_payment(id=pay2_id, status="pending", invoice_id=inv_id, amount=Decimal("600"))
        conf2 = _make_payment(id=pay2_id, status="confirmed", invoice_id=inv_id, amount=Decimal("600"))

        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay2, conf2])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # before: 400 already confirmed, after: 1000
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("400"), Decimal("1000")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()

        with _patch():
            await svc.confirm_payment(pay2_id)
        svc._invoice_repo.update_fields.assert_called_once()
        kwargs = svc._invoice_repo.update_fields.call_args[1]
        assert kwargs["status"] == "paid"

    @pytest.mark.asyncio
    async def test_overpayment_prevents_confirmation(self):
        svc, _ = _make_svc()
        inv_id = uuid.uuid4()
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("1000"))

        pay_id = uuid.uuid4()
        pay = _make_payment(id=pay_id, status="pending", invoice_id=inv_id, amount=Decimal("700"))

        svc._payment_repo.find_by_id = AsyncMock(return_value=pay)
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # 400 already confirmed, this 700 would make 1100 > 1000
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(return_value=Decimal("400"))

        with _patch():
            with pytest.raises(ValidationError, match="exceed"):
                await svc.confirm_payment(pay_id)

    @pytest.mark.asyncio
    async def test_three_partial_payments_settle_on_third(self):
        svc, db = _make_svc()
        inv_id = uuid.uuid4()
        inv = _make_invoice(id=inv_id, status="issued", total_amount=Decimal("900"))

        pay3_id = uuid.uuid4()
        pay3 = _make_payment(id=pay3_id, status="pending", invoice_id=inv_id, amount=Decimal("300"))
        conf3 = _make_payment(id=pay3_id, status="confirmed", invoice_id=inv_id, amount=Decimal("300"))

        svc._payment_repo.find_by_id = AsyncMock(side_effect=[pay3, conf3])
        svc._invoice_repo.find_by_id = AsyncMock(return_value=inv)
        # 600 already confirmed, this 300 = 900 total
        svc._payment_repo.sum_confirmed_for_invoice = AsyncMock(side_effect=[Decimal("600"), Decimal("900")])
        svc._payment_repo.update_fields = AsyncMock()
        svc._invoice_repo.update_fields = AsyncMock()

        with _patch():
            await svc.confirm_payment(pay3_id)
        kwargs = svc._invoice_repo.update_fields.call_args[1]
        assert kwargs["status"] == "paid"

    @pytest.mark.asyncio
    async def test_multiple_payments_can_be_cancelled(self):
        svc, db = _make_svc()
        # cancelling multiple payments in sequence should all succeed
        for status_val in ["pending", "confirmed"]:
            pay_id = uuid.uuid4()
            original = _make_payment(id=pay_id, status=status_val)
            cancelled = _make_payment(id=pay_id, status="cancelled")
            svc._payment_repo.find_by_id = AsyncMock(side_effect=[original, cancelled])
            svc._payment_repo.update_fields = AsyncMock()
            with _patch():
                result = await svc.cancel_payment(pay_id)
            assert result.status == "cancelled"
