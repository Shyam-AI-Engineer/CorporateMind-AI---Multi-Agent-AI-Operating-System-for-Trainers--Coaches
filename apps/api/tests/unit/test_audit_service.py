"""Unit tests for AuditLogService — Sprint 53: Audit Log & Compliance Center.

181 tests across 13 test classes.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.audit.repo import (
    AuditLogRepo,
    _decode_audit_cursor,
    _encode_audit_cursor,
)
from corpmind.modules.audit.schemas import (
    AUDIT_SEVERITIES,
    AuditLogCreate,
    AuditLogFilters,
    AuditLogListOut,
    AuditLogOut,
    AuditStatisticsOut,
)
from corpmind.modules.audit.service import (
    AuditLogService,
    _audit_detail_key,
    _audit_list_key,
    _audit_stats_key,
)
from corpmind.core.exceptions import NotFoundError, ValidationError

_PATCH_CTX = "corpmind.modules.audit.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.audit.service.get_redis"

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
    svc = AuditLogService(db)
    svc._repo = MagicMock()
    return svc, db


def _make_log_out(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=_WS,
        user_id=None,
        entity_type=None,
        entity_id=None,
        action="invoice.created",
        module="billing",
        severity="info",
        ip_address=None,
        user_agent=None,
        metadata={},
        created_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return AuditLogOut(**defaults)


def _make_orm_log(**kwargs):
    rec = MagicMock()
    rec.id = kwargs.get("id", uuid.uuid4())
    rec.workspace_id = kwargs.get("workspace_id", _WS)
    rec.user_id = kwargs.get("user_id", None)
    rec.entity_type = kwargs.get("entity_type", None)
    rec.entity_id = kwargs.get("entity_id", None)
    rec.action = kwargs.get("action", "invoice.created")
    rec.module = kwargs.get("module", "billing")
    rec.severity = kwargs.get("severity", "info")
    rec.ip_address = kwargs.get("ip_address", None)
    rec.user_agent = kwargs.get("user_agent", None)
    rec.extra_data = kwargs.get("extra_data", {})
    rec.created_at = kwargs.get("created_at", datetime.now(UTC))
    return rec


# ── TestAuditCacheKeys ────────────────────────────────────────────────────────

class TestAuditCacheKeys:
    def test_list_key_format(self):
        key = _audit_list_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:audit:events:list" == key

    def test_list_key_org_isolation(self):
        org2 = uuid.uuid4()
        assert _audit_list_key(_ORG, _WS) != _audit_list_key(org2, _WS)

    def test_detail_key_format(self):
        log_id = uuid.uuid4()
        key = _audit_detail_key(_ORG, log_id)
        assert f"t:{_ORG}:audit:events:detail:{log_id}" == key

    def test_detail_key_uniqueness(self):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        assert _audit_detail_key(_ORG, id1) != _audit_detail_key(_ORG, id2)

    def test_stats_key_format(self):
        key = _audit_stats_key(_ORG, _WS)
        assert f"t:{_ORG}:{_WS}:audit:statistics" == key

    def test_keys_different_workspaces(self):
        ws2 = uuid.uuid4()
        assert _audit_list_key(_ORG, _WS) != _audit_list_key(_ORG, ws2)

    def test_keys_different_orgs(self):
        org2 = uuid.uuid4()
        assert _audit_stats_key(_ORG, _WS) != _audit_stats_key(org2, _WS)

    def test_list_key_returns_str(self):
        assert isinstance(_audit_list_key(_ORG, _WS), str)

    def test_stats_key_returns_str(self):
        assert isinstance(_audit_stats_key(_ORG, _WS), str)


# ── TestAuditSchemas ──────────────────────────────────────────────────────────

class TestAuditSchemas:
    def test_valid_severities_set(self):
        assert AUDIT_SEVERITIES == {"info", "warning", "critical"}

    def test_invalid_severity_not_in_set(self):
        assert "debug" not in AUDIT_SEVERITIES
        assert "error" not in AUDIT_SEVERITIES

    def test_audit_log_create_required_fields(self):
        req = AuditLogCreate(
            workspace_id=_WS,
            action="payment.confirmed",
            module="billing",
        )
        assert req.action == "payment.confirmed"
        assert req.module == "billing"

    def test_audit_log_create_defaults(self):
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        assert req.severity == "info"
        assert req.metadata == {}
        assert req.user_id is None

    def test_audit_log_out_from_orm(self):
        rec = _make_orm_log()
        out = AuditLogOut.model_validate(rec)
        assert out.action == rec.action
        assert out.module == rec.module

    def test_audit_log_out_metadata_alias(self):
        rec = _make_orm_log(extra_data={"key": "val"})
        out = AuditLogOut.model_validate(rec)
        assert out.metadata == {"key": "val"}

    def test_audit_log_filters_defaults(self):
        f = AuditLogFilters(workspace_id=_WS)
        assert f.limit == 50
        assert f.cursor is None
        assert f.module is None

    def test_audit_log_filters_limit_bounds(self):
        f = AuditLogFilters(workspace_id=_WS, limit=200)
        assert f.limit == 200
        with pytest.raises(Exception):
            AuditLogFilters(workspace_id=_WS, limit=0)

    def test_audit_statistics_out_fields(self):
        s = AuditStatisticsOut(
            total_events=100,
            by_severity={"info": 90, "warning": 10},
            by_module={"billing": 50},
            by_action={"invoice.created": 20},
            period_days=30,
        )
        assert s.total_events == 100
        assert s.period_days == 30

    def test_audit_log_list_out_fields(self):
        lst = AuditLogListOut(items=[], next_cursor=None, has_more=False, total=0)
        assert lst.total == 0
        assert lst.has_more is False

    def test_audit_log_out_json_round_trip(self):
        out = _make_log_out(metadata={"foo": "bar"})
        json_str = out.model_dump_json()
        restored = AuditLogOut.model_validate_json(json_str)
        assert restored.metadata == {"foo": "bar"}

    def test_audit_log_create_metadata_default(self):
        req = AuditLogCreate(workspace_id=_WS, action="a", module="b")
        assert isinstance(req.metadata, dict)


# ── TestLogEvent ──────────────────────────────────────────────────────────────

class TestLogEvent:
    @pytest.mark.asyncio
    async def test_creates_record_with_correct_tenant_id(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="billing")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.tenant_id == _ORG

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_workspace(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="billing")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.workspace_id == _WS

    @pytest.mark.asyncio
    async def test_creates_record_action(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(action="invoice.issued"))
        req = AuditLogCreate(workspace_id=_WS, action="invoice.issued", module="billing")
        with _patch():
            result = await svc.log_event(req)
        assert result.action == "invoice.issued"

    @pytest.mark.asyncio
    async def test_creates_record_module(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(module="customers"))
        req = AuditLogCreate(workspace_id=_WS, action="contact.created", module="customers")
        with _patch():
            result = await svc.log_event(req)
        assert result.module == "customers"

    @pytest.mark.asyncio
    async def test_creates_record_severity_info(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(severity="info"))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", severity="info")
        with _patch():
            result = await svc.log_event(req)
        assert result.severity == "info"

    @pytest.mark.asyncio
    async def test_creates_record_severity_warning(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(severity="warning"))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", severity="warning")
        with _patch():
            result = await svc.log_event(req)
        assert result.severity == "warning"

    @pytest.mark.asyncio
    async def test_creates_record_severity_critical(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(severity="critical"))
        req = AuditLogCreate(workspace_id=_WS, action="breach", module="security", severity="critical")
        with _patch():
            result = await svc.log_event(req)
        assert result.severity == "critical"

    @pytest.mark.asyncio
    async def test_invalid_severity_raises(self):
        svc, _ = _make_svc()
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", severity="debug")
        with _patch():
            with pytest.raises(ValidationError):
                await svc.log_event(req)

    @pytest.mark.asyncio
    async def test_commit_called_once(self):
        svc, db = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch():
            await svc.log_event(req)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_busts_list_cache(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        r = _redis()
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(redis=r):
            await svc.log_event(req)
        deleted_keys = [str(call.args[0]) for call in r.delete.call_args_list]
        assert any("audit:events:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_busts_stats_cache(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        r = _redis()
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(redis=r):
            await svc.log_event(req)
        deleted_keys = [str(call.args[0]) for call in r.delete.call_args_list]
        assert any("statistics" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(redis=_redis(fail=True)):
            result = await svc.log_event(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_audit_log_out(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch():
            result = await svc.log_event(req)
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_user_id_stored(self):
        user_id = uuid.uuid4()
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(user_id=user_id))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", user_id=user_id)
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.user_id == user_id

    @pytest.mark.asyncio
    async def test_entity_type_stored(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(entity_type="invoice"))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", entity_type="invoice")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.entity_type == "invoice"

    @pytest.mark.asyncio
    async def test_entity_id_stored(self):
        entity_id = uuid.uuid4()
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(entity_id=entity_id))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", entity_id=entity_id)
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.entity_id == entity_id

    @pytest.mark.asyncio
    async def test_ip_address_stored(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(ip_address="1.2.3.4"))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", ip_address="1.2.3.4")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.ip_address == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_user_agent_stored(self):
        svc, _ = _make_svc()
        ua = "Mozilla/5.0"
        svc._repo.create = AsyncMock(return_value=_make_orm_log(user_agent=ua))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", user_agent=ua)
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.user_agent == ua

    @pytest.mark.asyncio
    async def test_metadata_stored(self):
        svc, _ = _make_svc()
        meta = {"invoice_id": str(uuid.uuid4()), "amount": "500.00"}
        svc._repo.create = AsyncMock(return_value=_make_orm_log(extra_data=meta))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", metadata=meta)
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.extra_data == meta

    @pytest.mark.asyncio
    async def test_default_severity_is_info(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        assert req.severity == "info"
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.severity == "info"

    @pytest.mark.asyncio
    async def test_null_user_id_allowed(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", user_id=None)
        with _patch():
            result = await svc.log_event(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_null_entity_type_allowed(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", entity_type=None)
        with _patch():
            result = await svc.log_event(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_null_ip_allowed(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y", ip_address=None)
        with _patch():
            result = await svc.log_event(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_created_at_set_to_now(self):
        svc, _ = _make_svc()
        before = datetime.now(UTC)
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.created_at >= before

    @pytest.mark.asyncio
    async def test_event_metadata_defaults_to_empty_dict(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log(extra_data={}))
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch():
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.extra_data == {}


# ── TestGetEvent ──────────────────────────────────────────────────────────────

class TestGetEvent:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        cached_out = _make_log_out(id=log_id)
        r = _redis(get_val=cached_out.model_dump_json())
        with _patch(redis=r):
            result = await svc.get_event(log_id)
        svc._repo.find_by_id.assert_not_called()
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_cache_miss_hits_db(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        with _patch():
            result = await svc.get_event(log_id)
        svc._repo.find_by_id.assert_called_once_with(log_id)
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_cache_miss_sets_redis(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = _redis()
        with _patch(redis=r):
            await svc.get_event(log_id)
        r.set.assert_called_once()
        _, kwargs = r.set.call_args
        assert kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_not_found_raises_not_found_error(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError):
                await svc.get_event(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_redis_get_failure_falls_through_to_db(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        with _patch(redis=_redis(fail=True)):
            result = await svc.get_event(log_id)
        svc._repo.find_by_id.assert_called_once()
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_redis_set_failure_still_returns_result(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = MagicMock()
        r.get = AsyncMock(return_value=None)
        r.set = AsyncMock(side_effect=Exception("timeout"))
        with _patch(redis=r):
            result = await svc.get_event(log_id)
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_returns_audit_log_out(self):
        svc, _ = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log())
        with _patch():
            result = await svc.get_event(uuid.uuid4())
        assert isinstance(result, AuditLogOut)

    @pytest.mark.asyncio
    async def test_key_uses_org_id(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = _redis()
        with _patch(redis=r):
            await svc.get_event(log_id)
        set_key = r.set.call_args[0][0]
        assert str(_ORG) in set_key

    @pytest.mark.asyncio
    async def test_correct_ttl_set(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = _redis()
        with _patch(redis=r):
            await svc.get_event(log_id)
        _, kwargs = r.set.call_args
        assert kwargs["ex"] == 300

    @pytest.mark.asyncio
    async def test_cache_key_includes_log_id(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = _redis()
        with _patch(redis=r):
            await svc.get_event(log_id)
        set_key = r.set.call_args[0][0]
        assert str(log_id) in set_key

    @pytest.mark.asyncio
    async def test_not_found_message_includes_id(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch():
            with pytest.raises(NotFoundError) as exc_info:
                await svc.get_event(log_id)
        assert str(log_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_db_called_with_correct_id(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        with _patch():
            await svc.get_event(log_id)
        svc._repo.find_by_id.assert_called_once_with(log_id)

    @pytest.mark.asyncio
    async def test_cached_value_validated_as_audit_log_out(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        original = _make_log_out(id=log_id, action="payment.confirmed")
        r = _redis(get_val=original.model_dump_json())
        with _patch(redis=r):
            result = await svc.get_event(log_id)
        assert result.action == "payment.confirmed"

    @pytest.mark.asyncio
    async def test_redis_failure_on_set_does_not_raise(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = MagicMock()
        r.get = AsyncMock(return_value=None)
        r.set = AsyncMock(side_effect=Exception("redis write error"))
        with _patch(redis=r):
            result = await svc.get_event(log_id)
        assert result is not None

    @pytest.mark.asyncio
    async def test_result_matches_db_record(self):
        svc, _ = _make_svc()
        log_id = uuid.uuid4()
        orm = _make_orm_log(id=log_id, action="workflow.run.completed", module="workflows")
        svc._repo.find_by_id = AsyncMock(return_value=orm)
        with _patch():
            result = await svc.get_event(log_id)
        assert result.action == "workflow.run.completed"
        assert result.module == "workflows"


# ── TestListEvents ────────────────────────────────────────────────────────────

class TestListEvents:
    def _make_filters(self, **kwargs):
        return AuditLogFilters(workspace_id=_WS, **kwargs)

    @pytest.mark.asyncio
    async def test_default_query_uses_cache(self):
        svc, _ = _make_svc()
        cached = AuditLogListOut(items=[], next_cursor=None, has_more=False, total=0)
        r = _redis(get_val=cached.model_dump_json())
        with _patch(redis=r):
            result = await svc.list_events(self._make_filters())
        svc._repo.count.assert_not_called()
        assert isinstance(result, AuditLogListOut)

    @pytest.mark.asyncio
    async def test_filtered_query_skips_cache(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        r = _redis(get_val="should-not-be-used")
        with _patch(redis=r):
            await svc.list_events(self._make_filters(module="billing"))
        svc._repo.count.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_list_out(self):
        svc, _ = _make_svc()
        items = [_make_log_out()]
        cached = AuditLogListOut(items=items, next_cursor=None, has_more=False, total=1)
        r = _redis(get_val=cached.model_dump_json())
        with _patch(redis=r):
            result = await svc.list_events(self._make_filters())
        assert result.total == 1
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_cache_miss_hits_db(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=2)
        svc._repo.list_page = AsyncMock(return_value=[_make_orm_log(), _make_orm_log()])
        with _patch():
            result = await svc.list_events(self._make_filters())
        svc._repo.count.assert_called_once()
        svc._repo.list_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_set_on_miss_for_default(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        r = _redis()
        with _patch(redis=r):
            await svc.list_events(self._make_filters())
        r.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_has_more_true(self):
        svc, _ = _make_svc()
        rows = [_make_orm_log() for _ in range(51)]  # limit=50, repo returns 51
        svc._repo.count = AsyncMock(return_value=60)
        svc._repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_events(self._make_filters(limit=50))
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_pagination_has_more_false(self):
        svc, _ = _make_svc()
        rows = [_make_orm_log() for _ in range(10)]
        svc._repo.count = AsyncMock(return_value=10)
        svc._repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_events(self._make_filters(limit=50))
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_next_cursor_set_when_has_more(self):
        svc, _ = _make_svc()
        rows = [_make_orm_log() for _ in range(51)]
        svc._repo.count = AsyncMock(return_value=100)
        svc._repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_events(self._make_filters(limit=50))
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_next_cursor_none_when_no_more(self):
        svc, _ = _make_svc()
        rows = [_make_orm_log() for _ in range(5)]
        svc._repo.count = AsyncMock(return_value=5)
        svc._repo.list_page = AsyncMock(return_value=rows)
        with _patch():
            result = await svc.list_events(self._make_filters(limit=50))
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_total_from_count_query(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=42)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_events(self._make_filters())
        assert result.total == 42

    @pytest.mark.asyncio
    async def test_module_filter_applied(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(module="billing"))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["module"] == "billing"

    @pytest.mark.asyncio
    async def test_severity_filter_applied(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(severity="critical"))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_user_id_filter_applied(self):
        svc, _ = _make_svc()
        user_id = uuid.uuid4()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(user_id=user_id))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_entity_type_filter_applied(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(entity_type="invoice"))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["entity_type"] == "invoice"

    @pytest.mark.asyncio
    async def test_action_filter_applied(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(action="invoice.issued"))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["action"] == "invoice.issued"

    @pytest.mark.asyncio
    async def test_date_range_filter_applied(self):
        svc, _ = _make_svc()
        now = datetime.now(UTC)
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(date_from=now))
        call_kwargs = svc._repo.count.call_args[1]
        assert call_kwargs["date_from"] == now

    @pytest.mark.asyncio
    async def test_cursor_passed_to_repo(self):
        svc, _ = _make_svc()
        cursor = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(cursor=cursor))
        call_kwargs = svc._repo.list_page.call_args[1]
        assert call_kwargs["cursor"] == cursor

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._make_filters(limit=25))
        call_kwargs = svc._repo.list_page.call_args[1]
        assert call_kwargs["limit"] == 25

    @pytest.mark.asyncio
    async def test_items_are_audit_log_out(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_events(self._make_filters())
        assert all(isinstance(item, AuditLogOut) for item in result.items)

    @pytest.mark.asyncio
    async def test_redis_failure_graceful(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch(redis=_redis(fail=True)):
            result = await svc.list_events(self._make_filters())
        assert isinstance(result, AuditLogListOut)


# ── TestListEntityEvents ──────────────────────────────────────────────────────

class TestListEntityEvents:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_filters_by_entity_type(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        with _patch():
            await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        args = svc._repo.list_by_entity.call_args[0]
        assert args[0] == "invoice"

    @pytest.mark.asyncio
    async def test_filters_by_entity_id(self):
        svc, _ = _make_svc()
        entity_id = uuid.uuid4()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        with _patch():
            await svc.list_entity_events("invoice", entity_id, _WS)
        args = svc._repo.list_by_entity.call_args[0]
        assert args[1] == entity_id

    @pytest.mark.asyncio
    async def test_filters_by_workspace(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        ws = uuid.uuid4()
        with _patch():
            await svc.list_entity_events("invoice", uuid.uuid4(), ws)
        args = svc._repo.list_by_entity.call_args[0]
        assert args[2] == ws

    @pytest.mark.asyncio
    async def test_empty_list_returned(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_audit_log_out_list(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        assert all(isinstance(r, AuditLogOut) for r in result)

    @pytest.mark.asyncio
    async def test_repo_called_with_correct_args(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        entity_id = uuid.uuid4()
        with _patch():
            await svc.list_entity_events("customer", entity_id, _WS)
        svc._repo.list_by_entity.assert_called_once_with("customer", entity_id, _WS)

    @pytest.mark.asyncio
    async def test_multiple_events_returned(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[_make_orm_log(), _make_orm_log()])
        with _patch():
            result = await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_entity_type_preserved(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[_make_orm_log(entity_type="workflow")])
        with _patch():
            result = await svc.list_entity_events("workflow", uuid.uuid4(), _WS)
        assert result[0].entity_type == "workflow"

    @pytest.mark.asyncio
    async def test_entity_id_preserved(self):
        svc, _ = _make_svc()
        entity_id = uuid.uuid4()
        svc._repo.list_by_entity = AsyncMock(return_value=[_make_orm_log(entity_id=entity_id)])
        with _patch():
            result = await svc.list_entity_events("invoice", entity_id, _WS)
        assert result[0].entity_id == entity_id

    @pytest.mark.asyncio
    async def test_workspace_id_used(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        ws = uuid.uuid4()
        with _patch():
            await svc.list_entity_events("invoice", uuid.uuid4(), ws)
        args = svc._repo.list_by_entity.call_args[0]
        assert args[2] == ws

    @pytest.mark.asyncio
    async def test_no_redis_cache(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        r = _redis()
        with _patch(redis=r):
            await svc.list_entity_events("invoice", uuid.uuid4(), _WS)
        r.get.assert_not_called()
        r.set.assert_not_called()


# ── TestListUserEvents ────────────────────────────────────────────────────────

class TestListUserEvents:
    @pytest.mark.asyncio
    async def test_returns_list_for_user(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_user_events(uuid.uuid4(), _WS)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_for_unknown_user(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_user_events(uuid.uuid4(), _WS)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_audit_log_out_list(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_user_events(uuid.uuid4(), _WS)
        assert all(isinstance(r, AuditLogOut) for r in result)

    @pytest.mark.asyncio
    async def test_repo_called_with_user_id(self):
        svc, _ = _make_svc()
        user_id = uuid.uuid4()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            await svc.list_user_events(user_id, _WS)
        svc._repo.list_by_user.assert_called_once_with(user_id, _WS)

    @pytest.mark.asyncio
    async def test_repo_called_with_workspace_id(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            await svc.list_user_events(uuid.uuid4(), _WS)
        args = svc._repo.list_by_user.call_args[0]
        assert args[1] == _WS

    @pytest.mark.asyncio
    async def test_user_id_preserved(self):
        svc, _ = _make_svc()
        user_id = uuid.uuid4()
        svc._repo.list_by_user = AsyncMock(return_value=[_make_orm_log(user_id=user_id)])
        with _patch():
            result = await svc.list_user_events(user_id, _WS)
        assert result[0].user_id == user_id

    @pytest.mark.asyncio
    async def test_multiple_events_returned(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[_make_orm_log(), _make_orm_log()])
        with _patch():
            result = await svc.list_user_events(uuid.uuid4(), _WS)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_cache_used(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        r = _redis()
        with _patch(redis=r):
            await svc.list_user_events(uuid.uuid4(), _WS)
        r.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_scoped(self):
        svc, _ = _make_svc()
        ws = uuid.uuid4()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            await svc.list_user_events(uuid.uuid4(), ws)
        args = svc._repo.list_by_user.call_args[0]
        assert args[1] == ws

    @pytest.mark.asyncio
    async def test_result_is_list_type(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_user_events(uuid.uuid4(), _WS)
        assert isinstance(result, list)


# ── TestListModuleEvents ──────────────────────────────────────────────────────

class TestListModuleEvents:
    @pytest.mark.asyncio
    async def test_returns_list_for_module(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_module_events("billing", _WS)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_for_unknown_module(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_module_events("nonexistent", _WS)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_audit_log_out_list(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[_make_orm_log()])
        with _patch():
            result = await svc.list_module_events("billing", _WS)
        assert all(isinstance(r, AuditLogOut) for r in result)

    @pytest.mark.asyncio
    async def test_repo_called_with_module(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            await svc.list_module_events("customers", _WS)
        args = svc._repo.list_by_module.call_args[0]
        assert args[0] == "customers"

    @pytest.mark.asyncio
    async def test_repo_called_with_workspace_id(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            await svc.list_module_events("billing", _WS)
        svc._repo.list_by_module.assert_called_once_with("billing", _WS)

    @pytest.mark.asyncio
    async def test_module_name_preserved(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[_make_orm_log(module="training")])
        with _patch():
            result = await svc.list_module_events("training", _WS)
        assert result[0].module == "training"

    @pytest.mark.asyncio
    async def test_multiple_events_returned(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[_make_orm_log(), _make_orm_log()])
        with _patch():
            result = await svc.list_module_events("billing", _WS)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_cache_used(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        r = _redis()
        with _patch(redis=r):
            await svc.list_module_events("billing", _WS)
        r.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_workspace_scoped(self):
        svc, _ = _make_svc()
        ws = uuid.uuid4()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            await svc.list_module_events("billing", ws)
        args = svc._repo.list_by_module.call_args[0]
        assert args[1] == ws

    @pytest.mark.asyncio
    async def test_result_is_list_type(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            result = await svc.list_module_events("billing", _WS)
        assert isinstance(result, list)


# ── TestGetStatistics ─────────────────────────────────────────────────────────

class TestGetStatistics:
    def _make_stats(self, **kwargs):
        return AuditStatisticsOut(
            total_events=kwargs.get("total_events", 50),
            by_severity=kwargs.get("by_severity", {"info": 45, "warning": 5}),
            by_module=kwargs.get("by_module", {"billing": 30, "customers": 20}),
            by_action=kwargs.get("by_action", {"invoice.created": 15}),
            period_days=kwargs.get("period_days", 30),
        )

    @pytest.mark.asyncio
    async def test_cache_hit_returns_stats(self):
        svc, _ = _make_svc()
        stats = self._make_stats()
        r = _redis(get_val=stats.model_dump_json())
        with _patch(redis=r):
            result = await svc.get_statistics(_WS)
        svc._repo.get_statistics.assert_not_called()
        assert result.total_events == 50

    @pytest.mark.asyncio
    async def test_cache_miss_hits_db(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        with _patch():
            result = await svc.get_statistics(_WS)
        svc._repo.get_statistics.assert_called_once()
        assert isinstance(result, AuditStatisticsOut)

    @pytest.mark.asyncio
    async def test_cache_set_on_miss(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        r = _redis()
        with _patch(redis=r):
            await svc.get_statistics(_WS)
        r.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_correct_ttl(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        r = _redis()
        with _patch(redis=r):
            await svc.get_statistics(_WS)
        _, kwargs = r.set.call_args
        assert kwargs["ex"] == 300

    @pytest.mark.asyncio
    async def test_default_period_is_30(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        with _patch():
            await svc.get_statistics(_WS)
        _, kwargs = svc._repo.get_statistics.call_args
        assert kwargs["period_days"] == 30

    @pytest.mark.asyncio
    async def test_custom_period_days_passed(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats(period_days=7))
        with _patch():
            await svc.get_statistics(_WS, period_days=7)
        _, kwargs = svc._repo.get_statistics.call_args
        assert kwargs["period_days"] == 7

    @pytest.mark.asyncio
    async def test_redis_failure_falls_through(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        with _patch(redis=_redis(fail=True)):
            result = await svc.get_statistics(_WS)
        svc._repo.get_statistics.assert_called_once()
        assert isinstance(result, AuditStatisticsOut)

    @pytest.mark.asyncio
    async def test_redis_set_failure_returns_result(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        r = MagicMock()
        r.get = AsyncMock(return_value=None)
        r.set = AsyncMock(side_effect=Exception("timeout"))
        with _patch(redis=r):
            result = await svc.get_statistics(_WS)
        assert isinstance(result, AuditStatisticsOut)

    @pytest.mark.asyncio
    async def test_returns_audit_statistics_out(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        with _patch():
            result = await svc.get_statistics(_WS)
        assert isinstance(result, AuditStatisticsOut)

    @pytest.mark.asyncio
    async def test_total_events_positive(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats(total_events=100))
        with _patch():
            result = await svc.get_statistics(_WS)
        assert result.total_events == 100

    @pytest.mark.asyncio
    async def test_by_severity_dict(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(
            return_value=self._make_stats(by_severity={"info": 10, "critical": 2})
        )
        with _patch():
            result = await svc.get_statistics(_WS)
        assert isinstance(result.by_severity, dict)
        assert result.by_severity["critical"] == 2

    @pytest.mark.asyncio
    async def test_by_module_dict(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(
            return_value=self._make_stats(by_module={"billing": 80, "workflows": 20})
        )
        with _patch():
            result = await svc.get_statistics(_WS)
        assert result.by_module["billing"] == 80

    @pytest.mark.asyncio
    async def test_by_action_dict(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(
            return_value=self._make_stats(by_action={"invoice.issued": 30})
        )
        with _patch():
            result = await svc.get_statistics(_WS)
        assert result.by_action["invoice.issued"] == 30

    @pytest.mark.asyncio
    async def test_period_days_in_result(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats(period_days=14))
        with _patch():
            result = await svc.get_statistics(_WS, period_days=14)
        assert result.period_days == 14

    @pytest.mark.asyncio
    async def test_stats_key_format(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(return_value=self._make_stats())
        r = _redis()
        with _patch(redis=r):
            await svc.get_statistics(_WS)
        set_key = r.set.call_args[0][0]
        assert "statistics" in set_key
        assert str(_ORG) in set_key


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_log_event_uses_context_org_not_param(self):
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(ctx=_ctx(org=org_a)):
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.tenant_id == org_a

    @pytest.mark.asyncio
    async def test_log_event_different_orgs_isolated(self):
        svc_a, _ = _make_svc()
        svc_b, _ = _make_svc()
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        svc_a._repo.create = AsyncMock(return_value=_make_orm_log())
        svc_b._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(ctx=_ctx(org=org_a)):
            await svc_a.log_event(req)
        with _patch(ctx=_ctx(org=org_b)):
            await svc_b.log_event(req)
        created_a = svc_a._repo.create.call_args[0][0]
        created_b = svc_b._repo.create.call_args[0][0]
        assert created_a.tenant_id != created_b.tenant_id

    @pytest.mark.asyncio
    async def test_get_event_key_uses_org_id(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        log_id = uuid.uuid4()
        svc._repo.find_by_id = AsyncMock(return_value=_make_orm_log(id=log_id))
        r = _redis()
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.get_event(log_id)
        get_key = r.get.call_args[0][0]
        assert str(org) in get_key

    @pytest.mark.asyncio
    async def test_list_events_key_uses_org_id(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        r = _redis()
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.list_events(AuditLogFilters(workspace_id=_WS))
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_stats_key_uses_org_id(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        svc._repo.get_statistics = AsyncMock(
            return_value=AuditStatisticsOut(
                total_events=0, by_severity={}, by_module={}, by_action={}, period_days=30
            )
        )
        r = _redis()
        with _patch(ctx=_ctx(org=org), redis=r):
            await svc.get_statistics(_WS)
        set_key = r.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_log_event_tenant_id_from_context(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(ctx=_ctx(org=org)):
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.tenant_id == org

    @pytest.mark.asyncio
    async def test_list_events_repo_called_with_workspace(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(AuditLogFilters(workspace_id=_WS))
        args = svc._repo.count.call_args[0]
        assert args[0] == _WS

    @pytest.mark.asyncio
    async def test_entity_events_repo_called_with_workspace(self):
        svc, _ = _make_svc()
        svc._repo.list_by_entity = AsyncMock(return_value=[])
        ws = uuid.uuid4()
        with _patch():
            await svc.list_entity_events("invoice", uuid.uuid4(), ws)
        args = svc._repo.list_by_entity.call_args[0]
        assert args[2] == ws

    @pytest.mark.asyncio
    async def test_user_events_repo_called_with_workspace(self):
        svc, _ = _make_svc()
        svc._repo.list_by_user = AsyncMock(return_value=[])
        with _patch():
            await svc.list_user_events(uuid.uuid4(), _WS)
        args = svc._repo.list_by_user.call_args[0]
        assert args[1] == _WS

    @pytest.mark.asyncio
    async def test_module_events_repo_called_with_workspace(self):
        svc, _ = _make_svc()
        svc._repo.list_by_module = AsyncMock(return_value=[])
        with _patch():
            await svc.list_module_events("billing", _WS)
        args = svc._repo.list_by_module.call_args[0]
        assert args[1] == _WS

    @pytest.mark.asyncio
    async def test_stats_repo_called_with_workspace(self):
        svc, _ = _make_svc()
        svc._repo.get_statistics = AsyncMock(
            return_value=AuditStatisticsOut(
                total_events=0, by_severity={}, by_module={}, by_action={}, period_days=30
            )
        )
        with _patch():
            await svc.get_statistics(_WS)
        args = svc._repo.get_statistics.call_args[0]
        assert args[0] == _WS

    @pytest.mark.asyncio
    async def test_tenant_id_not_in_schema_out(self):
        out = _make_log_out()
        assert not hasattr(out, "tenant_id")

    @pytest.mark.asyncio
    async def test_two_tenants_different_keys(self):
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        key_a = _audit_list_key(org_a, _WS)
        key_b = _audit_list_key(org_b, _WS)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_org_id_from_context_var(self):
        svc, _ = _make_svc()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        org = uuid.uuid4()
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(ctx=_ctx(org=org)):
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.tenant_id == org

    @pytest.mark.asyncio
    async def test_log_event_calls_repo_with_context_org(self):
        svc, _ = _make_svc()
        org = uuid.uuid4()
        svc._repo.create = AsyncMock(return_value=_make_orm_log())
        req = AuditLogCreate(workspace_id=_WS, action="x", module="y")
        with _patch(ctx=_ctx(org=org)):
            await svc.log_event(req)
        created = svc._repo.create.call_args[0][0]
        assert created.tenant_id == org


# ── TestCursorHelpers ─────────────────────────────────────────────────────────

class TestCursorHelpers:
    def test_encode_returns_string(self):
        token = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        assert isinstance(token, str)

    def test_decode_roundtrip_created_at(self):
        ts = datetime.now(UTC)
        token = _encode_audit_cursor(ts, uuid.uuid4())
        decoded_ts, _ = _decode_audit_cursor(token)
        assert abs((decoded_ts - ts).total_seconds()) < 0.001

    def test_decode_roundtrip_id(self):
        log_id = uuid.uuid4()
        token = _encode_audit_cursor(datetime.now(UTC), log_id)
        _, decoded_id = _decode_audit_cursor(token)
        assert decoded_id == log_id

    def test_encode_is_url_safe(self):
        token = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        # base64 url-safe uses - and _ instead of + and /
        assert "+" not in token
        assert "/" not in token

    def test_encode_different_timestamps_different_results(self):
        t1 = datetime.now(UTC)
        t2 = t1 + timedelta(seconds=1)
        rid = uuid.uuid4()
        assert _encode_audit_cursor(t1, rid) != _encode_audit_cursor(t2, rid)

    def test_encode_different_ids_different_results(self):
        ts = datetime.now(UTC)
        assert _encode_audit_cursor(ts, uuid.uuid4()) != _encode_audit_cursor(ts, uuid.uuid4())

    def test_decode_handles_utc_timezone(self):
        ts = datetime.now(UTC)
        token = _encode_audit_cursor(ts, uuid.uuid4())
        decoded_ts, _ = _decode_audit_cursor(token)
        assert decoded_ts.tzinfo is not None

    def test_encode_decode_uuid(self):
        log_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        token = _encode_audit_cursor(datetime.now(UTC), log_id)
        _, decoded_id = _decode_audit_cursor(token)
        assert decoded_id == log_id

    def test_cursor_is_base64(self):
        import base64
        token = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        assert "|" in decoded

    def test_cursor_not_plaintext(self):
        ts = datetime.now(UTC)
        log_id = uuid.uuid4()
        token = _encode_audit_cursor(ts, log_id)
        assert str(log_id) not in token


# ── TestAppendOnlyGuarantees ──────────────────────────────────────────────────

class TestAppendOnlyGuarantees:
    def test_repo_has_no_update_method(self):
        assert not hasattr(AuditLogRepo, "update")

    def test_repo_has_no_delete_method(self):
        assert not hasattr(AuditLogRepo, "delete")

    def test_repo_has_no_update_fields_method(self):
        assert not hasattr(AuditLogRepo, "update_fields")

    def test_repo_has_no_remove_method(self):
        assert not hasattr(AuditLogRepo, "remove")

    def test_repo_has_no_bulk_delete_method(self):
        assert not hasattr(AuditLogRepo, "bulk_delete")

    def test_service_has_no_delete_event_method(self):
        assert not hasattr(AuditLogService, "delete_event")

    def test_service_has_no_update_event_method(self):
        assert not hasattr(AuditLogService, "update_event")

    def test_service_has_no_remove_event_method(self):
        assert not hasattr(AuditLogService, "remove_event")

    def test_create_is_the_only_write_method(self):
        write_methods = [m for m in dir(AuditLogRepo) if not m.startswith("_") and "create" in m.lower() or not m.startswith("_") and any(w in m.lower() for w in ["update", "delete", "remove", "patch"])]
        write_mutations = [m for m in dir(AuditLogRepo) if not m.startswith("_") and any(w in m.lower() for w in ["update", "delete", "remove", "patch"])]
        assert len(write_mutations) == 0

    def test_repo_write_methods_count(self):
        all_public = [m for m in dir(AuditLogRepo) if not m.startswith("_") and callable(getattr(AuditLogRepo, m))]
        write_words = {"update", "delete", "remove", "patch", "put"}
        mutating = [m for m in all_public if any(w in m.lower() for w in write_words)]
        assert mutating == [], f"Unexpected mutation methods: {mutating}"


# ── TestFilterCombinations ────────────────────────────────────────────────────

class TestFilterCombinations:
    def _default(self, **kwargs):
        return AuditLogFilters(workspace_id=_WS, **kwargs)

    def _is_default_filter(self, f: AuditLogFilters) -> bool:
        return (
            f.module is None
            and f.severity is None
            and f.user_id is None
            and f.entity_type is None
            and f.entity_id is None
            and f.action is None
            and f.date_from is None
            and f.date_to is None
            and f.search is None
            and f.cursor is None
        )

    def test_no_filters_is_default(self):
        assert self._is_default_filter(self._default())

    def test_module_only_not_default(self):
        assert not self._is_default_filter(self._default(module="billing"))

    def test_severity_only_not_default(self):
        assert not self._is_default_filter(self._default(severity="critical"))

    def test_date_from_only_not_default(self):
        assert not self._is_default_filter(self._default(date_from=datetime.now(UTC)))

    def test_date_to_only_not_default(self):
        assert not self._is_default_filter(self._default(date_to=datetime.now(UTC)))

    def test_user_id_only_not_default(self):
        assert not self._is_default_filter(self._default(user_id=uuid.uuid4()))

    def test_entity_type_only_not_default(self):
        assert not self._is_default_filter(self._default(entity_type="invoice"))

    def test_cursor_only_not_default(self):
        cursor = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        assert not self._is_default_filter(self._default(cursor=cursor))

    def test_search_only_not_default(self):
        assert not self._is_default_filter(self._default(search="payment"))

    def test_all_filters_not_default(self):
        f = self._default(
            module="billing",
            severity="warning",
            user_id=uuid.uuid4(),
            entity_type="invoice",
            action="invoice.issued",
        )
        assert not self._is_default_filter(f)

    def test_module_and_severity_not_default(self):
        f = self._default(module="billing", severity="info")
        assert not self._is_default_filter(f)

    def test_date_range_not_default(self):
        now = datetime.now(UTC)
        f = self._default(date_from=now, date_to=now)
        assert not self._is_default_filter(f)

    def test_entity_filter_not_default(self):
        f = self._default(entity_type="customer", entity_id=uuid.uuid4())
        assert not self._is_default_filter(f)

    def test_user_and_module_not_default(self):
        f = self._default(user_id=uuid.uuid4(), module="workflows")
        assert not self._is_default_filter(f)

    @pytest.mark.asyncio
    async def test_filters_passed_to_count(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._default(severity="warning", module="billing"))
        kw = svc._repo.count.call_args[1]
        assert kw["severity"] == "warning"
        assert kw["module"] == "billing"

    @pytest.mark.asyncio
    async def test_filters_passed_to_list_page(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._default(action="payment.confirmed"))
        kw = svc._repo.list_page.call_args[1]
        assert kw["action"] == "payment.confirmed"

    @pytest.mark.asyncio
    async def test_cursor_filter_passed(self):
        svc, _ = _make_svc()
        cursor = _encode_audit_cursor(datetime.now(UTC), uuid.uuid4())
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._default(cursor=cursor))
        kw = svc._repo.list_page.call_args[1]
        assert kw["cursor"] == cursor

    @pytest.mark.asyncio
    async def test_limit_filter_passed(self):
        svc, _ = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        with _patch():
            await svc.list_events(self._default(limit=100))
        kw = svc._repo.list_page.call_args[1]
        assert kw["limit"] == 100
