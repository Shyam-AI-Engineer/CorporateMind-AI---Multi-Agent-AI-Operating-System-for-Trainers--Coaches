"""Platform Observability & Diagnostics REST API — Sprint 57.

All endpoints are GET-only.  No writes, no mutations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.observability.schemas import (
    ApiHealthOut,
    CacheHealthOut,
    DatabaseHealthOut,
    ModuleHealthOut,
    PlatformSummaryOut,
    RecentErrorsOut,
)
from corpmind.modules.observability.service import ObservabilityService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> ObservabilityService:
    return ObservabilityService(session)


@router.get(
    "/summary",
    response_model=PlatformSummaryOut,
    summary="Aggregate platform health snapshot (cached 5 min)",
)
async def get_summary(
    svc: ObservabilityService = Depends(_svc),
) -> PlatformSummaryOut:
    return await svc.get_platform_summary()


@router.get(
    "/cache",
    response_model=CacheHealthOut,
    summary="Redis cache availability and hit/miss ratios",
)
async def get_cache_health(
    svc: ObservabilityService = Depends(_svc),
) -> CacheHealthOut:
    return await svc.get_cache_health()


@router.get(
    "/database",
    response_model=DatabaseHealthOut,
    summary="PostgreSQL connectivity, latency, and migration version",
)
async def get_database_health(
    svc: ObservabilityService = Depends(_svc),
) -> DatabaseHealthOut:
    return await svc.get_database_health()


@router.get(
    "/api",
    response_model=ApiHealthOut,
    summary="API route count and error-rate diagnostics",
)
async def get_api_health(
    request: Request,
    svc: ObservabilityService = Depends(_svc),
) -> ApiHealthOut:
    route_count = len(request.app.routes)
    return await svc.get_api_health(route_count)


@router.get(
    "/modules",
    response_model=ModuleHealthOut,
    summary="Per-module health and record counts (cached 5 min)",
)
async def get_module_health(
    svc: ObservabilityService = Depends(_svc),
) -> ModuleHealthOut:
    return await svc.get_module_health()


@router.get(
    "/errors",
    response_model=RecentErrorsOut,
    summary="Recent warning/critical audit events (last 24h, max 50)",
)
async def get_recent_errors(
    svc: ObservabilityService = Depends(_svc),
) -> RecentErrorsOut:
    return await svc.get_recent_errors()
