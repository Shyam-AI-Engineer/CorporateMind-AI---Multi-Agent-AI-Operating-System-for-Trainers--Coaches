"""Unit tests for ObservabilityService — Sprint 57 (file 1 of 2).

Covers: schemas, constants, cache health, database health, API health,
and recent errors.  No database, no Redis — all I/O is mocked.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.observability.schemas import (
    ApiHealthOut,
    CacheHealthOut,
    DatabaseHealthOut,
    ModuleHealthItem,
    ModuleHealthOut,
    PlatformSummaryOut,
    RecentErrorItem,
    RecentErrorsOut,
)
from corpmind.modules.observability.service import (
    _CACHE_TTL,
    _KNOWN_TTLS,
    _MODULE_CONFIGS,
    _modules_cache_key,
    _summary_cache_key,
    ObservabilityService,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────

ORG_ID = uuid.uuid4()
WS_ID = uuid.uuid4()

_PATCH_CTX = "corpmind.modules.observability.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.observability.service.get_redis"


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(org_id=ORG_ID, workspace_id=WS_ID, user_id=uuid.uuid4())


def _session() -> AsyncMock:
    return AsyncMock()


def _svc(session: AsyncMock | None = None) -> ObservabilityService:
    return ObservabilityService(session or _session())


# ── Schema: PlatformSummaryOut ─────────────────────────────────────────────────


class TestPlatformSummaryOutSchema:
    def test_fields_present(self):
        fields = PlatformSummaryOut.model_fields
        assert "overall_health_score" in fields
        assert "api_health" in fields
        assert "database_health" in fields
        assert "cache_health" in fields
        assert "storage_health" in fields
        assert "active_modules" in fields
        assert "healthy_modules" in fields
        assert "warning_modules" in fields
        assert "checked_at" in fields

    def test_instantiation(self):
        obj = PlatformSummaryOut(
            overall_health_score=1.0,
            api_health="healthy",
            database_health="healthy",
            cache_health="healthy",
            storage_health="healthy",
            active_modules=12,
            healthy_modules=12,
            warning_modules=0,
            checked_at=datetime.now(UTC),
        )
        assert obj.overall_health_score == 1.0
        assert obj.active_modules == 12
        assert obj.warning_modules == 0

    def test_from_attributes(self):
        assert PlatformSummaryOut.model_config.get("from_attributes") is True

    def test_health_score_range(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PlatformSummaryOut(
                overall_health_score=1.5,
                api_health="healthy",
                database_health="healthy",
                cache_health="healthy",
                storage_health="healthy",
                active_modules=12,
                healthy_modules=12,
                warning_modules=0,
                checked_at=datetime.now(UTC),
            )

    def test_health_score_zero_valid(self):
        obj = PlatformSummaryOut(
            overall_health_score=0.0,
            api_health="down",
            database_health="down",
            cache_health="down",
            storage_health="down",
            active_modules=0,
            healthy_modules=0,
            warning_modules=0,
            checked_at=datetime.now(UTC),
        )
        assert obj.overall_health_score == 0.0


# ── Schema: CacheHealthOut ─────────────────────────────────────────────────────


class TestCacheHealthOutSchema:
    def test_fields_present(self):
        fields = CacheHealthOut.model_fields
        assert "redis_available" in fields
        assert "estimated_hit_ratio" in fields
        assert "estimated_miss_ratio" in fields
        assert "ttl_configuration" in fields
        assert "checked_at" in fields

    def test_instantiation(self):
        obj = CacheHealthOut(
            redis_available=True,
            estimated_hit_ratio=0.75,
            estimated_miss_ratio=0.25,
            ttl_configuration={"summary": 300},
            checked_at=datetime.now(UTC),
        )
        assert obj.redis_available is True
        assert obj.estimated_hit_ratio == 0.75

    def test_hit_ratio_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CacheHealthOut(
                redis_available=True,
                estimated_hit_ratio=1.5,
                estimated_miss_ratio=0.0,
                ttl_configuration={},
                checked_at=datetime.now(UTC),
            )


# ── Schema: DatabaseHealthOut ──────────────────────────────────────────────────


class TestDatabaseHealthOutSchema:
    def test_fields_present(self):
        fields = DatabaseHealthOut.model_fields
        assert "connection_ok" in fields
        assert "estimated_latency_ms" in fields
        assert "table_count" in fields
        assert "migration_version" in fields
        assert "checked_at" in fields

    def test_instantiation(self):
        obj = DatabaseHealthOut(
            connection_ok=True,
            estimated_latency_ms=2.5,
            table_count=40,
            migration_version="abc123",
            checked_at=datetime.now(UTC),
        )
        assert obj.connection_ok is True
        assert obj.table_count == 40


# ── Schema: ApiHealthOut ───────────────────────────────────────────────────────


class TestApiHealthOutSchema:
    def test_fields_present(self):
        fields = ApiHealthOut.model_fields
        assert "registered_routes" in fields
        assert "average_response_bucket" in fields
        assert "error_rate" in fields
        assert "checked_at" in fields

    def test_instantiation(self):
        obj = ApiHealthOut(
            registered_routes=150,
            average_response_bucket="fast",
            error_rate=0.01,
            checked_at=datetime.now(UTC),
        )
        assert obj.registered_routes == 150
        assert obj.average_response_bucket == "fast"

    def test_error_rate_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ApiHealthOut(
                registered_routes=50,
                average_response_bucket="fast",
                error_rate=2.0,
                checked_at=datetime.now(UTC),
            )


# ── Schema: ModuleHealthItem ───────────────────────────────────────────────────


class TestModuleHealthItemSchema:
    def test_fields_present(self):
        fields = ModuleHealthItem.model_fields
        assert "module" in fields
        assert "healthy" in fields
        assert "enabled" in fields
        assert "record_count" in fields
        assert "cache_enabled" in fields
        assert "checked_at" in fields

    def test_instantiation(self):
        obj = ModuleHealthItem(
            module="customers",
            healthy=True,
            enabled=True,
            record_count=500,
            cache_enabled=True,
            checked_at=datetime.now(UTC),
        )
        assert obj.module == "customers"
        assert obj.record_count == 500


# ── Schema: ModuleHealthOut ────────────────────────────────────────────────────


class TestModuleHealthOutSchema:
    def test_fields_present(self):
        fields = ModuleHealthOut.model_fields
        assert "modules" in fields
        assert "total" in fields
        assert "healthy" in fields
        assert "warning" in fields

    def test_instantiation(self):
        item = ModuleHealthItem(
            module="billing",
            healthy=True,
            enabled=True,
            record_count=10,
            cache_enabled=True,
            checked_at=datetime.now(UTC),
        )
        obj = ModuleHealthOut(modules=[item], total=1, healthy=1, warning=0)
        assert obj.total == 1
        assert len(obj.modules) == 1


# ── Schema: RecentErrorItem ────────────────────────────────────────────────────


class TestRecentErrorItemSchema:
    def test_fields_present(self):
        fields = RecentErrorItem.model_fields
        assert "source" in fields
        assert "message" in fields
        assert "severity" in fields
        assert "occurred_at" in fields

    def test_instantiation(self):
        obj = RecentErrorItem(
            source="billing",
            message="invoice_create_failed",
            severity="critical",
            occurred_at=datetime.now(UTC),
        )
        assert obj.source == "billing"
        assert obj.severity == "critical"


# ── Schema: RecentErrorsOut ────────────────────────────────────────────────────


class TestRecentErrorsOutSchema:
    def test_fields_present(self):
        fields = RecentErrorsOut.model_fields
        assert "errors" in fields
        assert "total" in fields
        assert "checked_at" in fields

    def test_empty_errors(self):
        obj = RecentErrorsOut(errors=[], total=0, checked_at=datetime.now(UTC))
        assert obj.total == 0
        assert obj.errors == []


# ── Constants ──────────────────────────────────────────────────────────────────


class TestConstants:
    def test_cache_ttl_is_300(self):
        assert _CACHE_TTL == 300

    def test_known_ttls_is_dict(self):
        assert isinstance(_KNOWN_TTLS, dict)

    def test_known_ttls_has_summary(self):
        assert "observability_summary" in _KNOWN_TTLS
        assert _KNOWN_TTLS["observability_summary"] == 300

    def test_known_ttls_has_modules(self):
        assert "observability_modules" in _KNOWN_TTLS

    def test_known_ttls_all_positive(self):
        for key, val in _KNOWN_TTLS.items():
            assert val > 0, f"TTL for {key!r} must be positive"

    def test_module_configs_has_12(self):
        assert len(_MODULE_CONFIGS) == 12

    def test_module_configs_contains_required(self):
        required = [
            "customers", "training", "billing", "payments",
            "workflows", "approvals", "notifications", "audit",
            "admin", "integrations", "reporting", "executive_dashboard",
        ]
        for mod in required:
            assert mod in _MODULE_CONFIGS, f"Missing module config: {mod}"

    def test_module_configs_executive_has_no_table(self):
        table, _ = _MODULE_CONFIGS["executive_dashboard"]
        assert table is None

    def test_module_configs_customers_has_table(self):
        table, _ = _MODULE_CONFIGS["customers"]
        assert table == "customers"

    def test_module_configs_training_has_table(self):
        table, _ = _MODULE_CONFIGS["training"]
        assert table == "training_engagements"

    def test_module_configs_billing_has_table(self):
        table, _ = _MODULE_CONFIGS["billing"]
        assert table == "customer_invoices"

    def test_module_configs_payments_has_table(self):
        table, _ = _MODULE_CONFIGS["payments"]
        assert table == "invoice_payments"

    def test_module_configs_workflows_has_table(self):
        table, _ = _MODULE_CONFIGS["workflows"]
        assert table == "workflow_runs"

    def test_module_configs_approvals_has_table(self):
        table, _ = _MODULE_CONFIGS["approvals"]
        assert table == "approval_requests"

    def test_module_configs_notifications_has_table(self):
        table, _ = _MODULE_CONFIGS["notifications"]
        assert table == "notifications"

    def test_module_configs_audit_has_table(self):
        table, _ = _MODULE_CONFIGS["audit"]
        assert table == "audit_logs"

    def test_module_configs_admin_has_table(self):
        table, _ = _MODULE_CONFIGS["admin"]
        assert table == "organization_settings"

    def test_module_configs_integrations_has_table(self):
        table, _ = _MODULE_CONFIGS["integrations"]
        assert table == "api_keys"

    def test_module_configs_reporting_has_table(self):
        table, _ = _MODULE_CONFIGS["reporting"]
        assert table == "report_exports"

    def test_module_configs_values_are_tuples(self):
        for name, val in _MODULE_CONFIGS.items():
            assert isinstance(val, tuple), f"{name} config must be a tuple"
            assert len(val) == 2, f"{name} config tuple must have 2 elements"


# ── Cache key helpers ──────────────────────────────────────────────────────────


class TestCacheKeyHelpers:
    def test_summary_cache_key_format(self):
        key = _summary_cache_key(ORG_ID)
        assert str(ORG_ID) in key
        assert "observability" in key
        assert "summary" in key

    def test_modules_cache_key_format(self):
        key = _modules_cache_key(ORG_ID)
        assert str(ORG_ID) in key
        assert "observability" in key
        assert "modules" in key

    def test_summary_key_differs_from_modules_key(self):
        assert _summary_cache_key(ORG_ID) != _modules_cache_key(ORG_ID)

    def test_different_orgs_different_keys(self):
        other_org = uuid.uuid4()
        assert _summary_cache_key(ORG_ID) != _summary_cache_key(other_org)


# ── get_cache_health ───────────────────────────────────────────────────────────


class TestGetCacheHealth:
    @pytest.mark.asyncio
    async def test_redis_available_with_hits(self):
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={"keyspace_hits": "800", "keyspace_misses": "200"})
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.redis_available is True
        assert result.estimated_hit_ratio == pytest.approx(0.8, abs=0.001)
        assert result.estimated_miss_ratio == pytest.approx(0.2, abs=0.001)

    @pytest.mark.asyncio
    async def test_redis_available_zero_total(self):
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={"keyspace_hits": "0", "keyspace_misses": "0"})
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.redis_available is True
        assert result.estimated_hit_ratio == 0.0
        assert result.estimated_miss_ratio == 0.0

    @pytest.mark.asyncio
    async def test_redis_unavailable_on_ping_exception(self):
        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.redis_available is False
        assert result.estimated_hit_ratio == 0.0
        assert result.estimated_miss_ratio == 0.0

    @pytest.mark.asyncio
    async def test_redis_unavailable_on_info_exception(self):
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(side_effect=RuntimeError("timeout"))
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.redis_available is False

    @pytest.mark.asyncio
    async def test_ttl_configuration_returned(self):
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={})
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.ttl_configuration == _KNOWN_TTLS

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self):
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={})
        with patch(_PATCH_REDIS, return_value=redis):
            result = await _svc().get_cache_health()
        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_redis_raises_gracefully(self):
        with patch(_PATCH_REDIS, side_effect=RuntimeError("not initialized")):
            result = await _svc().get_cache_health()
        assert result.redis_available is False


# ── get_database_health ────────────────────────────────────────────────────────


class TestGetDatabaseHealth:
    def _mock_session(self, latency_ok: bool = True, table_count: int = 42, version: str = "abc123") -> AsyncMock:
        session = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            call_count[0] += 1
            if not latency_ok and call_count[0] == 1:
                raise Exception("connection refused")
            mock_result = MagicMock()
            if call_count[0] == 2:
                mock_result.scalar_one.return_value = table_count
            else:
                mock_result.scalar_one_or_none.return_value = version
            return mock_result

        session.execute = mock_execute
        return session

    @pytest.mark.asyncio
    async def test_connection_ok(self):
        session = self._mock_session()
        result = await ObservabilityService(session).get_database_health()
        assert result.connection_ok is True

    @pytest.mark.asyncio
    async def test_latency_ms_non_negative(self):
        session = self._mock_session()
        result = await ObservabilityService(session).get_database_health()
        assert result.estimated_latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_table_count_returned(self):
        session = self._mock_session(table_count=55)
        result = await ObservabilityService(session).get_database_health()
        assert result.table_count == 55

    @pytest.mark.asyncio
    async def test_migration_version_returned(self):
        session = self._mock_session(version="deadbeef")
        result = await ObservabilityService(session).get_database_health()
        assert result.migration_version == "deadbeef"

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("connection refused"))
        result = await ObservabilityService(session).get_database_health()
        assert result.connection_ok is False
        assert result.estimated_latency_ms == -1.0
        assert result.table_count == 0
        assert result.migration_version == "unknown"

    @pytest.mark.asyncio
    async def test_checked_at_present(self):
        session = self._mock_session()
        result = await ObservabilityService(session).get_database_health()
        assert result.checked_at is not None

    @pytest.mark.asyncio
    async def test_migration_version_fallback_when_table_missing(self):
        session = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                return mock_result  # SELECT 1 ok
            elif call_count[0] == 2:
                mock_result.scalar_one.return_value = 30
                return mock_result  # table count ok
            else:
                raise Exception("alembic_version does not exist")

        session.execute = mock_execute
        result = await ObservabilityService(session).get_database_health()
        assert result.connection_ok is True
        assert result.migration_version == "unknown"
        assert result.table_count == 30


# ── get_api_health ─────────────────────────────────────────────────────────────


class TestGetApiHealth:
    @pytest.mark.asyncio
    async def test_route_count_returned(self):
        session = AsyncMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=200)
        assert result.registered_routes == 200

    @pytest.mark.asyncio
    async def test_zero_audit_events_zero_error_rate(self):
        session = AsyncMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=10)
        assert result.error_rate == 0.0

    @pytest.mark.asyncio
    async def test_error_rate_computed(self):
        session = AsyncMock()
        mock_row = MagicMock()
        values = [5, 100]  # 5 critical out of 100 total
        mock_row.__getitem__ = lambda self, i: values[i]
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=50)
        assert result.error_rate == pytest.approx(0.05, abs=0.0001)

    @pytest.mark.asyncio
    async def test_exception_in_audit_query_graceful(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("query failed"))
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=100)
        assert result.error_rate == 0.0
        assert result.registered_routes == 100

    @pytest.mark.asyncio
    async def test_average_response_bucket_is_fast(self):
        session = AsyncMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=1)
        assert result.average_response_bucket == "fast"

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self):
        session = AsyncMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: 0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_api_health(route_count=5)
        assert result.checked_at.tzinfo is not None


# ── get_recent_errors ──────────────────────────────────────────────────────────


class TestGetRecentErrors:
    @pytest.mark.asyncio
    async def test_empty_result(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.total == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_errors_mapped_correctly(self):
        session = AsyncMock()
        now = datetime.now(UTC)
        fake_row = ("invoice_create_failed", "billing", "critical", now)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [fake_row]
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.total == 1
        assert result.errors[0].source == "billing"
        assert result.errors[0].message == "invoice_create_failed"
        assert result.errors[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_multiple_errors(self):
        session = AsyncMock()
        now = datetime.now(UTC)
        rows = [
            ("action_a", "module_a", "warning", now),
            ("action_b", "module_b", "critical", now),
            ("action_c", "module_c", "warning", now),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.total == 3
        assert len(result.errors) == 3

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("DB error"))
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.total == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_checked_at_set(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.checked_at is not None

    @pytest.mark.asyncio
    async def test_tenant_id_used_in_query(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            await ObservabilityService(session).get_recent_errors()
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert "tenant_id" in params
        assert params["tenant_id"] == str(ORG_ID)
