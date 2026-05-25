"""Analytics repository — reads pre-computed rollup tables."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.analytics.models import AnalyticsDaily


class AnalyticsDailyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_date_range(
        self, from_date: date, to_date: date
    ) -> list[AnalyticsDaily]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AnalyticsDaily)
            .where(
                AnalyticsDaily.tenant_id == ctx.org_id,
                AnalyticsDaily.rollup_date >= from_date,
                AnalyticsDaily.rollup_date <= to_date,
            )
            .order_by(AnalyticsDaily.rollup_date.desc())
        )
        return list(result.scalars().all())
