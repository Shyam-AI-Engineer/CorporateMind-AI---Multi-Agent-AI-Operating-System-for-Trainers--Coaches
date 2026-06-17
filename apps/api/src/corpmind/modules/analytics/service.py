"""Analytics service — serves pre-computed dashboard data.

Design rule (analytics.md): never aggregate in request handlers.
  get_summary() and get_trend() read analytics_daily (pre-computed by Celery beat).
  get_funnel()  is the sole exception — it reads live transactional tables because
  the funnel reflects current pipeline state, not yesterday's snapshot.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.analytics.repo import AnalyticsDailyRepo
from corpmind.modules.analytics.schemas import (
    AnalyticsFunnelOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
)

log = structlog.get_logger(__name__)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_summary(self, *, days: int = 30) -> AnalyticsSummary:
        """Aggregate analytics_daily rows over the last `days` days."""
        ctx = get_tenant_context()
        to_date = date.today()
        from_date = to_date - timedelta(days=days - 1)

        repo = AnalyticsDailyRepo(self._session)
        rows = await repo.list_by_date_range(from_date, to_date)

        # aggregate — channel=None rows are cross-channel totals; sum over all
        total_sent = sum(r.outreach_sent for r in rows)
        total_delivered = sum(r.outreach_delivered for r in rows)
        total_replied = sum(r.outreach_replied for r in rows)
        total_spend = sum(r.ai_spend_inr for r in rows)
        meetings_scheduled = sum(r.meetings_scheduled for r in rows)
        meetings_completed = sum(r.meetings_completed for r in rows)
        leads_created = sum(r.leads_created for r in rows)
        leads_booked = sum(r.leads_booked for r in rows)
        proposals_generated = sum(r.proposals_generated for r in rows)
        proposals_approved = sum(r.proposals_approved for r in rows)
        proposals_sent = sum(r.proposals_sent for r in rows)

        reply_rate = round(total_replied / total_sent, 4) if total_sent else 0.0
        delivery_rate = round(total_delivered / total_sent, 4) if total_sent else 0.0

        log.info(
            "analytics.summary.computed",
            tenant_id=str(ctx.org_id),
            days=days,
            rows=len(rows),
            total_sent=total_sent,
        )

        return AnalyticsSummary(
            period_days=days,
            total_sent=total_sent,
            total_delivered=total_delivered,
            total_replied=total_replied,
            reply_rate=reply_rate,
            delivery_rate=delivery_rate,
            total_spend_inr=round(total_spend, 2),
            meetings_scheduled=meetings_scheduled,
            meetings_completed=meetings_completed,
            leads_created=leads_created,
            leads_booked=leads_booked,
            proposals_generated=proposals_generated,
            proposals_approved=proposals_approved,
            proposals_sent=proposals_sent,
        )

    async def get_trend(self, *, days: int = 30) -> list[AnalyticsTrendOut]:
        """Return per-day rollup rows for trend charts (most recent first).

        Only returns cross-channel aggregate rows (channel IS NULL) to keep
        the payload small.  Per-channel breakdown is a Phase 2 endpoint.
        """
        ctx = get_tenant_context()
        to_date = date.today()
        from_date = to_date - timedelta(days=days - 1)

        repo = AnalyticsDailyRepo(self._session)
        rows = await repo.list_by_date_range(from_date, to_date)

        # Return only the aggregate (channel=None) rows; one per day
        agg_rows = [r for r in rows if r.channel is None]

        log.info(
            "analytics.trend.fetched",
            tenant_id=str(ctx.org_id),
            days=days,
            rows=len(agg_rows),
        )

        return [
            AnalyticsTrendOut(
                rollup_date=r.rollup_date,
                outreach_sent=r.outreach_sent,
                outreach_replied=r.outreach_replied,
                leads_created=r.leads_created,
                leads_booked=r.leads_booked,
                proposals_sent=r.proposals_sent,
                ai_spend_inr=r.ai_spend_inr,
            )
            for r in agg_rows
        ]

    async def get_funnel(self, *, workspace_id: uuid.UUID) -> AnalyticsFunnelOut:
        """Return live revenue funnel counts for a workspace.

        Intentionally reads transactional tables directly (not analytics_daily)
        because the funnel represents the current state of the pipeline, not
        yesterday's snapshot.  These queries are fast — all on indexed columns.

        Column notes:
          hr_contacts  — no workspace_id (org-scoped); scoped via campaign_recipients
          outbound_messages — no workspace_id; scoped via campaigns subquery
          leads, proposals — have workspace_id directly
        """
        ctx = get_tenant_context()
        tid = ctx.org_id

        # Distinct contacts that have been added to any campaign in this workspace
        contacts_result = await self._session.execute(
            text(
                "SELECT COUNT(DISTINCT cr.contact_id)"
                " FROM campaign_recipients cr"
                " JOIN campaigns c ON cr.campaign_id = c.id"
                " WHERE c.tenant_id = :tid AND c.workspace_id = :wid"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        contacts: int = contacts_result.scalar_one() or 0

        # Outbound messages sent via campaigns in this workspace
        outreach_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM outbound_messages om"
                " JOIN campaigns c ON om.campaign_id = c.id"
                " WHERE om.tenant_id = :tid AND c.workspace_id = :wid"
                " AND om.status IN ('sent','delivered','opened','replied')"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        outreach_sent: int = outreach_result.scalar_one() or 0

        # Interested replies from inbox connections in this workspace
        replies_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM inbox_messages im"
                " JOIN inbox_connections ic ON im.connection_id = ic.id"
                " WHERE im.tenant_id = :tid AND ic.workspace_id = :wid"
                " AND im.reply_intent = 'interested'"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        replies: int = replies_result.scalar_one() or 0

        meetings_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM leads"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " AND stage IN ('meeting_scheduled','meeting_completed','booked')"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        meetings: int = meetings_result.scalar_one() or 0

        proposals_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        proposals: int = proposals_result.scalar_one() or 0

        bookings_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM leads"
                " WHERE tenant_id = :tid AND workspace_id = :wid AND stage = 'booked'"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        bookings: int = bookings_result.scalar_one() or 0

        log.info(
            "analytics.funnel.computed",
            tenant_id=str(tid),
            workspace_id=str(workspace_id),
            contacts=contacts,
            outreach_sent=outreach_sent,
            replies=replies,
            meetings=meetings,
            proposals=proposals,
            bookings=bookings,
        )

        return AnalyticsFunnelOut(
            contacts=contacts,
            outreach_sent=outreach_sent,
            replies=replies,
            meetings=meetings,
            proposals=proposals,
            bookings=bookings,
        )
