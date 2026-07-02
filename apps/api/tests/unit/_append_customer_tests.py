"""Append extra tests to test_customers_service.py."""
import pathlib

path = pathlib.Path(__file__).parent / "test_customers_service.py"

extra = r"""

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
"""

with open(path, "a", encoding="utf-8") as f:
    f.write(extra)
print("ok")
