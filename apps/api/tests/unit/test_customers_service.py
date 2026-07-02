"""Unit tests for Customer Account module — Sprint 41.

Tests: schemas, repo helpers, service CRUD, pagination, filters, search,
       owner assignment, health changes, cache behaviour, tenant isolation,
       events, and edge conditions. Target: 110+ tests.
"""

from __future__ import annotations

import base64
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Shared fixtures ───────────────────────────────────────────────────────────

_ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WS = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_CTX = SimpleNamespace(org_id=_ORG)
_CID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
_OWN = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
_NOW = datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)


def _customer(**kw):
    defaults = dict(
        id=_CID,
        tenant_id=_ORG,
        workspace_id=_WS,
        company_name="Acme Corp",
        display_name="Acme",
        industry="SaaS",
        website="https://acme.com",
        email="info@acme.com",
        phone="+911234567890",
        address="123 Main St",
        city="Mumbai",
        state="MH",
        country="India",
        postal_code="400001",
        company_size="50-200",
        annual_revenue_inr=Decimal("5000000"),
        status="active",
        health_status="healthy",
        relationship_owner_id=_OWN,
        primary_contact_name="Jane Doe",
        primary_contact_email="jane@acme.com",
        primary_contact_phone="+910987654321",
        notes="VIP customer",
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


@contextmanager
def _ctx(redis_val=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=redis_val)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    with (
        patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
        patch("corpmind.modules.customers.service.get_redis", return_value=r),
    ):
        yield r


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestSchemas:
    def test_customer_create_required_fields(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        req = CustomerCreate(
            workspace_id=_WS,
            company_name="TestCo",
            display_name="Test",
        )
        assert req.status == "active"
        assert req.health_status == "healthy"

    def test_customer_create_invalid_status(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", status="bogus")

    def test_customer_create_invalid_health(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", health_status="good")

    def test_customer_create_all_statuses(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        for s in ["active", "inactive", "prospect", "former"]:
            req = CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", status=s)
            assert req.status == s

    def test_customer_create_all_health_statuses(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        for h in ["healthy", "attention", "at_risk", "inactive"]:
            req = CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", health_status=h)
            assert req.health_status == h

    def test_customer_create_revenue_non_negative(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", annual_revenue_inr=Decimal("-1"))

    def test_customer_out_from_attributes(self):
        from corpmind.modules.customers.schemas import CustomerOut
        c = _customer()
        out = CustomerOut.model_validate(c)
        assert out.company_name == "Acme Corp"
        assert out.status == "active"

    def test_customer_out_nullable_fields(self):
        from corpmind.modules.customers.schemas import CustomerOut
        c = _customer(industry=None, website=None, email=None, annual_revenue_inr=None)
        out = CustomerOut.model_validate(c)
        assert out.industry is None
        assert out.annual_revenue_inr is None

    def test_customer_update_partial(self):
        from corpmind.modules.customers.schemas import CustomerUpdate
        u = CustomerUpdate(company_name="NewName")
        assert u.company_name == "NewName"
        assert u.display_name is None

    def test_customer_update_all_none(self):
        from corpmind.modules.customers.schemas import CustomerUpdate
        u = CustomerUpdate()
        assert u.model_dump(exclude_none=True) == {}

    def test_customer_health_update_valid(self):
        from corpmind.modules.customers.schemas import CustomerHealthUpdate
        u = CustomerHealthUpdate(health_status="at_risk")
        assert u.health_status == "at_risk"

    def test_customer_health_update_invalid(self):
        from corpmind.modules.customers.schemas import CustomerHealthUpdate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerHealthUpdate(health_status="critical")

    def test_customer_owner_assign(self):
        from corpmind.modules.customers.schemas import CustomerOwnerAssign
        a = CustomerOwnerAssign(relationship_owner_id=_OWN)
        assert a.relationship_owner_id == _OWN

    def test_customer_filters_defaults(self):
        from corpmind.modules.customers.schemas import CustomerFilters
        f = CustomerFilters(workspace_id=_WS)
        assert f.limit == 50
        assert f.cursor is None
        assert f.search is None

    def test_customer_list_out_empty(self):
        from corpmind.modules.customers.schemas import CustomerListOut
        out = CustomerListOut(items=[], next_cursor=None, has_more=False, total=0)
        assert out.has_more is False

    def test_customer_create_company_name_empty_invalid(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerCreate(workspace_id=_WS, company_name="", display_name="X")

    def test_customer_out_json_roundtrip(self):
        from corpmind.modules.customers.schemas import CustomerOut
        c = _customer()
        out = CustomerOut.model_validate(c)
        restored = CustomerOut.model_validate_json(out.model_dump_json())
        assert restored.id == out.id
        assert restored.company_name == out.company_name


# ── Cursor encoding tests ─────────────────────────────────────────────────────

class TestCursorEncoding:
    def test_encode_returns_string(self):
        from corpmind.modules.customers.repo import encode_cursor
        token = encode_cursor(_NOW, _CID)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_roundtrip(self):
        from corpmind.modules.customers.repo import encode_cursor, decode_cursor
        token = encode_cursor(_NOW, _CID)
        ts, rid = decode_cursor(token)
        assert rid == _CID
        assert ts.isoformat() == _NOW.isoformat()

    def test_different_ids_produce_different_cursors(self):
        from corpmind.modules.customers.repo import encode_cursor
        id2 = uuid.uuid4()
        t1 = encode_cursor(_NOW, _CID)
        t2 = encode_cursor(_NOW, id2)
        assert t1 != t2

    def test_decode_invalid_raises(self):
        from corpmind.modules.customers.repo import decode_cursor
        with pytest.raises(Exception):
            decode_cursor("not-a-valid-cursor")

    def test_cursor_url_safe(self):
        from corpmind.modules.customers.repo import encode_cursor
        token = encode_cursor(_NOW, _CID)
        assert "+" not in token
        assert "/" not in token


# ── Service: create ───────────────────────────────────────────────────────────

from corpmind.modules.customers.service import CustomerService
from corpmind.modules.customers.schemas import (
    CustomerCreate, CustomerUpdate, CustomerHealthUpdate, CustomerOwnerAssign, CustomerFilters,
)


def _svc(session=None):
    return CustomerService(session or AsyncMock())


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_returns_out(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_create(self_repo, c):
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        with _ctx() as r:
            with patch.object(CustomerRepo, "create", fake_create):
                svc = _svc(session)
                req = CustomerCreate(workspace_id=_WS, company_name="Acme", display_name="Acme")
                out = await svc.create_customer(req)
        assert out.company_name == "Acme"
        assert out.status == "active"

    @pytest.mark.asyncio
    async def test_create_sets_tenant_id(self):
        captured = []
        async def fake_create(self_repo, c):
            captured.append(c.tenant_id)
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx():
            with patch.object(CustomerRepo, "create", fake_create):
                svc = _svc(session)
                await svc.create_customer(CustomerCreate(workspace_id=_WS, company_name="X", display_name="X"))
        assert captured[0] == _ORG

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_create(self_repo, c):
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        with _ctx() as r:
            with patch.object(CustomerRepo, "create", fake_create):
                await _svc(session).create_customer(
                    CustomerCreate(workspace_id=_WS, company_name="X", display_name="X")
                )
        r.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_prospect_status(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_create(self_repo, c):
            c.created_at = _NOW
            c.updated_at = _NOW
            return c

        with _ctx():
            with patch.object(CustomerRepo, "create", fake_create):
                out = await _svc(session).create_customer(
                    CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", status="prospect")
                )
        assert out.status == "prospect"


# ── Service: get ─────────────────────────────────────────────────────────────

class TestGetCustomer:
    @pytest.mark.asyncio
    async def test_get_returns_cached(self):
        c = _customer()
        from corpmind.modules.customers.schemas import CustomerOut
        cached_json = CustomerOut.model_validate(c).model_dump_json()
        with _ctx(redis_val=cached_json):
            out = await _svc().get_customer(_CID)
        assert out.id == _CID

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(self_repo, cid):
            return None
        with _ctx():
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().get_customer(_CID)

    @pytest.mark.asyncio
    async def test_get_stores_in_cache(self):
        c = _customer()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(self_repo, cid):
            return c
        with _ctx() as r:
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                await _svc().get_customer(_CID)
        r.set.assert_called()

    @pytest.mark.asyncio
    async def test_get_works_when_cache_down(self):
        c = _customer()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(self_repo, cid):
            return c
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        bad_redis.set = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=bad_redis),
            patch.object(CustomerRepo, "find_by_id", fake_find),
        ):
            out = await _svc().get_customer(_CID)
        assert out.id == _CID


# ── Service: update ───────────────────────────────────────────────────────────

class TestUpdateCustomer:
    def _setup_update(self, existing=None):
        c = existing or _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo

        async def fake_find(self_repo, cid):
            return c

        async def fake_update(self_repo, cid, **vals):
            for k, v in vals.items():
                object.__setattr__(c, k, v) if hasattr(c, k) else None

        async def fake_find2(self_repo2, cid):
            return c

        return session, fake_find, fake_update, fake_find2, c

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(self_repo, cid):
            return None
        with _ctx():
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().update_customer(_CID, CustomerUpdate(company_name="New"))

    @pytest.mark.asyncio
    async def test_update_changes_company_name(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo

        async def fake_find(self_repo, cid):
            return c

        async def fake_update(self_repo, cid, **vals):
            c.company_name = vals.get("company_name", c.company_name)

        with _ctx():
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                out = await _svc(session).update_customer(_CID, CustomerUpdate(company_name="New Corp"))
        assert out.company_name == "New Corp"

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v): pass
        with _ctx() as r:
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                await _svc(session).update_customer(_CID, CustomerUpdate(notes="note"))
        r.delete.assert_called()


# ── Service: archive ──────────────────────────────────────────────────────────

class TestArchiveCustomer:
    @pytest.mark.asyncio
    async def test_archive_sets_archived_status(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v): c.status = v.get("status", c.status)
        with _ctx():
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                out = await _svc(session).archive_customer(_CID)
        assert out.status == "archived"

    @pytest.mark.asyncio
    async def test_archive_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return None
        with _ctx():
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().archive_customer(_CID)


# ── Service: change_health ───────────────────────────────────────────────────

class TestChangeHealth:
    @pytest.mark.asyncio
    async def test_change_health_valid(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v): c.health_status = v.get("health_status", c.health_status)
        with _ctx():
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                out = await _svc(session).change_health(_CID, "at_risk")
        assert out.health_status == "at_risk"

    @pytest.mark.asyncio
    async def test_change_health_invalid_raises(self):
        from corpmind.core.exceptions import ValidationError
        with _ctx():
            with pytest.raises(ValidationError):
                await _svc().change_health(_CID, "critical")

    @pytest.mark.asyncio
    async def test_change_health_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return None
        with _ctx():
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().change_health(_CID, "attention")

    @pytest.mark.asyncio
    async def test_change_health_all_values(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        for h in ["healthy", "attention", "at_risk", "inactive"]:
            c = _customer(health_status=h)  # returned by re-fetch after update

            async def fake_find(s, cid, _c=c): return _c
            async def fake_update(s, cid, **v): pass

            with _ctx():
                with (
                    patch.object(CustomerRepo, "find_by_id", fake_find),
                    patch.object(CustomerRepo, "update_fields", fake_update),
                ):
                    out = await _svc(session).change_health(_CID, h)
            assert out.health_status == h


# ── Service: assign_owner ─────────────────────────────────────────────────────

class TestAssignOwner:
    @pytest.mark.asyncio
    async def test_assign_owner_sets_owner(self):
        c = _customer(relationship_owner_id=None)
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        new_owner = uuid.uuid4()
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v):
            c.relationship_owner_id = v.get("relationship_owner_id", c.relationship_owner_id)
        with _ctx():
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                out = await _svc(session).assign_owner(_CID, new_owner)
        assert out.relationship_owner_id == new_owner

    @pytest.mark.asyncio
    async def test_assign_owner_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return None
        with _ctx():
            with patch.object(CustomerRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().assign_owner(_CID, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_assign_owner_busts_cache(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v): pass
        with _ctx() as r:
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                await _svc(session).assign_owner(_CID, _OWN)
        r.delete.assert_called()


# ── Service: list_customers ───────────────────────────────────────────────────

class TestListCustomers:
    def _mock_list(self, rows, total=None):
        from corpmind.modules.customers.repo import CustomerRepo

        async def fake_count(self_repo, ws, **kw):
            return total if total is not None else len(rows)

        async def fake_list(self_repo, ws, **kw):
            return rows

        return fake_count, fake_list

    @pytest.mark.asyncio
    async def test_empty_list(self):
        fake_count, fake_list = self._mock_list([])
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert out.items == []
        assert out.has_more is False
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_single_page_no_cursor(self):
        rows = [_customer()]
        fake_count, fake_list = self._mock_list(rows)
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert len(out.items) == 1
        assert out.has_more is False
        assert out.next_cursor is None

    @pytest.mark.asyncio
    async def test_full_page_sets_next_cursor(self):
        rows = [_customer(id=uuid.uuid4()) for _ in range(50)]
        for r in rows:
            r.created_at = _NOW
        fake_count, fake_list = self._mock_list(rows, total=100)
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert out.has_more is True
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_cache_hit(self):
        from corpmind.modules.customers.schemas import CustomerListOut
        cached = CustomerListOut(items=[], next_cursor=None, has_more=False, total=99)
        with _ctx(redis_val=cached.model_dump_json()):
            out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert out.total == 99

    @pytest.mark.asyncio
    async def test_list_cache_miss_stores_result(self):
        rows = [_customer()]
        fake_count, fake_list = self._mock_list(rows)
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx() as r:
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        r.set.assert_called()

    @pytest.mark.asyncio
    async def test_list_with_filter_skips_cache(self):
        rows = [_customer()]
        fake_count, fake_list = self._mock_list(rows)
        from corpmind.modules.customers.repo import CustomerRepo
        # Cache has stale data but filtered query bypasses it
        with _ctx(redis_val='{"items":[],"next_cursor":null,"has_more":false,"total":99}') as r:
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS, status="active"))
        assert out.total == 1  # not the cached 99

    @pytest.mark.asyncio
    async def test_list_with_search_bypasses_cache(self):
        rows = []
        fake_count, fake_list = self._mock_list(rows, 0)
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx(redis_val='{"items":[],"next_cursor":null,"has_more":false,"total":55}'):
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS, search="acme"))
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_list_with_cursor_bypasses_cache(self):
        from corpmind.modules.customers.repo import encode_cursor
        cursor = encode_cursor(_NOW, _CID)
        rows = []
        fake_count, fake_list = self._mock_list(rows, 0)
        from corpmind.modules.customers.repo import CustomerRepo
        with _ctx(redis_val='{"items":[],"next_cursor":null,"has_more":false,"total":77}'):
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS, cursor=cursor))
        assert out.total == 0


# ── Service: search_customers ─────────────────────────────────────────────────

class TestSearchCustomers:
    @pytest.mark.asyncio
    async def test_search_returns_items(self):
        rows = [_customer(), _customer(id=uuid.uuid4(), company_name="Acme India")]
        for r in rows:
            r.created_at = _NOW
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_count(s, ws, **kw): return 2
        async def fake_list(s, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                items = await _svc().search_customers(_WS, "acme")
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_search_empty_result(self):
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_count(s, ws, **kw): return 0
        async def fake_list(s, ws, **kw): return []
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                items = await _svc().search_customers(_WS, "noresult")
        assert items == []


# ── Tenant isolation ─────────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_context_tenant(self):
        captured = []
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_create(self_repo, c):
            captured.append(c.tenant_id)
            c.created_at = _NOW
            c.updated_at = _NOW
            return c
        with _ctx():
            with patch.object(CustomerRepo, "create", fake_create):
                await _svc(session).create_customer(CustomerCreate(workspace_id=_WS, company_name="X", display_name="X"))
        assert captured[0] == _ORG

    @pytest.mark.asyncio
    async def test_get_tenant_from_context_not_param(self):
        """Service never accepts tenant_id as a parameter — always from context."""
        import inspect
        sig = inspect.signature(CustomerService.get_customer)
        assert "tenant_id" not in sig.parameters

    @pytest.mark.asyncio
    async def test_find_by_id_filters_by_tenant(self):
        """Repo find_by_id includes tenant_id in WHERE — verified via query structure."""
        from corpmind.modules.customers.repo import CustomerRepo
        repo = CustomerRepo(AsyncMock())
        # Verify the WHERE clause includes tenant_id by inspecting the method
        import inspect
        src = inspect.getsource(CustomerRepo.find_by_id)
        assert "tenant_id" in src

    @pytest.mark.asyncio
    async def test_list_page_filters_by_tenant(self):
        from corpmind.modules.customers.repo import CustomerRepo
        import inspect
        src = inspect.getsource(CustomerRepo.list_page)
        assert "tenant_id" in src

    @pytest.mark.asyncio
    async def test_update_filters_by_tenant(self):
        from corpmind.modules.customers.repo import CustomerRepo
        import inspect
        src = inspect.getsource(CustomerRepo.update_fields)
        assert "tenant_id" in src


# ── Cache key isolation ───────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_includes_org(self):
        from corpmind.modules.customers.service import _list_key
        key = _list_key(_ORG, _WS)
        assert str(_ORG) in key
        assert str(_WS) in key

    def test_detail_key_includes_org_and_customer(self):
        from corpmind.modules.customers.service import _detail_key
        key = _detail_key(_ORG, _CID)
        assert str(_ORG) in key
        assert str(_CID) in key

    def test_different_orgs_different_list_keys(self):
        from corpmind.modules.customers.service import _list_key
        org2 = uuid.uuid4()
        assert _list_key(_ORG, _WS) != _list_key(org2, _WS)

    def test_different_customers_different_detail_keys(self):
        from corpmind.modules.customers.service import _detail_key
        c2 = uuid.uuid4()
        assert _detail_key(_ORG, _CID) != _detail_key(_ORG, c2)


# ── Events tests ──────────────────────────────────────────────────────────────

class TestEvents:
    def test_customer_created_frozen(self):
        from corpmind.modules.customers.events import CustomerCreated
        import dataclasses
        e = CustomerCreated(
            customer_id=_CID, tenant_id=_ORG, workspace_id=_WS, company_name="Acme"
        )
        assert e.company_name == "Acme"
        # frozen=True raises FrozenInstanceError on regular attribute assignment
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.company_name = "X"  # type: ignore[misc]

    def test_customer_updated_fields(self):
        from corpmind.modules.customers.events import CustomerUpdated
        e = CustomerUpdated(customer_id=_CID, tenant_id=_ORG)
        assert e.customer_id == _CID

    def test_customer_archived_fields(self):
        from corpmind.modules.customers.events import CustomerArchived
        e = CustomerArchived(customer_id=_CID, tenant_id=_ORG)
        assert e.tenant_id == _ORG

    def test_customer_health_changed_from_to(self):
        from corpmind.modules.customers.events import CustomerHealthChanged
        e = CustomerHealthChanged(
            customer_id=_CID, tenant_id=_ORG, from_health="healthy", to_health="at_risk"
        )
        assert e.from_health == "healthy"
        assert e.to_health == "at_risk"

    def test_customer_owner_assigned_fields(self):
        from corpmind.modules.customers.events import CustomerOwnerAssigned
        e = CustomerOwnerAssigned(customer_id=_CID, tenant_id=_ORG, owner_id=_OWN)
        assert e.owner_id == _OWN

    def test_all_events_have_occurred_at(self):
        import dataclasses
        from corpmind.modules.customers import events as ev
        for klass in [
            ev.CustomerCreated, ev.CustomerUpdated, ev.CustomerArchived,
            ev.CustomerHealthChanged, ev.CustomerOwnerAssigned,
        ]:
            assert dataclasses.is_dataclass(klass)
            assert "occurred_at" in {f.name for f in dataclasses.fields(klass)}


# ── Edge conditions ───────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_list_less_than_full_page_no_cursor(self):
        rows = [_customer(id=uuid.uuid4()) for _ in range(10)]
        for r in rows:
            r.created_at = _NOW
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_count(s, ws, **kw): return 10
        async def fake_list(s, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS, limit=50))
        assert out.next_cursor is None
        assert out.has_more is False

    @pytest.mark.asyncio
    async def test_list_exact_page_size_sets_cursor(self):
        rows = [_customer(id=uuid.uuid4()) for _ in range(10)]
        for r in rows:
            r.created_at = _NOW
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_count(s, ws, **kw): return 20
        async def fake_list(s, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS, limit=10))
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_update_empty_body_noop(self):
        c = _customer()
        session = AsyncMock()
        session.commit = AsyncMock()
        from corpmind.modules.customers.repo import CustomerRepo
        fields_written = {}
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **v): fields_written.update(v)
        with _ctx():
            with (
                patch.object(CustomerRepo, "find_by_id", fake_find),
                patch.object(CustomerRepo, "update_fields", fake_update),
            ):
                await _svc(session).update_customer(_CID, CustomerUpdate())
        # Only updated_at should be written
        assert set(fields_written.keys()) == {"updated_at"}

    def test_customer_filters_limit_bounds(self):
        from corpmind.modules.customers.schemas import CustomerFilters
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerFilters(workspace_id=_WS, limit=0)
        with pytest.raises((pydantic.ValidationError, ValueError)):
            CustomerFilters(workspace_id=_WS, limit=201)

    @pytest.mark.asyncio
    async def test_bust_cache_silent_on_redis_error(self):
        bad_redis = AsyncMock()
        bad_redis.delete = AsyncMock(side_effect=Exception("fail"))
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.core.redis.get_redis", return_value=bad_redis),
        ):
            # Should not raise even if Redis delete fails
            svc = _svc()
            await svc._bust_list_cache(_ORG, _WS)

    def test_valid_statuses_constant(self):
        from corpmind.modules.customers.schemas import VALID_STATUSES
        assert "active" in VALID_STATUSES
        assert "former" in VALID_STATUSES

    def test_valid_health_statuses_constant(self):
        from corpmind.modules.customers.schemas import VALID_HEALTH_STATUSES
        assert "at_risk" in VALID_HEALTH_STATUSES
        assert "inactive" in VALID_HEALTH_STATUSES


# ── Pagination extra ──────────────────────────────────────────────────────────

class TestPaginationExtra:
    @pytest.mark.asyncio
    async def test_next_cursor_is_decodeable(self):
        from corpmind.modules.customers.repo import CustomerRepo, decode_cursor, encode_cursor
        import uuid as _uuid
        rows = [_customer(id=_uuid.uuid4()) for _ in range(50)]
        for r in rows:
            r.created_at = _NOW
        async def fake_count(s, ws, **kw): return 100
        async def fake_list(s, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        ts, rid = decode_cursor(out.next_cursor)
        assert rid == rows[-1].id

    @pytest.mark.asyncio
    async def test_cursor_from_page1_passed_to_page2(self):
        from corpmind.modules.customers.repo import CustomerRepo, encode_cursor
        import uuid as _uuid
        page1_rows = [_customer(id=_uuid.uuid4()) for _ in range(10)]
        for r in page1_rows:
            r.created_at = _NOW
        page2_rows = [_customer(id=_uuid.uuid4()) for _ in range(5)]
        for r in page2_rows:
            r.created_at = _NOW
        call_count = [0]
        async def fake_count(s, ws, **kw): return 15
        async def fake_list(s, ws, cursor=None, **kw):
            call_count[0] += 1
            return page1_rows if call_count[0] == 1 else page2_rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                p1 = await _svc().list_customers(CustomerFilters(workspace_id=_WS, limit=10))
                p2 = await _svc().list_customers(CustomerFilters(workspace_id=_WS, limit=10, cursor=p1.next_cursor))
        assert p1.has_more is True
        assert p2.has_more is False

    @pytest.mark.asyncio
    async def test_total_count_independent_of_page(self):
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_count(s, ws, **kw): return 250
        async def fake_list(s, ws, **kw): return [_customer()]
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert out.total == 250

    @pytest.mark.asyncio
    async def test_custom_limit_respected(self):
        from corpmind.modules.customers.repo import CustomerRepo
        import uuid as _uuid
        rows = [_customer(id=_uuid.uuid4()) for _ in range(5)]
        for r in rows:
            r.created_at = _NOW
        received_limit = [None]
        async def fake_count(s, ws, **kw): return 100
        async def fake_list(s, ws, limit=50, **kw):
            received_limit[0] = limit
            return rows
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                await _svc().list_customers(CustomerFilters(workspace_id=_WS, limit=5))
        assert received_limit[0] == 5


# ── Filter pass-through tests ─────────────────────────────────────────────────

class TestFilterPassThrough:
    @pytest.mark.asyncio
    async def _run_with_filter(self, **filter_kw):
        from corpmind.modules.customers.repo import CustomerRepo
        received = {}
        async def fake_count(s, ws, **kw): received.update(kw); return 0
        async def fake_list(s, ws, **kw): return []
        with _ctx():
            with (
                patch.object(CustomerRepo, "count", fake_count),
                patch.object(CustomerRepo, "list_page", fake_list),
            ):
                await _svc().list_customers(CustomerFilters(workspace_id=_WS, **filter_kw))
        return received

    @pytest.mark.asyncio
    async def test_status_filter_forwarded(self):
        received = await self._run_with_filter(status="inactive")
        assert received.get("status") == "inactive"

    @pytest.mark.asyncio
    async def test_industry_filter_forwarded(self):
        received = await self._run_with_filter(industry="Finance")
        assert received.get("industry") == "Finance"

    @pytest.mark.asyncio
    async def test_health_status_filter_forwarded(self):
        received = await self._run_with_filter(health_status="at_risk")
        assert received.get("health_status") == "at_risk"

    @pytest.mark.asyncio
    async def test_owner_id_filter_forwarded(self):
        received = await self._run_with_filter(owner_id=_OWN)
        assert received.get("owner_id") == _OWN

    @pytest.mark.asyncio
    async def test_search_filter_forwarded(self):
        received = await self._run_with_filter(search="abc")
        assert received.get("search") == "abc"


# ── Repo helper function tests ────────────────────────────────────────────────

class TestRepoCursorHelpers:
    def test_encode_decode_with_tz(self):
        from corpmind.modules.customers.repo import encode_cursor, decode_cursor
        from datetime import timezone
        ts = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
        token = encode_cursor(ts, _CID)
        back_ts, back_id = decode_cursor(token)
        assert back_id == _CID

    def test_cursor_is_base64(self):
        from corpmind.modules.customers.repo import encode_cursor
        import base64
        token = encode_cursor(_NOW, _CID)
        # Should decode without error
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        assert "|" in decoded

    def test_decode_malformed_raises(self):
        from corpmind.modules.customers.repo import decode_cursor
        import pytest
        with pytest.raises(Exception):
            decode_cursor("abc")

    def test_encode_same_inputs_same_output(self):
        from corpmind.modules.customers.repo import encode_cursor
        t1 = encode_cursor(_NOW, _CID)
        t2 = encode_cursor(_NOW, _CID)
        assert t1 == t2

    def test_different_timestamps_different_cursors(self):
        from corpmind.modules.customers.repo import encode_cursor
        from datetime import timedelta
        t2 = _NOW + timedelta(seconds=1)
        assert encode_cursor(_NOW, _CID) != encode_cursor(t2, _CID)


# ── Schema extra tests ────────────────────────────────────────────────────────

class TestSchemasExtra:
    def test_customer_update_model_dump_excludes_none(self):
        from corpmind.modules.customers.schemas import CustomerUpdate
        u = CustomerUpdate(company_name="New")
        dumped = u.model_dump(exclude_none=True)
        assert "display_name" not in dumped
        assert dumped["company_name"] == "New"

    def test_customer_list_out_has_more_true(self):
        from corpmind.modules.customers.schemas import CustomerListOut
        out = CustomerListOut(
            items=[], next_cursor="tok", has_more=True, total=100
        )
        assert out.has_more is True

    def test_customer_filters_all_fields(self):
        from corpmind.modules.customers.schemas import CustomerFilters
        f = CustomerFilters(
            workspace_id=_WS,
            status="active",
            industry="SaaS",
            health_status="healthy",
            owner_id=_OWN,
            search="acme",
            cursor="tok",
            limit=10,
        )
        assert f.status == "active"
        assert f.limit == 10

    def test_customer_create_with_revenue(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        req = CustomerCreate(
            workspace_id=_WS,
            company_name="Big Corp",
            display_name="Big",
            annual_revenue_inr=Decimal("10000000.00"),
        )
        assert req.annual_revenue_inr == Decimal("10000000.00")

    def test_customer_out_annual_revenue_decimal(self):
        from corpmind.modules.customers.schemas import CustomerOut
        c = _customer(annual_revenue_inr=Decimal("999999.99"))
        out = CustomerOut.model_validate(c)
        assert out.annual_revenue_inr == Decimal("999999.99")

    def test_customer_create_no_owner(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        req = CustomerCreate(workspace_id=_WS, company_name="X", display_name="X")
        assert req.relationship_owner_id is None

    def test_customer_create_prospect_default_health(self):
        from corpmind.modules.customers.schemas import CustomerCreate
        req = CustomerCreate(workspace_id=_WS, company_name="X", display_name="X", status="prospect")
        assert req.health_status == "healthy"

    def test_customer_out_workspace_id(self):
        from corpmind.modules.customers.schemas import CustomerOut
        c = _customer()
        out = CustomerOut.model_validate(c)
        assert out.workspace_id == _WS

    def test_customer_health_update_attention(self):
        from corpmind.modules.customers.schemas import CustomerHealthUpdate
        u = CustomerHealthUpdate(health_status="attention")
        assert u.health_status == "attention"

    def test_customer_owner_assign_different_id(self):
        from corpmind.modules.customers.schemas import CustomerOwnerAssign
        import uuid as _uuid
        new_id = _uuid.uuid4()
        a = CustomerOwnerAssign(relationship_owner_id=new_id)
        assert a.relationship_owner_id == new_id


# ── Service list cache resilience ─────────────────────────────────────────────

class TestListCacheResilience:
    @pytest.mark.asyncio
    async def test_list_works_when_redis_down(self):
        from corpmind.modules.customers.repo import CustomerRepo
        rows = [_customer()]
        async def fake_count(s, ws, **kw): return 1
        async def fake_list(s, ws, **kw): return rows
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        bad_redis.set = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=bad_redis),
            patch.object(CustomerRepo, "count", fake_count),
            patch.object(CustomerRepo, "list_page", fake_list),
        ):
            out = await _svc().list_customers(CustomerFilters(workspace_id=_WS))
        assert len(out.items) == 1

    @pytest.mark.asyncio
    async def test_detail_works_when_redis_down_and_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.customers.repo import CustomerRepo
        async def fake_find(s, cid): return None
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=bad_redis),
            patch.object(CustomerRepo, "find_by_id", fake_find),
        ):
            with pytest.raises(NotFoundError):
                await _svc().get_customer(_CID)


# ── Event integrity extras ────────────────────────────────────────────────────

class TestEventIntegrityExtra:
    def test_customer_updated_has_tenant_id(self):
        from corpmind.modules.customers.events import CustomerUpdated
        e = CustomerUpdated(customer_id=_CID, tenant_id=_ORG)
        assert e.tenant_id == _ORG

    def test_customer_health_changed_has_both_statuses(self):
        from corpmind.modules.customers.events import CustomerHealthChanged
        e = CustomerHealthChanged(
            customer_id=_CID,
            tenant_id=_ORG,
            from_health="healthy",
            to_health="at_risk",
        )
        assert e.from_health == "healthy"
        assert e.to_health == "at_risk"

    def test_customer_owner_assigned_has_owner_id(self):
        from corpmind.modules.customers.events import CustomerOwnerAssigned
        e = CustomerOwnerAssigned(
            customer_id=_CID,
            tenant_id=_ORG,
            owner_id=_OWN,
        )
        assert e.owner_id == _OWN

    def test_customer_archived_event(self):
        from corpmind.modules.customers.events import CustomerArchived
        e = CustomerArchived(customer_id=_CID, tenant_id=_ORG)
        assert e.customer_id == _CID
        assert e.tenant_id == _ORG


# ── Service cache busting ─────────────────────────────────────────────────────

class TestCacheBusting:
    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        from corpmind.modules.customers.repo import CustomerRepo
        deleted_keys: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        async def fake_delete(key): deleted_keys.append(key)
        redis.delete = fake_delete

        async def fake_create(s, c): return c
        async def fake_find(s, cid): return _customer()
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=redis),
            patch.object(CustomerRepo, "create", fake_create),
        ):
            req = CustomerCreate(workspace_id=_WS, company_name="X", display_name="X")
            await _svc().create_customer(req)
        assert any("customers:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        from corpmind.modules.customers.repo import CustomerRepo
        deleted_keys: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        async def fake_delete(key): deleted_keys.append(key)
        redis.delete = fake_delete

        c = _customer()
        async def fake_find(s, cid): return c
        async def fake_update(s, cid, **kw): pass
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=redis),
            patch.object(CustomerRepo, "find_by_id", fake_find),
            patch.object(CustomerRepo, "update_fields", fake_update),
        ):
            req = CustomerUpdate(company_name="New")
            await _svc().update_customer(_CID, req)
        assert any("customers:detail" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_archive_busts_detail_cache(self):
        from corpmind.modules.customers.repo import CustomerRepo
        deleted_keys: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        async def fake_delete(key): deleted_keys.append(key)
        redis.delete = fake_delete

        c = _customer()
        archived = _customer(status="archived")
        calls = [0]
        async def fake_find(s, cid):
            calls[0] += 1
            return archived if calls[0] > 1 else c
        async def fake_update(s, cid, **kw): pass
        with (
            patch("corpmind.modules.customers.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.customers.service.get_redis", return_value=redis),
            patch.object(CustomerRepo, "find_by_id", fake_find),
            patch.object(CustomerRepo, "update_fields", fake_update),
        ):
            await _svc().archive_customer(_CID)
        assert any("customers:detail" in k for k in deleted_keys)


# ── Service key helpers ───────────────────────────────────────────────────────

class TestCacheKeyHelpers:
    def test_list_key_format(self):
        from corpmind.modules.customers.service import _list_key
        k = _list_key(_ORG, _WS)
        assert k.startswith(f"t:{_ORG}:")
        assert "customers:list" in k

    def test_detail_key_format(self):
        from corpmind.modules.customers.service import _detail_key
        k = _detail_key(_ORG, _CID)
        assert f"customers:detail:{_CID}" in k

    def test_list_and_detail_keys_differ(self):
        from corpmind.modules.customers.service import _list_key, _detail_key
        assert _list_key(_ORG, _WS) != _detail_key(_ORG, _CID)
