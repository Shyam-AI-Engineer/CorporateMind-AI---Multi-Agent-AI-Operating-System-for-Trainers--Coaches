"""Analytics service — serves pre-computed dashboard data."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    # TODO(Phase 1): implement get_summary(), get_channel_breakdown()
    # Never aggregate in request handlers — read from analytics_daily only.
