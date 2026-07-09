"""Unit tests for ObservabilityService — Sprint 57 (file 2 of 2).

Covers: get_platform_summary (cache hit, cache miss, health scoring,
db/cache down scenarios) and get_module_health (cache hit, all modules,
executive_dashboard special case, failure in one module, score aggregation).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.observability.schemas import (
    CacheHealthOut,
    DatabaseHealthOut,
    ModuleHealthItem,
    ModuleHealthOut,
    PlatformSummaryOut,
)
from corpmind.modules.observability.service import (
    _CACHE_TTL,
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


def _make_cache_health(available: bool = True) -> CacheHealthOut:
    return CacheHealthOut(
        redis_available=available,
        estimated_hit_ratio=0.7,
        estimated_miss_ratio=0.3,
        ttl_configuration={"summary": 300},
        checked_at=datetime.now(UTC),
    )


def _make_db_health(ok: bool = True) -> DatabaseHealthOut:
    return DatabaseHealthOut(
        connection_ok=ok,
        estimated_latency_ms=1.5,
        table_count=40,
        migration_version="abc123",
        checked_at=datetime.now(UTC),
    )


def _make_module_health(healthy: int = 12, warning: int = 0) -> ModuleHealthOut:
    items = [
        ModuleHealthItem(
            module=f"mod_{i}",
            healthy=(i < healthy),
            enabled=True,
            record_count=i * 10,
            cache_enabled=False,
            checked_at=datetime.now(UTC),
        )
        for i in range(healthy + warning)
    ]
    return ModuleHealthOut(
        modules=items,
        total=healthy + warning,
        healthy=healthy,
        warning=warning,
    )


# ── get_platform_summary — cache hit ──────────────────────────────────────────


class TestGetPlatformSummaryCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        cached_obj = PlatformSummaryOut(
            overall_health_score=0.95,
            api_health="healthy",
            database_health="healthy",
            cache_health="healthy",
            storage_health="healthy",
            active_modules=12,
            healthy_modules=12,
            warning_modules=0,
            checked_at=datetime.now(UTC),
        )
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=cached_obj.model_dump_json())
        session = AsyncMock()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_platform_summary()
        assert result.overall_health_score == pytest.approx(0.95)
        assert result.healthy_modules == 12
        # Session should not be called (cache hit)
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_checked(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={})
        redis.setex = AsyncMock()
        session = AsyncMock()

        svc = ObservabilityService(session)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health", AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health", AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health", AsyncMock(return_value=_make_module_health())):
            await svc.get_platform_summary()

        redis.get.assert_called_once_with(_summary_cache_key(ORG_ID))


# ── get_platform_summary — all healthy ────────────────────────────────────────


class TestGetPlatformSummaryAllHealthy:
    @pytest.mark.asyncio
    async def test_score_is_one_when_all_healthy(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=True))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=True))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(12, 0))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score == pytest.approx(1.0)
        assert result.database_health == "healthy"
        assert result.cache_health == "healthy"
        assert result.api_health == "healthy"
        assert result.storage_health == "healthy"

    @pytest.mark.asyncio
    async def test_active_modules_count(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(12, 0))):
            result = await svc.get_platform_summary()

        assert result.active_modules == 12
        assert result.healthy_modules == 12
        assert result.warning_modules == 0

    @pytest.mark.asyncio
    async def test_result_stored_in_cache(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health())):
            await svc.get_platform_summary()

        redis.setex.assert_called_once()
        cache_key, ttl, payload = redis.setex.call_args[0]
        assert cache_key == _summary_cache_key(ORG_ID)
        assert ttl == _CACHE_TTL
        assert "overall_health_score" in payload


# ── get_platform_summary — degraded scenarios ─────────────────────────────────


class TestGetPlatformSummaryDegraded:
    @pytest.mark.asyncio
    async def test_db_down_reduces_score(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=False))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=True))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health())):
            result = await svc.get_platform_summary()

        assert result.overall_health_score < 1.0
        assert result.database_health == "down"

    @pytest.mark.asyncio
    async def test_cache_down_reduces_score(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=True))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=False))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health())):
            result = await svc.get_platform_summary()

        assert result.overall_health_score < 1.0
        assert result.cache_health == "degraded"

    @pytest.mark.asyncio
    async def test_db_and_cache_down_score_floor(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=False))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=False))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(0, 12))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score >= 0.0

    @pytest.mark.asyncio
    async def test_module_warnings_reduce_score(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(10, 2))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score < 1.0

    @pytest.mark.asyncio
    async def test_redis_cache_write_failure_graceful(self):
        """Cache write failure must not raise — result is still returned."""
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(side_effect=Exception("write fail"))

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health())):
            result = await svc.get_platform_summary()

        assert isinstance(result, PlatformSummaryOut)

    @pytest.mark.asyncio
    async def test_redis_get_failure_falls_through_to_compute(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("timeout"))
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health())), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health())), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health())):
            result = await svc.get_platform_summary()

        assert isinstance(result, PlatformSummaryOut)


# ── get_module_health — cache hit ─────────────────────────────────────────────


class TestGetModuleHealthCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        now = datetime.now(UTC)
        module_items = [
            {
                "module": f"mod_{i}",
                "healthy": True,
                "enabled": True,
                "record_count": i * 5,
                "cache_enabled": False,
                "checked_at": now.isoformat(),
            }
            for i in range(12)
        ]
        cached_data = json.dumps({
            "modules": module_items,
            "total": 12,
            "healthy": 12,
            "warning": 0,
        })
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=cached_data)
        session = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        assert result.total == 12
        assert result.healthy == 12
        assert result.warning == 0
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_checked(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            await ObservabilityService(session).get_module_health()

        redis.get.assert_called_once_with(_modules_cache_key(ORG_ID))


# ── get_module_health — uncached ──────────────────────────────────────────────


class TestGetModuleHealthUncached:
    @pytest.mark.asyncio
    async def test_all_12_modules_returned(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        assert result.total == 12
        module_names = {item.module for item in result.modules}
        for expected in _MODULE_CONFIGS.keys():
            assert expected in module_names

    @pytest.mark.asyncio
    async def test_executive_dashboard_has_zero_count(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        ed_item = next(i for i in result.modules if i.module == "executive_dashboard")
        assert ed_item.record_count == 0
        assert ed_item.healthy is True
        assert ed_item.enabled is True

    @pytest.mark.asyncio
    async def test_modules_with_table_get_count(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 99
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        customers_item = next(i for i in result.modules if i.module == "customers")
        assert customers_item.record_count == 99

    @pytest.mark.asyncio
    async def test_failed_module_query_marks_unhealthy(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("table missing"))

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        # executive_dashboard never queries DB; all others should be unhealthy
        non_ed = [i for i in result.modules if i.module != "executive_dashboard"]
        assert all(not item.healthy for item in non_ed)

    @pytest.mark.asyncio
    async def test_healthy_warning_counts_sum_to_total(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        assert result.healthy + result.warning == result.total

    @pytest.mark.asyncio
    async def test_result_stored_in_cache(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            await ObservabilityService(session).get_module_health()

        redis.setex.assert_called_once()
        key, ttl, payload = redis.setex.call_args[0]
        assert key == _modules_cache_key(ORG_ID)
        assert ttl == _CACHE_TTL
        parsed = json.loads(payload)
        assert "modules" in parsed
        assert parsed["total"] == 12

    @pytest.mark.asyncio
    async def test_cache_write_failure_graceful(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(side_effect=Exception("write fail"))
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        assert isinstance(result, ModuleHealthOut)

    @pytest.mark.asyncio
    async def test_cache_enabled_flag_per_module(self):
        from corpmind.modules.observability.service import _MODULE_CONFIGS
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        for item in result.modules:
            _, expected_cache = _MODULE_CONFIGS[item.module]
            assert item.cache_enabled == expected_cache, (
                f"Module {item.module}: expected cache_enabled={expected_cache}"
            )

    @pytest.mark.asyncio
    async def test_all_modules_enabled(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_result)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(session).get_module_health()

        assert all(item.enabled for item in result.modules)

    @pytest.mark.asyncio
    async def test_tenant_id_in_count_queries(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        session = AsyncMock()

        captured_params: list[dict] = []

        async def mock_execute(stmt, params=None, *args, **kwargs):
            if params and "tenant_id" in params:
                captured_params.append(params)
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = 0
            return mock_result

        session.execute = mock_execute

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis):
            await ObservabilityService(session).get_module_health()

        # Should have run 11 queries with tenant_id (12 modules - 1 executive_dashboard)
        assert len(captured_params) == 11
        for p in captured_params:
            assert p["tenant_id"] == str(ORG_ID)


# ── Integration-style: platform summary health scoring ────────────────────────


class TestHealthScoring:
    """Verify the mathematical scoring rules in get_platform_summary."""

    @pytest.mark.asyncio
    async def test_score_decreases_by_0_4_when_db_down(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=False))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=True))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(12, 0))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score == pytest.approx(0.6, abs=0.001)

    @pytest.mark.asyncio
    async def test_score_decreases_by_0_2_when_cache_down(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=True))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=False))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(12, 0))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score == pytest.approx(0.8, abs=0.001)

    @pytest.mark.asyncio
    async def test_score_never_below_zero(self):
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=False))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=False))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(0, 12))):
            result = await svc.get_platform_summary()

        assert result.overall_health_score >= 0.0

    @pytest.mark.asyncio
    async def test_warning_cap_at_3(self):
        """Warning deduction should cap at 3 (0.3) even with more warning modules."""
        svc = ObservabilityService(AsyncMock())
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=redis), \
             patch.object(svc, "get_database_health",
                          AsyncMock(return_value=_make_db_health(ok=True))), \
             patch.object(svc, "get_cache_health",
                          AsyncMock(return_value=_make_cache_health(available=True))), \
             patch.object(svc, "get_module_health",
                          AsyncMock(return_value=_make_module_health(0, 12))):
            result = await svc.get_platform_summary()

        # Max deduction for warnings is 0.3 (3 * 0.1), so min score is 0.7 if only warnings
        assert result.overall_health_score >= 0.69


# ── Edge cases ─────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_service_constructor_stores_session(self):
        session = AsyncMock()
        svc = ObservabilityService(session)
        assert svc._session is session

    @pytest.mark.asyncio
    async def test_get_cache_health_missing_keyspace_stats(self):
        """info() may not have keyspace_hits if no cache activity yet."""
        redis = AsyncMock()
        redis.ping = AsyncMock()
        redis.info = AsyncMock(return_value={})  # no keyspace_hits/misses
        with patch(_PATCH_REDIS, return_value=redis):
            result = await ObservabilityService(AsyncMock()).get_cache_health()
        assert result.estimated_hit_ratio == 0.0
        assert result.estimated_miss_ratio == 0.0

    @pytest.mark.asyncio
    async def test_get_recent_errors_source_is_module_column(self):
        """source maps to audit_logs.module (row[1]), not action (row[0])."""
        session = AsyncMock()
        now = datetime.now(UTC)
        fake_row = ("payment_failed", "payments", "critical", now)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [fake_row]
        session.execute = AsyncMock(return_value=mock_result)
        with patch(_PATCH_CTX, return_value=_ctx()):
            result = await ObservabilityService(session).get_recent_errors()
        assert result.errors[0].source == "payments"
        assert result.errors[0].message == "payment_failed"

    @pytest.mark.asyncio
    async def test_all_methods_return_checked_at(self):
        """Every schema response has a checked_at timestamp."""
        from corpmind.modules.observability.schemas import (
            ApiHealthOut, CacheHealthOut, DatabaseHealthOut,
            ModuleHealthOut, PlatformSummaryOut, RecentErrorsOut,
        )
        for schema in [PlatformSummaryOut, CacheHealthOut, DatabaseHealthOut,
                       ApiHealthOut, RecentErrorsOut]:
            assert "checked_at" in schema.model_fields

        # ModuleHealthOut itself doesn't have checked_at but items do
        assert "checked_at" in ModuleHealthItem.model_fields

    def test_module_configs_cache_flags(self):
        """Verify known cache_enabled flags match expectations."""
        assert _MODULE_CONFIGS["customers"][1] is True    # cache enabled
        assert _MODULE_CONFIGS["audit"][1] is False       # no cache
        assert _MODULE_CONFIGS["billing"][1] is True
        assert _MODULE_CONFIGS["executive_dashboard"][1] is False
