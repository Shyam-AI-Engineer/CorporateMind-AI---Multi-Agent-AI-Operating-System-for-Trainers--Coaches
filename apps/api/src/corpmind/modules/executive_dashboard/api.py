"""Executive Dashboard REST API — Sprint 50.

Read-only endpoints. No writes. No mutations.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.executive_dashboard.schemas import (
    ExecutiveAlertOut,
    ExecutiveDashboardOut,
    ExecutiveKPIsOut,
    ExecutiveTrendOut,
)
from corpmind.modules.executive_dashboard.service import ExecutiveDashboardService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> ExecutiveDashboardService:
    return ExecutiveDashboardService(session)


@router.get("", response_model=ExecutiveDashboardOut)
async def get_dashboard(
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    svc: ExecutiveDashboardService = Depends(_svc),
) -> ExecutiveDashboardOut:
    return await svc.get_dashboard(workspace_id)


@router.get("/kpis", response_model=ExecutiveKPIsOut)
async def get_kpis(
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    svc: ExecutiveDashboardService = Depends(_svc),
) -> ExecutiveKPIsOut:
    return await svc.get_kpis(workspace_id)


@router.get("/alerts", response_model=list[ExecutiveAlertOut])
async def get_alerts(
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    svc: ExecutiveDashboardService = Depends(_svc),
) -> list[ExecutiveAlertOut]:
    return await svc.get_alerts(workspace_id)


@router.get("/trends", response_model=list[ExecutiveTrendOut])
async def get_trends(
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    days: Annotated[int, Query(description="Trend window: 30 | 90 | 365")] = 30,
    svc: ExecutiveDashboardService = Depends(_svc),
) -> list[ExecutiveTrendOut]:
    return await svc.get_trends(workspace_id, days=days)
