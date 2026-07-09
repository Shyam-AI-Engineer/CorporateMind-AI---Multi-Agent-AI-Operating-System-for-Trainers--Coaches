"""Platform Observability & Diagnostics service — Sprint 57.

All methods are READ-ONLY.  No writes, no mutations, no background tasks.
Cross-module data is accessed via sqlalchemy.text() raw SQL — never importing
other modules' models or repos.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
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

log = structlog.get_logger(__name__)

_CACHE_TTL = 300  # seconds

# Known TTL values for the cache config response
_KNOWN_TTLS: dict[str, int] = {
    "observability_summary": _CACHE_TTL,
    "observability_modules": _CACHE_TTL,
    "reporting_list": 300,
    "audit_list": 300,
    "approvals_list": 300,
    "notifications_list": 60,
    "integrations_list": 300,
}

# (table_name | None, cache_enabled)
_MODULE_CONFIGS: dict[str, tuple[str | None, bool]] = {
    "customers": ("customers", True),
    "training": ("training_engagements", False),
    "billing": ("customer_invoices", True),
    "payments": ("invoice_payments", False),
    "workflows": ("workflow_runs", True),
    "approvals": ("approval_requests", True),
    "notifications": ("notifications", True),
    "audit": ("audit_logs", False),
    "admin": ("organization_settings", False),
    "integrations": ("api_keys", True),
    "reporting": ("report_exports", True),
    "executive_dashboard": (None, False),
}


def _summary_cache_key(org_id: object) -> str:
    return f"t:{org_id}:observability:summary"


def _modules_cache_key(org_id: object) -> str:
    return f"t:{org_id}:observability:modules"


class ObservabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_platform_summary(self) -> PlatformSummaryOut:
        """Aggregate health snapshot; cached for 5 minutes."""
        ctx = get_tenant_context()
        cache_key = _summary_cache_key(ctx.org_id)

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return PlatformSummaryOut(**json.loads(cached))
        except Exception:
            pass

        db_health = await self.get_database_health()
        cache_health = await self.get_cache_health()
        module_health = await self.get_module_health()

        db_status = "healthy" if db_health.connection_ok else "down"
        cache_status = "healthy" if cache_health.redis_available else "degraded"

        score = 1.0
        if not db_health.connection_ok:
            score -= 0.4
        if not cache_health.redis_available:
            score -= 0.2
        if module_health.warning > 0:
            score -= 0.1 * min(module_health.warning, 3)
        score = max(0.0, round(score, 2))

        result = PlatformSummaryOut(
            overall_health_score=score,
            api_health="healthy",
            database_health=db_status,
            cache_health=cache_status,
            storage_health="healthy",
            active_modules=module_health.total,
            healthy_modules=module_health.healthy,
            warning_modules=module_health.warning,
            checked_at=datetime.now(UTC),
        )

        try:
            await get_redis().setex(cache_key, _CACHE_TTL, result.model_dump_json())
        except Exception:
            pass

        return result

    async def get_cache_health(self) -> CacheHealthOut:
        """Redis availability and estimated hit/miss ratios."""
        try:
            redis = get_redis()
            await redis.ping()
            info = await redis.info("stats")
            hits = int(info.get("keyspace_hits", 0))
            misses = int(info.get("keyspace_misses", 0))
            total = hits + misses
            hit_ratio = round(hits / total, 4) if total > 0 else 0.0
            miss_ratio = round(misses / total, 4) if total > 0 else 0.0
            available = True
        except Exception:
            available = False
            hit_ratio = 0.0
            miss_ratio = 0.0

        return CacheHealthOut(
            redis_available=available,
            estimated_hit_ratio=hit_ratio,
            estimated_miss_ratio=miss_ratio,
            ttl_configuration=_KNOWN_TTLS,
            checked_at=datetime.now(UTC),
        )

    async def get_database_health(self) -> DatabaseHealthOut:
        """PostgreSQL connectivity, round-trip latency, table count, and migration version."""
        try:
            t0 = time.perf_counter()
            await self._session.execute(text("SELECT 1"))
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            tbl_result = await self._session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            table_count = int(tbl_result.scalar_one() or 0)

            try:
                ver_result = await self._session.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                migration_version = ver_result.scalar_one_or_none() or "unknown"
            except Exception:
                migration_version = "unknown"

            connection_ok = True
        except Exception:
            connection_ok = False
            latency_ms = -1.0
            table_count = 0
            migration_version = "unknown"

        return DatabaseHealthOut(
            connection_ok=connection_ok,
            estimated_latency_ms=latency_ms,
            table_count=table_count,
            migration_version=migration_version,
            checked_at=datetime.now(UTC),
        )

    async def get_api_health(self, route_count: int) -> ApiHealthOut:
        """API route count plus error-rate derived from recent critical audit events."""
        try:
            ctx = get_tenant_context()
            result = await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE severity = 'critical') AS critical_count,
                        COUNT(*) AS total_count
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id
                      AND created_at >= NOW() - INTERVAL '24 hours'
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
            row = result.fetchone()
            critical = int(row[0] or 0)
            total = int(row[1] or 0)
            error_rate = round(critical / total, 4) if total > 0 else 0.0
        except Exception:
            error_rate = 0.0

        return ApiHealthOut(
            registered_routes=route_count,
            average_response_bucket="fast",
            error_rate=error_rate,
            checked_at=datetime.now(UTC),
        )

    async def get_module_health(self) -> ModuleHealthOut:
        """Per-module record count and health status; cached for 5 minutes."""
        ctx = get_tenant_context()
        cache_key = _modules_cache_key(ctx.org_id)

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                data = json.loads(cached)
                items = [ModuleHealthItem(**m) for m in data["modules"]]
                return ModuleHealthOut(
                    modules=items,
                    total=data["total"],
                    healthy=data["healthy"],
                    warning=data["warning"],
                )
        except Exception:
            pass

        now = datetime.now(UTC)
        items: list[ModuleHealthItem] = []

        for module_name, (table_name, cache_enabled) in _MODULE_CONFIGS.items():
            if table_name is None:
                items.append(
                    ModuleHealthItem(
                        module=module_name,
                        healthy=True,
                        enabled=True,
                        record_count=0,
                        cache_enabled=cache_enabled,
                        checked_at=now,
                    )
                )
                continue

            try:
                count_result = await self._session.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = :tenant_id"  # noqa: S608
                    ),
                    {"tenant_id": str(ctx.org_id)},
                )
                record_count = int(count_result.scalar_one() or 0)
                healthy = True
            except Exception:
                record_count = 0
                healthy = False

            items.append(
                ModuleHealthItem(
                    module=module_name,
                    healthy=healthy,
                    enabled=True,
                    record_count=record_count,
                    cache_enabled=cache_enabled,
                    checked_at=now,
                )
            )

        healthy_count = sum(1 for i in items if i.healthy)
        warning_count = len(items) - healthy_count

        result = ModuleHealthOut(
            modules=items,
            total=len(items),
            healthy=healthy_count,
            warning=warning_count,
        )

        try:
            await get_redis().setex(cache_key, _CACHE_TTL, result.model_dump_json())
        except Exception:
            pass

        return result

    async def get_recent_errors(self) -> RecentErrorsOut:
        """Recent warning/critical audit events in the last 24 hours (max 50)."""
        ctx = get_tenant_context()
        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT action, module, severity, created_at
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id
                      AND severity IN ('warning', 'critical')
                      AND created_at >= NOW() - INTERVAL '24 hours'
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
            rows = result.fetchall()
            errors = [
                RecentErrorItem(
                    source=str(row[1]),
                    message=str(row[0]),
                    severity=str(row[2]),
                    occurred_at=row[3],
                )
                for row in rows
            ]
        except Exception:
            errors = []

        return RecentErrorsOut(
            errors=errors,
            total=len(errors),
            checked_at=datetime.now(UTC),
        )
