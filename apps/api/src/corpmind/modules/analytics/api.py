"""Analytics module REST API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.analytics.schemas import (
    AnalyticsFunnelOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
)
from corpmind.modules.analytics.service import AnalyticsService

router = APIRouter()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummary:
    """Return aggregated analytics over the last N days (default 30).

    Reads pre-computed analytics_daily rows — O(1) index scan, never
    aggregates transactional tables in the request handler.
    """
    return await AnalyticsService(session).get_summary(days=days)


@router.get("/trend", response_model=list[AnalyticsTrendOut])
async def get_analytics_trend(
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    session: AsyncSession = Depends(get_session),
) -> list[AnalyticsTrendOut]:
    """Return per-day rollup rows for trend charts (most recent first).

    Returns cross-channel aggregate rows only (channel IS NULL).
    Max 90 days to keep the payload bounded.
    """
    return await AnalyticsService(session).get_trend(days=days)


@router.get("/funnel", response_model=AnalyticsFunnelOut)
async def get_analytics_funnel(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsFunnelOut:
    """Return the live trainer revenue funnel for a workspace.

    Uses live transactional queries (not analytics_daily) so the funnel
    reflects the current pipeline state rather than yesterday's snapshot.
    All queries hit indexed columns and are fast at current tenant scale.
    """
    return await AnalyticsService(session).get_funnel(workspace_id=workspace_id)
