"""Analytics repository — reads pre-computed rollup tables."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    async def upsert_rollup(
        self,
        *,
        tenant_id: uuid.UUID,
        rollup_date: date,
        channel: str | None,
        outreach_sent: int,
        outreach_delivered: int,
        outreach_opened: int,
        outreach_replied: int,
        compliance_blocks: int,
        meetings_scheduled: int,
        meetings_completed: int,
        leads_created: int,
        leads_booked: int,
        proposals_generated: int,
        proposals_approved: int,
        proposals_sent: int,
        ai_spend_inr: float,
    ) -> None:
        """Insert or replace a daily rollup row.

        ON CONFLICT DO UPDATE replaces all metric columns so re-running the
        rollup corrects any previously-written values rather than duplicating.
        The unique constraint uq_analytics_daily_tenant_date_channel ensures
        exactly one row per (tenant, date, channel).
        """
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "rollup_date": rollup_date,
            "channel": channel,
            "outreach_sent": outreach_sent,
            "outreach_delivered": outreach_delivered,
            "outreach_opened": outreach_opened,
            "outreach_replied": outreach_replied,
            "compliance_blocks": compliance_blocks,
            "meetings_scheduled": meetings_scheduled,
            "meetings_completed": meetings_completed,
            "leads_created": leads_created,
            "leads_booked": leads_booked,
            "proposals_generated": proposals_generated,
            "proposals_approved": proposals_approved,
            "proposals_sent": proposals_sent,
            "ai_spend_inr": ai_spend_inr,
            "computed_at": datetime.now(UTC),
        }
        skip = {"id", "tenant_id", "rollup_date", "channel"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(AnalyticsDaily)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_analytics_daily_tenant_date_channel",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)
