"""Dashboard API — Sprint 28 Business Health Center endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.dashboard.schemas import (
    BusinessHealthOut,
    BusinessSummaryOut,
    OperationalAlertsOut,
)
from corpmind.modules.dashboard.service import BusinessHealthService

router = APIRouter()


@router.get("/business-health", response_model=BusinessHealthOut)
async def get_business_health(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BusinessHealthOut:
    """Overall business health score with component breakdown and top alerts."""
    return await BusinessHealthService(session).get_health(workspace_id=workspace_id)


@router.get("/operational-alerts", response_model=OperationalAlertsOut)
async def get_operational_alerts(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> OperationalAlertsOut:
    """Full list of deterministic operational alerts ordered by priority."""
    return await BusinessHealthService(session).get_alerts(workspace_id=workspace_id)


@router.get("/business-summary", response_model=BusinessSummaryOut)
async def get_business_summary(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BusinessSummaryOut:
    """Template-generated executive summary of current business health."""
    return await BusinessHealthService(session).get_summary_data(workspace_id=workspace_id)
