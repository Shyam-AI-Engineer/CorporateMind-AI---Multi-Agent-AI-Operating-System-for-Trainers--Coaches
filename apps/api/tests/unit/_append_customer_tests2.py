"""Append final batch of tests."""
import pathlib

path = pathlib.Path(__file__).parent / "test_customers_service.py"

extra = r"""

# ── Event integrity extras ────────────────────────────────────────────────────

class TestEventIntegrityExtra:
    def test_customer_updated_carries_changed_fields(self):
        from corpmind.modules.customers.events import CustomerUpdated
        e = CustomerUpdated(
            customer_id=_CID,
            tenant_id=_ORG,
            workspace_id=_WS,
            changed_fields={"company_name": "New"},
        )
        assert e.changed_fields["company_name"] == "New"

    def test_customer_health_changed_has_both_statuses(self):
        from corpmind.modules.customers.events import CustomerHealthChanged
        e = CustomerHealthChanged(
            customer_id=_CID,
            tenant_id=_ORG,
            workspace_id=_WS,
            old_health="healthy",
            new_health="at_risk",
        )
        assert e.old_health == "healthy"
        assert e.new_health == "at_risk"

    def test_customer_owner_assigned_has_owner_id(self):
        from corpmind.modules.customers.events import CustomerOwnerAssigned
        e = CustomerOwnerAssigned(
            customer_id=_CID,
            tenant_id=_ORG,
            workspace_id=_WS,
            owner_id=_OWN,
        )
        assert e.owner_id == _OWN

    def test_customer_archived_event(self):
        from corpmind.modules.customers.events import CustomerArchived
        e = CustomerArchived(
            customer_id=_CID,
            tenant_id=_ORG,
            workspace_id=_WS,
        )
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
"""

with open(path, "a", encoding="utf-8") as f:
    f.write(extra)
print("ok")
