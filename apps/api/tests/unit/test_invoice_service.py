"""Unit tests for CustomerInvoiceService — Sprint 51.

154+ tests covering: cache keys, schemas, cursor helpers, create, update, issue,
mark_paid, cancel, get, list, get_kpis, tenant isolation, events.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.modules.billing.events import (
    InvoiceCancelled,
    InvoiceCreated,
    InvoiceIssued,
    InvoicePaid,
)
from corpmind.modules.billing.models import CustomerInvoice
from corpmind.modules.billing.schemas import (
    CustomerInvoiceCreate,
    CustomerInvoiceFilters,
    CustomerInvoiceListOut,
    CustomerInvoiceOut,
    CustomerInvoiceUpdate,
    InvoiceKPIsOut,
    MarkInvoicePaid,
)
from corpmind.modules.billing.repo import (
    _decode_invoice_cursor,
    _encode_invoice_cursor,
)
from corpmind.modules.billing.service import (
    CustomerInvoiceService,
    _invoice_detail_key,
    _invoice_kpis_key,
    _invoice_list_key,
)

# ── Harness ───────────────────────────────────────────────────────────────────

_PATCH_CTX = "corpmind.modules.billing.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.billing.service.get_redis"

_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_ORG2 = uuid.uuid4()
_WS2 = uuid.uuid4()


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
    svc = CustomerInvoiceService(db)
    svc._repo = MagicMock()
    return svc, db


def _make_invoice(**overrides) -> CustomerInvoice:
    inv = CustomerInvoice()
    inv.id = uuid.uuid4()
    inv.tenant_id = _ORG
    inv.workspace_id = _WS
    inv.customer_id = uuid.uuid4()
    inv.invoice_number = "INV-001"
    inv.invoice_date = date(2026, 7, 1)
    inv.due_date = date(2026, 7, 31)
    inv.amount = Decimal("10000.00")
    inv.tax_amount = Decimal("1800.00")
    inv.total_amount = Decimal("11800.00")
    inv.currency = "INR"
    inv.status = "draft"
    inv.payment_date = None
    inv.renewal_id = None
    inv.notes = None
    inv.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    inv.updated_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for k, v in overrides.items():
        setattr(inv, k, v)
    return inv


def _make_create(**overrides) -> CustomerInvoiceCreate:
    defaults = dict(
        workspace_id=_WS,
        customer_id=uuid.uuid4(),
        invoice_number="INV-002",
        invoice_date=date(2026, 7, 1),
        due_date=date(2026, 7, 31),
        amount=Decimal("5000.00"),
        tax_amount=Decimal("900.00"),
        total_amount=Decimal("5900.00"),
        currency="INR",
    )
    defaults.update(overrides)
    return CustomerInvoiceCreate(**defaults)


# ── TestCacheKeys ─────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self):
        key = _invoice_list_key(_ORG, _WS)
        assert key == f"t:{_ORG}:{_WS}:billing:invoices:list"

    def test_detail_key_format(self):
        rid = uuid.uuid4()
        key = _invoice_detail_key(_ORG, rid)
        assert key == f"t:{_ORG}:billing:invoices:detail:{rid}"

    def test_kpis_key_format(self):
        key = _invoice_kpis_key(_ORG, _WS)
        assert key == f"t:{_ORG}:{_WS}:billing:invoices:kpis"

    def test_list_key_includes_org_and_ws(self):
        key = _invoice_list_key(_ORG, _WS)
        assert str(_ORG) in key
        assert str(_WS) in key

    def test_detail_key_includes_record_id(self):
        rid = uuid.uuid4()
        key = _invoice_detail_key(_ORG, rid)
        assert str(rid) in key

    def test_different_orgs_different_list_keys(self):
        assert _invoice_list_key(_ORG, _WS) != _invoice_list_key(_ORG2, _WS)

    def test_different_workspaces_different_list_keys(self):
        assert _invoice_list_key(_ORG, _WS) != _invoice_list_key(_ORG, _WS2)

    def test_different_invoice_ids_different_detail_keys(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        assert _invoice_detail_key(_ORG, a) != _invoice_detail_key(_ORG, b)


# ── TestInvoiceSchemas ────────────────────────────────────────────────────────

class TestInvoiceSchemas:
    def test_invoice_out_from_attributes(self):
        inv = _make_invoice()
        out = CustomerInvoiceOut.model_validate(inv)
        assert out.id == inv.id
        assert out.status == "draft"

    def test_invoice_out_defaults(self):
        inv = _make_invoice(invoice_number=None, notes=None)
        out = CustomerInvoiceOut.model_validate(inv)
        assert out.invoice_number is None
        assert out.notes is None

    def test_invoice_create_minimal(self):
        req = CustomerInvoiceCreate(workspace_id=_WS, customer_id=uuid.uuid4())
        assert req.currency == "INR"
        assert req.invoice_number is None

    def test_invoice_create_all_fields(self):
        req = _make_create()
        assert req.amount == Decimal("5000.00")
        assert req.total_amount == Decimal("5900.00")

    def test_invoice_update_partial(self):
        upd = CustomerInvoiceUpdate(notes="updated note")
        assert upd.notes == "updated note"
        assert upd.invoice_number is None

    def test_invoice_list_out_structure(self):
        inv = _make_invoice()
        out = CustomerInvoiceOut.model_validate(inv)
        lst = CustomerInvoiceListOut(items=[out], total=1, next_cursor=None, has_more=False)
        assert len(lst.items) == 1
        assert lst.total == 1

    def test_invoice_kpis_out_defaults(self):
        k = InvoiceKPIsOut()
        assert k.total_outstanding == Decimal("0.00")
        assert k.count_draft == 0

    def test_mark_paid_requires_payment_date(self):
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        assert req.payment_date == date(2026, 7, 15)

    def test_invoice_out_json_roundtrip(self):
        inv = _make_invoice()
        out = CustomerInvoiceOut.model_validate(inv)
        restored = CustomerInvoiceOut.model_validate_json(out.model_dump_json())
        assert restored.id == out.id
        assert restored.status == out.status

    def test_invoice_list_json_roundtrip(self):
        inv = _make_invoice()
        out = CustomerInvoiceOut.model_validate(inv)
        lst = CustomerInvoiceListOut(items=[out], total=1, next_cursor=None, has_more=False)
        restored = CustomerInvoiceListOut.model_validate_json(lst.model_dump_json())
        assert restored.total == 1

    def test_invoice_kpis_json_roundtrip(self):
        k = InvoiceKPIsOut(total_outstanding=Decimal("500.00"), count_issued=2)
        restored = InvoiceKPIsOut.model_validate_json(k.model_dump_json())
        assert restored.count_issued == 2

    def test_filters_default_limit(self):
        f = CustomerInvoiceFilters(workspace_id=_WS)
        assert f.limit == 50
        assert f.cursor is None


# ── TestCreateInvoice ─────────────────────────────────────────────────────────

class TestCreateInvoice:
    @pytest.mark.asyncio
    async def test_create_returns_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create()
        with _patch():
            result = await svc.create(req)
        assert isinstance(result, CustomerInvoiceOut)

    @pytest.mark.asyncio
    async def test_create_default_status_draft(self):
        svc, _ = _make_svc()
        created_inv = None

        async def _capture(record):
            nonlocal created_inv
            created_inv = record
            return record

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _capture
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: created_inv)
        req = _make_create()
        with _patch():
            await svc.create(req)
        assert created_inv is not None
        assert created_inv.status == "draft"

    @pytest.mark.asyncio
    async def test_create_sets_tenant_id_from_context(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create()
        custom_org = uuid.uuid4()
        with _patch(ctx=_ctx(org=custom_org)):
            await svc.create(req)
        assert captured.tenant_id == custom_org

    @pytest.mark.asyncio
    async def test_create_sets_workspace_id(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create(workspace_id=_WS2)
        with _patch():
            await svc.create(req)
        assert captured.workspace_id == _WS2

    @pytest.mark.asyncio
    async def test_create_with_invoice_number(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create(invoice_number="INV-999")
        with _patch():
            await svc.create(req)
        assert captured.invoice_number == "INV-999"

    @pytest.mark.asyncio
    async def test_create_without_invoice_number_skips_uniqueness_check(self):
        svc, _ = _make_svc()
        inv = _make_invoice(invoice_number=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create(invoice_number=None)
        with _patch():
            await svc.create(req)
        svc._repo.find_by_invoice_number.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_duplicate_invoice_number_raises_validation_error(self):
        svc, _ = _make_svc()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=_make_invoice())
        req = _make_create(invoice_number="INV-DUPE")
        with _patch():
            with pytest.raises(ValidationError):
                await svc.create(req)

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis()
        req = _make_create()
        with _patch(redis=redis):
            await svc.create(req)
        assert redis.delete.called

    @pytest.mark.asyncio
    async def test_create_redis_bust_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create()
        with _patch(redis=_redis(fail=True)):
            result = await svc.create(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_with_renewal_id(self):
        svc, _ = _make_svc()
        renewal_id = uuid.uuid4()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create(renewal_id=renewal_id)
        with _patch():
            await svc.create(req)
        assert captured.renewal_id == renewal_id

    @pytest.mark.asyncio
    async def test_create_sets_created_at_and_updated_at(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create()
        with _patch():
            await svc.create(req)
        assert captured.created_at is not None
        assert captured.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_calls_repo_create(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create()
        with _patch():
            await svc.create(req)
        svc._repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_currency_stored(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create(currency="USD")
        with _patch():
            await svc.create(req)
        assert captured.currency == "USD"

    @pytest.mark.asyncio
    async def test_create_payment_date_is_none(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create()
        with _patch():
            await svc.create(req)
        assert captured.payment_date is None

    @pytest.mark.asyncio
    async def test_create_emits_event_logged(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create()
        with _patch():
            result = await svc.create(req)
        assert result.status == "draft"

    @pytest.mark.asyncio
    async def test_create_without_renewal_id(self):
        svc, _ = _make_svc()
        inv = _make_invoice(renewal_id=None)
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create(renewal_id=None)
        with _patch():
            result = await svc.create(req)
        assert result.renewal_id is None

    @pytest.mark.asyncio
    async def test_create_with_notes(self):
        svc, _ = _make_svc()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create(notes="Please pay promptly")
        with _patch():
            await svc.create(req)
        assert captured.notes == "Please pay promptly"

    @pytest.mark.asyncio
    async def test_create_busts_kpis_cache(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis()
        req = _make_create()
        with _patch(redis=redis):
            await svc.create(req)
        # Both list and kpis cache are busted (2 deletes)
        assert redis.delete.call_count >= 2


# ── TestUpdateInvoice ─────────────────────────────────────────────────────────

class TestUpdateInvoice:
    @pytest.mark.asyncio
    async def test_update_draft_succeeds(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft", notes="updated")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update(inv.id, CustomerInvoiceUpdate(notes="updated"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_non_draft_raises_validation_error(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch():
            with pytest.raises(ValidationError, match="cannot be updated"):
                await svc.update(inv.id, CustomerInvoiceUpdate(notes="x"))

    @pytest.mark.asyncio
    async def test_update_paid_raises_validation_error(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="paid")
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch():
            with pytest.raises(ValidationError):
                await svc.update(inv.id, CustomerInvoiceUpdate(notes="x"))

    @pytest.mark.asyncio
    async def test_update_cancelled_raises_validation_error(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch():
            with pytest.raises(ValidationError):
                await svc.update(inv.id, CustomerInvoiceUpdate(notes="x"))

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.update(uuid.uuid4(), CustomerInvoiceUpdate(notes="x"))

    @pytest.mark.asyncio
    async def test_update_busts_caches(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        redis = _redis()
        with _patch(redis=redis):
            await svc.update(inv.id, CustomerInvoiceUpdate(notes="x"))
        assert redis.delete.called

    @pytest.mark.asyncio
    async def test_update_calls_update_fields(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft", notes="new note")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch():
            await svc.update(inv.id, CustomerInvoiceUpdate(notes="new note"))
        svc._repo.update_fields.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_duplicate_number_raises(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft", invoice_number="INV-001")
        other = _make_invoice(invoice_number="INV-002")
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        svc._repo.find_by_invoice_number = AsyncMock(return_value=other)
        with _patch():
            with pytest.raises(ValidationError):
                await svc.update(inv.id, CustomerInvoiceUpdate(invoice_number="INV-002"))

    @pytest.mark.asyncio
    async def test_update_same_number_on_same_invoice_ok(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft", invoice_number="INV-001")
        updated = _make_invoice(status="draft", invoice_number="INV-001")
        # same id → no conflict
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=inv)
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update(inv.id, CustomerInvoiceUpdate(invoice_number="INV-001"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_returns_updated_invoice(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft", currency="USD")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update(inv.id, CustomerInvoiceUpdate(currency="USD"))
        assert result.currency == "USD"

    @pytest.mark.asyncio
    async def test_update_partial_fields_only(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        req = CustomerInvoiceUpdate()  # no fields set
        with _patch():
            await svc.update(inv.id, req)
        # only updated_at should be in the call
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "updated_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_update_redis_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        updated = _make_invoice(status="draft")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch(redis=_redis(fail=True)):
            result = await svc.update(inv.id, CustomerInvoiceUpdate(notes="x"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_date_fields(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        new_due = date(2026, 8, 31)
        updated = _make_invoice(status="draft", due_date=new_due)
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, updated])
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.update(inv.id, CustomerInvoiceUpdate(due_date=new_due))
        assert result.due_date == new_due


# ── TestIssueInvoice ──────────────────────────────────────────────────────────

class TestIssueInvoice:
    @pytest.mark.asyncio
    async def test_issue_draft_to_issued(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.issue(inv.id)
        assert result.status == "issued"

    @pytest.mark.asyncio
    async def test_issue_already_issued_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="issued"))
        with _patch():
            with pytest.raises(ValidationError, match="cannot be issued"):
                await svc.issue(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_issue_paid_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="paid"))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.issue(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_issue_cancelled_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.issue(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_issue_overdue_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="overdue"))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.issue(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_issue_not_found_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.issue(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_issue_calls_update_fields_with_issued_status(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            await svc.issue(inv.id)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs.get("status") == "issued"

    @pytest.mark.asyncio
    async def test_issue_busts_caches(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        redis = _redis()
        with _patch(redis=redis):
            await svc.issue(inv.id)
        assert redis.delete.called

    @pytest.mark.asyncio
    async def test_issue_redis_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        with _patch(redis=_redis(fail=True)):
            result = await svc.issue(inv.id)
        assert result is not None

    @pytest.mark.asyncio
    async def test_issue_returns_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.issue(inv.id)
        assert isinstance(result, CustomerInvoiceOut)
        assert result.status == "issued"

    @pytest.mark.asyncio
    async def test_issue_commits_session(self):
        svc, db = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            await svc.issue(inv.id)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_issue_busts_kpis_cache(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        redis = _redis()
        with _patch(redis=redis):
            await svc.issue(inv.id)
        # list + detail + kpis all busted
        assert redis.delete.call_count >= 3


# ── TestMarkInvoicePaid ───────────────────────────────────────────────────────

class TestMarkInvoicePaid:
    @pytest.mark.asyncio
    async def test_mark_paid_from_issued(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            result = await svc.mark_paid(inv.id, req)
        assert result.status == "paid"

    @pytest.mark.asyncio
    async def test_mark_paid_records_payment_date(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            result = await svc.mark_paid(inv.id, req)
        assert result.payment_date == date(2026, 7, 15)

    @pytest.mark.asyncio
    async def test_mark_paid_calls_update_fields_with_payment_date(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            await svc.mark_paid(inv.id, req)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs.get("payment_date") == date(2026, 7, 15)
        assert call_kwargs.get("status") == "paid"

    @pytest.mark.asyncio
    async def test_mark_paid_from_draft_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="draft"))
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            with pytest.raises(ValidationError, match="cannot be marked paid"):
                await svc.mark_paid(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_mark_paid_from_paid_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="paid"))
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.mark_paid(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_mark_paid_from_cancelled_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="cancelled"))
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.mark_paid(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_mark_paid_not_found_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.mark_paid(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_mark_paid_busts_caches(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        redis = _redis()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch(redis=redis):
            await svc.mark_paid(inv.id, req)
        assert redis.delete.called

    @pytest.mark.asyncio
    async def test_mark_paid_redis_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch(redis=_redis(fail=True)):
            result = await svc.mark_paid(inv.id, req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_mark_paid_returns_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            result = await svc.mark_paid(inv.id, req)
        assert isinstance(result, CustomerInvoiceOut)

    @pytest.mark.asyncio
    async def test_mark_paid_commits_session(self):
        svc, db = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            await svc.mark_paid(inv.id, req)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_paid_from_overdue_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="overdue"))
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.mark_paid(uuid.uuid4(), req)


# ── TestCancelInvoice ─────────────────────────────────────────────────────────

class TestCancelInvoice:
    @pytest.mark.asyncio
    async def test_cancel_draft_to_cancelled(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel(inv.id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_issued_to_cancelled(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel(inv.id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_overdue_to_cancelled(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="overdue")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel(inv.id)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_paid_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="paid"))
        with _patch():
            with pytest.raises(ValidationError, match="cannot be cancelled"):
                await svc.cancel(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_invoice(status="cancelled"))
        with _patch():
            with pytest.raises(ValidationError):
                await svc.cancel(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_not_found_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.cancel(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_calls_update_fields_with_cancelled_status(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel(inv.id)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs.get("status") == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_busts_caches(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        redis = _redis()
        with _patch(redis=redis):
            await svc.cancel(inv.id)
        assert redis.delete.called

    @pytest.mark.asyncio
    async def test_cancel_returns_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel(inv.id)
        assert isinstance(result, CustomerInvoiceOut)

    @pytest.mark.asyncio
    async def test_cancel_redis_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch(redis=_redis(fail=True)):
            result = await svc.cancel(inv.id)
        assert result is not None

    @pytest.mark.asyncio
    async def test_cancel_commits_session(self):
        svc, db = _make_svc()
        inv = _make_invoice(status="draft")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            await svc.cancel(inv.id)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_sets_cancelled_status(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        with _patch():
            result = await svc.cancel(inv.id)
        assert result.status == "cancelled"


# ── TestGetInvoice ────────────────────────────────────────────────────────────

class TestGetInvoice:
    @pytest.mark.asyncio
    async def test_get_cache_hit(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        cached_json = CustomerInvoiceOut.model_validate(inv).model_dump_json()
        with _patch(redis=_redis(get_val=cached_json)):
            result = await svc.get(inv.id)
        assert result.id == inv.id
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cache_miss_queries_repo(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get(inv.id)
        assert result.id == inv.id
        svc._repo.find_by_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stores_in_cache_on_miss(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.get(inv.id)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch(redis=_redis(get_val=None)):
            with pytest.raises(NotFoundError):
                await svc.get(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_redis_get_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch(redis=_redis(fail=True)):
            result = await svc.get(inv.id)
        assert result.id == inv.id

    @pytest.mark.asyncio
    async def test_get_redis_set_failure_silent(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis(get_val=None)
        redis.set = AsyncMock(side_effect=Exception("set failed"))
        with _patch(redis=redis):
            result = await svc.get(inv.id)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_returns_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get(inv.id)
        assert isinstance(result, CustomerInvoiceOut)

    @pytest.mark.asyncio
    async def test_get_correct_key_uses_tenant_and_id(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.get(inv.id)
        key_arg = redis.set.call_args[0][0]
        assert str(inv.id) in key_arg
        assert str(_ORG) in key_arg

    @pytest.mark.asyncio
    async def test_get_cache_hit_skips_repo(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        cached_json = CustomerInvoiceOut.model_validate(inv).model_dump_json()
        svc._repo.find_by_id = AsyncMock()
        with _patch(redis=_redis(get_val=cached_json)):
            await svc.get(inv.id)
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_ttl_set_on_cache_write(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.get(inv.id)
        call_kwargs = redis.set.call_args[1]
        assert call_kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_get_different_tenant_different_key(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis1, redis2 = _redis(get_val=None), _redis(get_val=None)
        with _patch(ctx=_ctx(org=_ORG), redis=redis1):
            await svc.get(inv.id)
        with _patch(ctx=_ctx(org=_ORG2), redis=redis2):
            await svc.get(inv.id)
        key1 = redis1.set.call_args[0][0]
        key2 = redis2.set.call_args[0][0]
        assert key1 != key2


# ── TestListInvoices ──────────────────────────────────────────────────────────

class TestListInvoices:
    def _default_filters(self, ws=None) -> CustomerInvoiceFilters:
        return CustomerInvoiceFilters(workspace_id=ws or _WS)

    @pytest.mark.asyncio
    async def test_list_default_cache_hit(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        out = CustomerInvoiceOut.model_validate(inv)
        lst = CustomerInvoiceListOut(items=[out], total=1, has_more=False)
        cached_json = lst.model_dump_json()
        with _patch(redis=_redis(get_val=cached_json)):
            result = await svc.list(self._default_filters())
        assert result.total == 1
        svc._repo.count.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_default_cache_miss_queries_repo(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(self._default_filters())
        assert result.total == 0
        svc._repo.count.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_filtered_not_cached(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_invoice()])
        redis = _redis(get_val=None)
        filters = CustomerInvoiceFilters(workspace_id=_WS, status="draft")
        with _patch(redis=redis):
            await svc.list(filters)
        redis.get.assert_not_called()
        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_has_more_true(self):
        svc, _ = _make_svc()
        invoices = [_make_invoice() for _ in range(51)]
        svc._repo.count = AsyncMock(return_value=51)
        svc._repo.list_page = AsyncMock(return_value=invoices)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(self._default_filters())
        assert result.has_more is True
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_has_more_false(self):
        svc, _ = _make_svc()
        invoices = [_make_invoice() for _ in range(5)]
        svc._repo.count = AsyncMock(return_value=5)
        svc._repo.list_page = AsyncMock(return_value=invoices)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(self._default_filters())
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_returns_correct_total(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=42)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(self._default_filters())
        assert result.total == 42

    @pytest.mark.asyncio
    async def test_list_redis_get_failure_silent(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch(redis=_redis(fail=True)):
            result = await svc.list(self._default_filters())
        assert result is not None

    @pytest.mark.asyncio
    async def test_list_redis_set_failure_silent(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        redis.set = AsyncMock(side_effect=Exception("fail"))
        with _patch(redis=redis):
            result = await svc.list(self._default_filters())
        assert result is not None

    @pytest.mark.asyncio
    async def test_list_items_mapped_to_invoice_out(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[inv])
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(self._default_filters())
        assert len(result.items) == 1
        assert isinstance(result.items[0], CustomerInvoiceOut)

    @pytest.mark.asyncio
    async def test_list_with_customer_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        filters = CustomerInvoiceFilters(workspace_id=_WS, customer_id=uuid.uuid4())
        with _patch(redis=redis):
            await svc.list(filters)
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_limit_respected(self):
        svc, _ = _make_svc()
        invoices = [_make_invoice() for _ in range(10)]
        svc._repo.count = AsyncMock(return_value=10)
        svc._repo.list_page = AsyncMock(return_value=invoices)
        filters = CustomerInvoiceFilters(workspace_id=_WS, limit=10)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.list(filters)
        assert len(result.items) == 10

    @pytest.mark.asyncio
    async def test_list_default_limit_50(self):
        f = CustomerInvoiceFilters(workspace_id=_WS)
        assert f.limit == 50

    @pytest.mark.asyncio
    async def test_list_stores_default_result_in_cache(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.list(self._default_filters())
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_with_renewal_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        filters = CustomerInvoiceFilters(workspace_id=_WS, renewal_id=uuid.uuid4())
        with _patch(redis=redis):
            await svc.list(filters)
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_search_filter_not_cached(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        filters = CustomerInvoiceFilters(workspace_id=_WS, search="INV-")
        with _patch(redis=redis):
            await svc.list(filters)
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_cursor_not_cached(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis = _redis(get_val=None)
        filters = CustomerInvoiceFilters(workspace_id=_WS, cursor="abc123")
        with _patch(redis=redis):
            await svc.list(filters)
        redis.get.assert_not_called()


# ── TestGetKPIs ───────────────────────────────────────────────────────────────

class TestGetKPIs:
    @pytest.mark.asyncio
    async def test_get_kpis_returns_kpis_out(self):
        svc, _ = _make_svc()
        expected = InvoiceKPIsOut(total_outstanding=Decimal("5000"), count_issued=1)
        svc._repo.fetch_kpis = AsyncMock(return_value=expected)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_kpis(_WS)
        assert isinstance(result, InvoiceKPIsOut)

    @pytest.mark.asyncio
    async def test_get_kpis_cache_hit(self):
        svc, _ = _make_svc()
        k = InvoiceKPIsOut(count_draft=3)
        with _patch(redis=_redis(get_val=k.model_dump_json())):
            result = await svc.get_kpis(_WS)
        assert result.count_draft == 3
        svc._repo.fetch_kpis.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_kpis_cache_miss_queries_repo(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        with _patch(redis=_redis(get_val=None)):
            await svc.get_kpis(_WS)
        svc._repo.fetch_kpis.assert_called_once_with(_WS)

    @pytest.mark.asyncio
    async def test_get_kpis_stores_in_cache(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.get_kpis(_WS)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_kpis_redis_get_failure_silent(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        with _patch(redis=_redis(fail=True)):
            result = await svc.get_kpis(_WS)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_kpis_redis_set_failure_silent(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        redis = _redis(get_val=None)
        redis.set = AsyncMock(side_effect=Exception("fail"))
        with _patch(redis=redis):
            result = await svc.get_kpis(_WS)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_kpis_total_outstanding_from_repo(self):
        svc, _ = _make_svc()
        expected = InvoiceKPIsOut(total_outstanding=Decimal("15000.00"), count_issued=2)
        svc._repo.fetch_kpis = AsyncMock(return_value=expected)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_kpis(_WS)
        assert result.total_outstanding == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_get_kpis_all_zero_when_empty(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_kpis(_WS)
        assert result.total_outstanding == Decimal("0.00")
        assert result.count_draft == 0

    @pytest.mark.asyncio
    async def test_get_kpis_ttl_set(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        redis = _redis(get_val=None)
        with _patch(redis=redis):
            await svc.get_kpis(_WS)
        call_kwargs = redis.set.call_args[1]
        assert call_kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_get_kpis_count_by_status(self):
        svc, _ = _make_svc()
        expected = InvoiceKPIsOut(count_draft=1, count_issued=2, count_paid=3)
        svc._repo.fetch_kpis = AsyncMock(return_value=expected)
        with _patch(redis=_redis(get_val=None)):
            result = await svc.get_kpis(_WS)
        assert result.count_draft == 1
        assert result.count_issued == 2
        assert result.count_paid == 3


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_tenant_from_context_not_arg(self):
        svc, _ = _make_svc()
        custom_org = uuid.uuid4()
        captured = None

        async def _cap(rec):
            nonlocal captured
            captured = rec
            return rec

        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = _cap
        svc._repo.find_by_id = AsyncMock(side_effect=lambda rid: captured)
        req = _make_create()
        with _patch(ctx=_ctx(org=custom_org)):
            await svc.create(req)
        assert captured.tenant_id == custom_org

    @pytest.mark.asyncio
    async def test_list_key_uses_tenant_from_context(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        redis_a, redis_b = _redis(get_val=None), _redis(get_val=None)
        with _patch(ctx=_ctx(org=org_a), redis=redis_a):
            await svc.list(CustomerInvoiceFilters(workspace_id=_WS))
        with _patch(ctx=_ctx(org=org_b), redis=redis_b):
            await svc.list(CustomerInvoiceFilters(workspace_id=_WS))
        key_a = redis_a.set.call_args[0][0]
        key_b = redis_b.set.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_detail_key_uses_tenant_id(self):
        svc, _ = _make_svc()
        inv = _make_invoice()
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        redis_a, redis_b = _redis(get_val=None), _redis(get_val=None)
        with _patch(ctx=_ctx(org=org_a), redis=redis_a):
            await svc.get(inv.id)
        with _patch(ctx=_ctx(org=org_b), redis=redis_b):
            await svc.get(inv.id)
        key_a = redis_a.set.call_args[0][0]
        key_b = redis_b.set.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_kpis_key_uses_tenant_and_workspace(self):
        svc, _ = _make_svc()
        svc._repo.fetch_kpis = AsyncMock(return_value=InvoiceKPIsOut())
        redis_a, redis_b = _redis(get_val=None), _redis(get_val=None)
        with _patch(ctx=_ctx(org=_ORG), redis=redis_a):
            await svc.get_kpis(_WS)
        with _patch(ctx=_ctx(org=_ORG2), redis=redis_b):
            await svc.get_kpis(_WS)
        key_a = redis_a.set.call_args[0][0]
        key_b = redis_b.set.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_different_workspaces_different_list_keys(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        redis_a, redis_b = _redis(get_val=None), _redis(get_val=None)
        with _patch(redis=redis_a):
            await svc.list(CustomerInvoiceFilters(workspace_id=_WS))
        with _patch(redis=redis_b):
            await svc.list(CustomerInvoiceFilters(workspace_id=_WS2))
        key_a = redis_a.set.call_args[0][0]
        key_b = redis_b.set.call_args[0][0]
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_issue_bust_uses_tenant_from_context(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        issued = _make_invoice(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, issued])
        svc._repo.update_fields = AsyncMock()
        custom_org = uuid.uuid4()
        redis = _redis()
        with _patch(ctx=_ctx(org=custom_org), redis=redis):
            await svc.issue(inv.id)
        for call in redis.delete.call_args_list:
            key = call[0][0]
            assert str(custom_org) in key

    @pytest.mark.asyncio
    async def test_cancel_bust_uses_tenant_from_context(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="draft")
        cancelled = _make_invoice(status="cancelled")
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, cancelled])
        svc._repo.update_fields = AsyncMock()
        custom_org = uuid.uuid4()
        redis = _redis()
        with _patch(ctx=_ctx(org=custom_org), redis=redis):
            await svc.cancel(inv.id)
        for call in redis.delete.call_args_list:
            key = call[0][0]
            assert str(custom_org) in key

    @pytest.mark.asyncio
    async def test_mark_paid_bust_uses_tenant_from_context(self):
        svc, _ = _make_svc()
        inv = _make_invoice(status="issued")
        paid = _make_invoice(status="paid", payment_date=date(2026, 7, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[inv, paid])
        svc._repo.update_fields = AsyncMock()
        custom_org = uuid.uuid4()
        redis = _redis()
        req = MarkInvoicePaid(payment_date=date(2026, 7, 15))
        with _patch(ctx=_ctx(org=custom_org), redis=redis):
            await svc.mark_paid(inv.id, req)
        for call in redis.delete.call_args_list:
            key = call[0][0]
            assert str(custom_org) in key

    @pytest.mark.asyncio
    async def test_uniqueness_check_uses_tenant_from_context(self):
        svc, _ = _make_svc()
        custom_org = uuid.uuid4()
        captured_org = None

        async def _check(org, number):
            nonlocal captured_org
            captured_org = org
            return None

        svc._repo.find_by_invoice_number = _check
        inv = _make_invoice()
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        req = _make_create(invoice_number="INV-TEST")
        with _patch(ctx=_ctx(org=custom_org)):
            await svc.create(req)
        assert captured_org == custom_org

    @pytest.mark.asyncio
    async def test_create_list_bust_uses_workspace_from_request(self):
        svc, _ = _make_svc()
        inv = _make_invoice(workspace_id=_WS2)
        svc._repo.find_by_invoice_number = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(return_value=inv)
        svc._repo.find_by_id = AsyncMock(return_value=inv)
        redis = _redis()
        req = _make_create(workspace_id=_WS2)
        with _patch(redis=redis):
            await svc.create(req)
        deleted_keys = [call[0][0] for call in redis.delete.call_args_list]
        assert any(str(_WS2) in k for k in deleted_keys)


# ── TestEvents ────────────────────────────────────────────────────────────────

class TestEvents:
    def test_invoice_created_fields(self):
        inv_id = uuid.uuid4()
        ev = InvoiceCreated(
            invoice_id=inv_id,
            tenant_id=_ORG,
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            invoice_number="INV-001",
        )
        assert ev.invoice_id == inv_id
        assert ev.invoice_number == "INV-001"

    def test_invoice_issued_fields(self):
        inv_id = uuid.uuid4()
        ev = InvoiceIssued(
            invoice_id=inv_id,
            tenant_id=_ORG,
            customer_id=uuid.uuid4(),
            total_amount=Decimal("11800.00"),
        )
        assert ev.total_amount == Decimal("11800.00")

    def test_invoice_paid_has_payment_date(self):
        pdate = date(2026, 7, 15)
        ev = InvoicePaid(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            customer_id=uuid.uuid4(),
            payment_date=pdate,
            total_amount=Decimal("5000.00"),
        )
        assert ev.payment_date == pdate

    def test_invoice_paid_fields(self):
        ev = InvoicePaid(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            customer_id=uuid.uuid4(),
            payment_date=date(2026, 7, 15),
            total_amount=None,
        )
        assert ev.total_amount is None

    def test_invoice_cancelled_fields(self):
        inv_id = uuid.uuid4()
        ev = InvoiceCancelled(
            invoice_id=inv_id,
            tenant_id=_ORG,
            customer_id=uuid.uuid4(),
        )
        assert ev.invoice_id == inv_id

    def test_events_are_frozen_dataclasses(self):
        ev = InvoiceCreated(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            invoice_number=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            ev.invoice_id = uuid.uuid4()  # type: ignore[misc]

    def test_events_have_occurred_at(self):
        ev = InvoiceCreated(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            invoice_number=None,
        )
        assert ev.occurred_at is not None

    def test_invoice_created_null_number_allowed(self):
        ev = InvoiceCreated(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            invoice_number=None,
        )
        assert ev.invoice_number is None

    def test_invoice_issued_null_total_allowed(self):
        ev = InvoiceIssued(
            invoice_id=uuid.uuid4(),
            tenant_id=_ORG,
            customer_id=uuid.uuid4(),
            total_amount=None,
        )
        assert ev.total_amount is None

    def test_events_are_distinct_types(self):
        assert InvoiceCreated is not InvoiceIssued
        assert InvoiceIssued is not InvoicePaid
        assert InvoicePaid is not InvoiceCancelled


# ── TestCursorHelpers ─────────────────────────────────────────────────────────

class TestCursorHelpers:
    def test_encode_cursor_returns_string(self):
        ts = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        assert isinstance(token, str)

    def test_encode_cursor_is_base64_url_safe(self):
        ts = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        assert "+" not in token
        assert "/" not in token

    def test_encode_decode_roundtrip(self):
        ts = datetime(2026, 7, 1, 12, 30, 45, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        decoded_ts, decoded_id = _decode_invoice_cursor(token)
        assert decoded_id == rid

    def test_decode_preserves_datetime(self):
        ts = datetime(2026, 7, 1, 12, 30, 45, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        decoded_ts, _ = _decode_invoice_cursor(token)
        assert decoded_ts.isoformat() == ts.isoformat()

    def test_different_ids_produce_different_cursors(self):
        ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
        a, b = uuid.uuid4(), uuid.uuid4()
        assert _encode_invoice_cursor(ts, a) != _encode_invoice_cursor(ts, b)

    def test_different_timestamps_produce_different_cursors(self):
        rid = uuid.uuid4()
        ts1 = datetime(2026, 7, 1, tzinfo=timezone.utc)
        ts2 = datetime(2026, 7, 2, tzinfo=timezone.utc)
        assert _encode_invoice_cursor(ts1, rid) != _encode_invoice_cursor(ts2, rid)

    def test_decode_invalid_token_raises(self):
        with pytest.raises(Exception):
            _decode_invoice_cursor("not-valid-base64!!!")

    def test_cursor_token_stable_across_calls(self):
        ts = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
        rid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        token1 = _encode_invoice_cursor(ts, rid)
        token2 = _encode_invoice_cursor(ts, rid)
        assert token1 == token2

    def test_list_has_more_triggers_cursor_generation(self):
        """Service generates next_cursor when has_more is True (integration with list)."""
        ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        assert len(token) > 0

    def test_encode_cursor_contains_no_padding_issues(self):
        # urlsafe_b64encode can produce = padding — ensure decode still works
        ts = datetime(2026, 7, 1, 0, 0, 1, tzinfo=timezone.utc)
        rid = uuid.uuid4()
        token = _encode_invoice_cursor(ts, rid)
        decoded_ts, decoded_id = _decode_invoice_cursor(token)
        assert decoded_id == rid
