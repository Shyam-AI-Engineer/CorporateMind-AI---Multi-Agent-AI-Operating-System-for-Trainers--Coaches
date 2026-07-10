"""Analytics service — serves pre-computed dashboard data.

Design rule (analytics.md): never aggregate in request handlers.
  get_summary() and get_trend() read analytics_daily (pre-computed by Celery beat).
  get_funnel()  is the sole exception — it reads live transactional tables because
  the funnel reflects current pipeline state, not yesterday's snapshot.

Sprint 19 intelligence methods (get_topic_performance, get_industry_performance,
get_pricing_calibration) are also live queries, following the get_funnel() precedent.
They run at most once per workspace per hour via Redis caching (1h TTL), so they never
execute on every page load.  get_campaign_roi() reads the pre-computed
analytics_campaign_summary table.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.analytics.models import RecommendationQualityScore
from corpmind.modules.analytics.repo import (
    AnalyticsCampaignSummaryRepo,
    AnalyticsDailyRepo,
    OutcomeWithTiming,
    RecommendationFeedbackRepo,
    RecommendationOutcomeRepo,
    RecommendationQualityScoreRepo,
    RecommendationSnapshotRepo,
)
from corpmind.modules.analytics.schemas import (
    AnalyticsChannelSummary,
    AnalyticsFunnelOut,
    AnalyticsInsightOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
    CampaignROIListOut,
    CampaignROISummary,
    IndustryPerformanceOut,
    IndustryStat,
    InsightOpportunity,
    InsightRisk,
    PricingCalibrationOut,
    QualityTrendPointOut,
    RecAdoptedTypeOut,
    RecBestWorstPerformerOut,
    RecCalibrationGroupItemOut,
    RecCalibrationGroupSummaryOut,
    RecCalibrationOut,
    RecCalibrationOverallOut,
    RecCalibrationTypeItemOut,
    RecEffectivenessOut,
    RecEffectivenessSummaryOut,
    RecEffectivenessTypeItemOut,
    CalibrationAccuracyOut,
    CalibrationReviewOut,
    CalibrationReviewTypeItemOut,
    ConfidenceDistributionOut,
    QualityScoreStabilityOut,
    RecIgnoredTypeOut,
    RecReviewOut,
    RecReviewTrendPointOut,
    RecSuccessfulTypeOut,
    RecommendationEffectivenessOut,
    RecommendationFeedbackIn,
    RecommendationFeedbackOut,
    RecommendationItem,
    RecommendationQualityItem,
    RecommendationsOut,
    CoverageItemOut,
    CoverageOut,
    DecayBucketOut,
    EvidenceMetricOut,
    EvidenceOut,
    EvidenceSummaryOut,
    DecayOut,
    DecayTypeItemOut,
    DriftOut,
    DriftOverallOut,
    DriftTypeItemOut,
    LifecycleOut,
    LifecycleOverallOut,
    LifecycleTypeItemOut,
    MetricTrendOut,
    PortfolioBalanceOut,
    PortfolioOut,
    PortfolioTypeItemOut,
    ReliabilityOut,
    ReliabilityOverallOut,
    ReliabilityTypeItemOut,
    StabilityOut,
    StabilityTypeItemOut,
    TopicPerformanceOut,
    TopicStat,
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
        proposals_accepted = sum(r.proposals_accepted for r in rows)
        closed_revenue_inr = float(sum(r.closed_revenue_inr for r in rows))

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
            proposals_accepted=proposals_accepted,
            closed_revenue_inr=round(closed_revenue_inr, 2),
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

        # Sprint 18A — revenue queries (live from proposals, same pattern as bookings)
        accepted_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " AND client_status = 'accepted'"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        proposals_accepted: int = accepted_result.scalar_one() or 0

        pipeline_result = await self._session.execute(
            text(
                "SELECT COALESCE(SUM(expected_value_inr), 0) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " AND status = 'sent' AND client_status IS NULL"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        pipeline_value_inr: float = float(pipeline_result.scalar_one() or 0)

        revenue_result = await self._session.execute(
            text(
                "SELECT COALESCE(SUM(actual_value_inr), 0) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " AND client_status = 'accepted'"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        closed_revenue_inr: float = float(revenue_result.scalar_one() or 0)

        proposals_sent_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid AND status = 'sent'"
            ),
            {"tid": tid, "wid": workspace_id},
        )
        proposals_sent_count: int = proposals_sent_result.scalar_one() or 0
        win_rate = (
            round(proposals_accepted / proposals_sent_count, 4)
            if proposals_sent_count
            else 0.0
        )

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
            proposals_accepted=proposals_accepted,
            pipeline_value_inr=pipeline_value_inr,
            closed_revenue_inr=closed_revenue_inr,
        )

        return AnalyticsFunnelOut(
            contacts=contacts,
            outreach_sent=outreach_sent,
            replies=replies,
            meetings=meetings,
            proposals=proposals,
            bookings=bookings,
            proposals_accepted=proposals_accepted,
            pipeline_value_inr=round(pipeline_value_inr, 2),
            closed_revenue_inr=round(closed_revenue_inr, 2),
            win_rate=win_rate,
        )

    async def get_channel_summary(
        self, *, channel: str, days: int = 30
    ) -> AnalyticsChannelSummary:
        """Return per-channel outreach performance for the last N days.

        sent / delivered / opened / compliance_blocks: summed from analytics_daily
        channel-specific rows (written by the WA rollup in Sprint 16B).
        failed: computed live from outbound_messages because analytics_daily has
        no outreach_failed column — identical pattern to get_funnel().
        """
        ctx = get_tenant_context()
        to_date = date.today()
        from_date = to_date - timedelta(days=days - 1)

        repo = AnalyticsDailyRepo(self._session)
        rows = await repo.list_by_date_range(from_date, to_date)
        channel_rows = [r for r in rows if r.channel == channel]

        sent = sum(r.outreach_sent for r in channel_rows)
        delivered = sum(r.outreach_delivered for r in channel_rows)
        opened = sum(r.outreach_opened for r in channel_rows)
        compliance_blocks = sum(r.compliance_blocks for r in channel_rows)

        # failed: live query — analytics_daily has no outreach_failed column.
        failed_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM outbound_messages"
                " WHERE tenant_id = :tid AND channel = :ch"
                " AND failed_at::date >= :from_d AND failed_at::date <= :to_d"
            ),
            {
                "tid": ctx.org_id,
                "ch": channel,
                "from_d": from_date,
                "to_d": to_date,
            },
        )
        failed = int(failed_result.scalar_one() or 0)

        delivery_rate = round(delivered / sent, 4) if sent else 0.0
        read_rate = round(opened / delivered, 4) if delivered else 0.0

        log.info(
            "analytics.channel_summary.computed",
            tenant_id=str(ctx.org_id),
            channel=channel,
            days=days,
            sent=sent,
            delivered=delivered,
            opened=opened,
        )

        return AnalyticsChannelSummary(
            channel=channel,
            period_days=days,
            sent=sent,
            delivered=delivered,
            opened=opened,
            failed=failed,
            compliance_blocks=compliance_blocks,
            delivery_rate=delivery_rate,
            read_rate=read_rate,
        )

    # ── Sprint 19 intelligence methods ───────────────────────────────────────

    async def get_campaign_roi(
        self,
        *,
        workspace_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> CampaignROIListOut:
        """Return paginated campaign ROI from analytics_campaign_summary.

        Uses pre-computed snapshot rows — fast, no aggregation at request time.
        Attribution model is 'all_touch': a contact in multiple campaigns
        has their revenue credited to each.
        """
        repo = AnalyticsCampaignSummaryRepo(self._session)
        rows = await repo.list_by_workspace(workspace_id, limit=limit, offset=offset)
        total = await repo.count_by_workspace(workspace_id)

        items = [
            CampaignROISummary(
                campaign_id=r.campaign_id,
                campaign_name=r.campaign_name,
                channel=r.channel,
                campaign_status=r.campaign_status,
                recipients_count=r.recipients_count,
                messages_sent=r.messages_sent,
                messages_delivered=r.messages_delivered,
                replies_received=r.replies_received,
                leads_created=r.leads_created,
                proposals_sent=r.proposals_sent,
                proposals_accepted=r.proposals_accepted,
                win_rate=float(r.win_rate),
                closed_revenue_inr=float(r.closed_revenue_inr),
                avg_deal_size_inr=float(r.avg_deal_size_inr) if r.avg_deal_size_inr is not None else None,
                avg_days_to_accept=float(r.avg_days_to_accept) if r.avg_days_to_accept is not None else None,
                last_refreshed_at=r.last_refreshed_at,
                sample_size=r.proposals_sent,
                low_confidence=r.proposals_sent < 5,
            )
            for r in rows
        ]

        log.info(
            "analytics.campaign_roi.fetched",
            tenant_id=str(get_tenant_context().org_id),
            workspace_id=str(workspace_id),
            total=total,
        )
        return CampaignROIListOut(items=items, total=total)

    async def get_topic_performance(
        self,
        *,
        workspace_id: uuid.UUID,
        limit: int = 15,
    ) -> TopicPerformanceOut:
        """Return top trainer topics by revenue and win rate.

        Live query against trainer_profiles (UNNEST topics) joined to proposals.
        Result is Redis-cached per workspace for 1 hour so it never runs on
        every page load (follows get_funnel() precedent).
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:topics"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return TopicPerformanceOut.model_validate_json(cached)
        except Exception:
            pass  # Redis unavailable — proceed to live query

        sample_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid AND status = 'sent'"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        sample_size = int(sample_result.scalar_one() or 0)

        rows_result = await self._session.execute(
            text(
                "SELECT"
                "  t.topic,"
                "  COUNT(p.id) AS proposals_sent,"
                "  COUNT(p.id) FILTER (WHERE p.client_status = 'accepted') AS proposals_accepted,"
                "  COALESCE(SUM(p.actual_value_inr)"
                "    FILTER (WHERE p.client_status = 'accepted'), 0) AS closed_revenue_inr"
                " FROM trainer_profiles tp"
                " CROSS JOIN UNNEST(tp.topics) AS t(topic)"
                " JOIN proposals p"
                "   ON p.workspace_id = tp.workspace_id"
                "  AND p.tenant_id = tp.tenant_id"
                "  AND p.status = 'sent'"
                " WHERE tp.tenant_id = :tid AND tp.workspace_id = :wid"
                " GROUP BY t.topic"
                " ORDER BY closed_revenue_inr DESC"
                " LIMIT :lim"
            ),
            {"tid": ctx.org_id, "wid": workspace_id, "lim": limit},
        )
        rows = rows_result.mappings().all()

        items = [
            TopicStat(
                topic=row["topic"],
                proposals_sent=row["proposals_sent"],
                proposals_accepted=row["proposals_accepted"],
                win_rate=(
                    round(row["proposals_accepted"] / row["proposals_sent"], 4)
                    if row["proposals_sent"] > 0
                    else 0.0
                ),
                closed_revenue_inr=float(row["closed_revenue_inr"]),
            )
            for row in rows
            if row["topic"]
        ]

        out = TopicPerformanceOut(
            items=items,
            workspace_id=str(workspace_id),
            generated_at=datetime.now(UTC),
            sample_size=sample_size,
            low_confidence=sample_size < 5,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.topics.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            topic_count=len(items),
            sample_size=sample_size,
        )
        return out

    async def get_industry_performance(
        self,
        *,
        workspace_id: uuid.UUID,
        limit: int = 15,
    ) -> IndustryPerformanceOut:
        """Return top industries by revenue and win rate.

        Three-table join: proposals → hr_contacts → companies.industry.
        NULL industries are grouped as 'Unknown'.
        Redis-cached 1 hour per workspace.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:industries"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return IndustryPerformanceOut.model_validate_json(cached)
        except Exception:
            pass

        sample_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid AND status = 'sent'"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        sample_size = int(sample_result.scalar_one() or 0)

        unknown_result = await self._session.execute(
            text(
                "SELECT COUNT(*) FROM proposals p"
                " JOIN hr_contacts hc ON hc.id = p.contact_id AND hc.tenant_id = p.tenant_id"
                " JOIN companies co    ON co.id = hc.company_id AND co.tenant_id = p.tenant_id"
                " WHERE p.tenant_id = :tid AND p.workspace_id = :wid"
                "   AND p.status = 'sent' AND co.industry IS NULL"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        unknown_count = int(unknown_result.scalar_one() or 0)

        rows_result = await self._session.execute(
            text(
                "SELECT"
                "  COALESCE(co.industry, 'Unknown') AS industry,"
                "  COUNT(p.id) AS proposals_sent,"
                "  COUNT(p.id) FILTER (WHERE p.client_status = 'accepted') AS proposals_accepted,"
                "  COALESCE(SUM(p.actual_value_inr)"
                "    FILTER (WHERE p.client_status = 'accepted'), 0) AS closed_revenue_inr"
                " FROM proposals p"
                " JOIN hr_contacts hc ON hc.id = p.contact_id AND hc.tenant_id = p.tenant_id"
                " JOIN companies co    ON co.id = hc.company_id AND co.tenant_id = p.tenant_id"
                " WHERE p.tenant_id = :tid AND p.workspace_id = :wid AND p.status = 'sent'"
                " GROUP BY COALESCE(co.industry, 'Unknown')"
                " ORDER BY closed_revenue_inr DESC"
                " LIMIT :lim"
            ),
            {"tid": ctx.org_id, "wid": workspace_id, "lim": limit},
        )
        rows = rows_result.mappings().all()

        items = [
            IndustryStat(
                industry=row["industry"],
                proposals_sent=row["proposals_sent"],
                proposals_accepted=row["proposals_accepted"],
                win_rate=(
                    round(row["proposals_accepted"] / row["proposals_sent"], 4)
                    if row["proposals_sent"] > 0
                    else 0.0
                ),
                closed_revenue_inr=float(row["closed_revenue_inr"]),
            )
            for row in rows
        ]

        out = IndustryPerformanceOut(
            items=items,
            workspace_id=str(workspace_id),
            generated_at=datetime.now(UTC),
            unknown_count=unknown_count,
            sample_size=sample_size,
            low_confidence=sample_size < 5,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.industries.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            industry_count=len(items),
            sample_size=sample_size,
            unknown_count=unknown_count,
        )
        return out

    async def get_pricing_calibration(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> PricingCalibrationOut:
        """Return pricing calibration: stated trainer range vs actual accepted values.

        Uses PERCENTILE_CONT for median — requires at least 1 accepted proposal.
        avg_days_to_accept is the workspace-wide average (Amendment 1).
        Redis-cached 1 hour per workspace.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:pricing"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return PricingCalibrationOut.model_validate_json(cached)
        except Exception:
            pass

        # Trainer profile pricing range (most recently locked profile)
        profile_result = await self._session.execute(
            text(
                "SELECT pricing_min_inr, pricing_max_inr"
                " FROM trainer_profiles"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " ORDER BY created_at DESC LIMIT 1"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        profile_row = profile_result.mappings().first()
        stated_min = int(profile_row["pricing_min_inr"]) if profile_row and profile_row["pricing_min_inr"] else None
        stated_max = int(profile_row["pricing_max_inr"]) if profile_row and profile_row["pricing_max_inr"] else None

        # Actual accepted proposal statistics
        stats_result = await self._session.execute(
            text(
                "SELECT"
                "  COUNT(*)                                                         AS sample_size,"
                "  MIN(actual_value_inr)                                            AS actual_min,"
                "  MAX(actual_value_inr)                                            AS actual_max,"
                "  AVG(actual_value_inr)                                            AS actual_avg,"
                "  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY actual_value_inr)   AS actual_median,"
                "  AVG(EXTRACT(EPOCH FROM (client_accepted_at - sent_at)) / 86400.0)"
                "    FILTER (WHERE sent_at IS NOT NULL AND client_accepted_at IS NOT NULL)"
                "                                                                   AS avg_days"
                " FROM proposals"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                "   AND client_status = 'accepted' AND actual_value_inr IS NOT NULL"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        stats = stats_result.mappings().first()

        sample_size = int(stats["sample_size"]) if stats and stats["sample_size"] else 0
        actual_min = float(stats["actual_min"]) if stats and stats["actual_min"] is not None else None
        actual_max = float(stats["actual_max"]) if stats and stats["actual_max"] is not None else None
        actual_avg = round(float(stats["actual_avg"]), 2) if stats and stats["actual_avg"] is not None else None
        actual_median = round(float(stats["actual_median"]), 2) if stats and stats["actual_median"] is not None else None
        avg_days = round(float(stats["avg_days"]), 2) if stats and stats["avg_days"] is not None else None

        out = PricingCalibrationOut(
            workspace_id=str(workspace_id),
            stated_min_inr=stated_min,
            stated_max_inr=stated_max,
            actual_min_inr=actual_min,
            actual_max_inr=actual_max,
            actual_avg_inr=actual_avg,
            actual_median_inr=actual_median,
            avg_days_to_accept=avg_days,
            sample_size=sample_size,
            low_confidence=sample_size < 5,
            generated_at=datetime.now(UTC),
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.pricing.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            sample_size=sample_size,
            avg_days_to_accept=avg_days,
        )
        return out

    # ── Sprint 20A — Deterministic Recommendations ───────────────────────────

    @staticmethod
    def _confidence(
        *,
        n: int,
        n_ideal: int,
        hard_min: int,
        delta: float,
        noise_floor: float,
        signal_ceiling: float,
    ) -> tuple[int, str, str]:
        """Return (confidence_score, confidence_level, evidence_strength).

        Returns (0, 'suppressed', 'weak') when n < hard_min or final score < 20.
        Composite formula: S × 0.6 + R × 0.4
          S = sample adequacy  (n / n_ideal, capped at 1.0)
          R = signal strength  (delta above noise_floor, normalised to signal_ceiling)
        """
        if n < hard_min:
            return 0, "suppressed", "weak"
        S = min(n / n_ideal, 1.0)
        span = max(signal_ceiling - noise_floor, 1e-9)
        R = max(0.0, min((delta - noise_floor) / span, 1.0))
        raw = S * 0.6 + R * 0.4
        score = round(raw * 100)
        if score < 20:
            return 0, "suppressed", "weak"
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        strength = "strong" if score >= 70 else "moderate" if score >= 40 else "weak"
        return score, level, strength

    async def _rec_industry(
        self,
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> tuple[RecommendationItem | None, int]:
        """Industry targeting recommendation.

        Returns (item, suppressed_increment).  suppressed_increment is 1 when
        data exists but confidence is below threshold (not when there is simply
        no data at all, to avoid inflating suppressed_count for empty workspaces).
        """
        industry_data = await self.get_industry_performance(workspace_id=workspace_id)
        qualifying = [i for i in industry_data.items if i.proposals_sent >= 5 and i.industry != "Unknown"]
        if len(qualifying) < 2:
            return None, (1 if qualifying else 0)

        best = max(qualifying, key=lambda x: x.win_rate)
        sorted_rates = sorted(i.win_rate for i in qualifying)
        median_wr = sorted_rates[len(sorted_rates) // 2]
        delta = best.win_rate - median_wr

        if delta < 0.05:
            return None, 0

        score, level, strength = self._confidence(
            n=best.proposals_sent,
            n_ideal=20,
            hard_min=5,
            delta=delta,
            noise_floor=0.05,
            signal_ceiling=0.25,
        )
        if score == 0:
            return None, 1

        item = RecommendationItem(
            type="industry",
            title=f"Focus on {best.industry}",
            rationale=(
                f"{best.industry} closes at {best.win_rate * 100:.0f}% "
                f"vs your {median_wr * 100:.0f}% median — "
                f"{delta * 100:.0f}pp higher."
            ),
            action=f"Target {best.industry} companies in your next campaign.",
            supporting_data={
                "industry": best.industry,
                "win_rate": round(best.win_rate, 4),
                "median_win_rate": round(median_wr, 4),
                "delta_pp": round(delta * 100, 1),
                "proposals_sent": best.proposals_sent,
                "closed_revenue_inr": best.closed_revenue_inr,
                "qualifying_industries": len(qualifying),
            },
            confidence_score=score,
            confidence_level=level,
            evidence_strength=strength,
            sample_size=best.proposals_sent,
            low_confidence=score < 40,
            generated_at=now,
        )
        return item, 0

    async def _rec_topic(
        self,
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> tuple[RecommendationItem | None, int]:
        """Topic selection recommendation — requires ≥2 qualifying topics."""
        topic_data = await self.get_topic_performance(workspace_id=workspace_id)
        qualifying = [t for t in topic_data.items if t.proposals_sent >= 5]
        if len(qualifying) < 2:
            return None, (1 if qualifying else 0)

        best = max(qualifying, key=lambda x: x.win_rate)
        second_best = sorted(qualifying, key=lambda x: x.win_rate, reverse=True)[1]
        delta = best.win_rate - second_best.win_rate

        if delta < 0.08:
            return None, 0

        score, level, strength = self._confidence(
            n=best.proposals_sent,
            n_ideal=15,
            hard_min=5,
            delta=delta,
            noise_floor=0.08,
            signal_ceiling=0.30,
        )
        if score == 0:
            return None, 1

        item = RecommendationItem(
            type="topic",
            title=f"Lead with {best.topic}",
            rationale=(
                f"{best.topic} closes at {best.win_rate * 100:.0f}% "
                f"vs {second_best.topic} at {second_best.win_rate * 100:.0f}% — "
                f"{delta * 100:.0f}pp higher win rate."
            ),
            action=f"Position {best.topic} as your primary topic in upcoming proposals.",
            supporting_data={
                "topic": best.topic,
                "win_rate": round(best.win_rate, 4),
                "runner_up_topic": second_best.topic,
                "runner_up_win_rate": round(second_best.win_rate, 4),
                "delta_pp": round(delta * 100, 1),
                "proposals_sent": best.proposals_sent,
                "closed_revenue_inr": best.closed_revenue_inr,
                "qualifying_topics": len(qualifying),
            },
            confidence_score=score,
            confidence_level=level,
            evidence_strength=strength,
            sample_size=best.proposals_sent,
            low_confidence=score < 40,
            generated_at=now,
        )
        return item, 0

    async def _rec_pricing(
        self,
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> tuple[RecommendationItem | None, int]:
        """Pricing optimization recommendation.

        Checks three sub-cases in priority order:
        1. Underpriced  — actual_median > stated_max * 1.05
        2. Overpriced   — actual_median < stated_min * 0.85
        3. Slow         — avg_days_to_accept > 30
        Returns the highest-priority applicable case, or None.
        """
        pricing = await self.get_pricing_calibration(workspace_id=workspace_id)

        # Hard minimum: 10 accepted proposals with recorded value
        score, level, strength = self._confidence(
            n=pricing.sample_size,
            n_ideal=20,
            hard_min=10,
            delta=0.0,  # will be overridden per case below
            noise_floor=0.05,
            signal_ceiling=0.30,
        )
        if pricing.sample_size < 10:
            return None, (1 if pricing.sample_size > 0 else 0)

        median = pricing.actual_median_inr
        if median is None:
            return None, 0

        # Re-compute score with actual signal delta
        rec_type: str | None = None
        delta_ratio = 0.0

        if pricing.stated_max_inr and median > pricing.stated_max_inr * 1.05:
            rec_type = "underpriced"
            delta_ratio = (median - pricing.stated_max_inr) / pricing.stated_max_inr
        elif pricing.stated_min_inr and median < pricing.stated_min_inr * 0.85:
            rec_type = "overpriced"
            delta_ratio = (pricing.stated_min_inr - median) / pricing.stated_min_inr
        elif pricing.avg_days_to_accept is not None and pricing.avg_days_to_accept > 30:
            rec_type = "slow_acceptance"
            delta_ratio = (pricing.avg_days_to_accept - 30) / 30  # normalise over 30-day baseline

        if rec_type is None:
            return None, 0

        score, level, strength = self._confidence(
            n=pricing.sample_size,
            n_ideal=20,
            hard_min=10,
            delta=delta_ratio,
            noise_floor=0.05,
            signal_ceiling=0.30,
        )
        if score == 0:
            return None, 1

        if rec_type == "underpriced":
            title = "You may be underpricing your workshops"
            rationale = (
                f"Your accepted deals median at "
                f"₹{median:,.0f}, above your stated ceiling of "
                f"₹{pricing.stated_max_inr:,.0f} — clients are consistently paying more than your floor."
            )
            action = f"Consider raising your pricing floor to ₹{median:,.0f}."
        elif rec_type == "overpriced":
            title = "Your closing price is below your stated range"
            rationale = (
                f"Accepted deals median at ₹{median:,.0f}, "
                f"below your stated minimum of ₹{pricing.stated_min_inr:,.0f}."
            )
            action = "Review your stated minimum — or focus on higher-budget segments."
        else:
            title = "Proposals are taking longer than average to close"
            rationale = (
                f"Your avg acceptance time is "
                f"{pricing.avg_days_to_accept:.1f} days — "
                f"above the 30-day benchmark."
            )
            action = "Consider adding a limited-validity clause (e.g., 21-day offer window) to your proposals."

        item = RecommendationItem(
            type="pricing",
            title=title,
            rationale=rationale,
            action=action,
            supporting_data={
                "sub_type": rec_type,
                "actual_median_inr": round(median, 2),
                "stated_min_inr": pricing.stated_min_inr,
                "stated_max_inr": pricing.stated_max_inr,
                "avg_days_to_accept": pricing.avg_days_to_accept,
                "sample_size": pricing.sample_size,
            },
            confidence_score=score,
            confidence_level=level,
            evidence_strength=strength,
            sample_size=pricing.sample_size,
            low_confidence=score < 40,
            generated_at=now,
        )
        return item, 0

    async def _rec_campaign(
        self,
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> tuple[RecommendationItem | None, int]:
        """Best campaign pattern recommendation.

        Reads analytics_campaign_summary directly to avoid pagination limits.
        Requires ≥3 campaigns each with ≥5 proposals_sent.
        """
        ctx = get_tenant_context()
        rows_result = await self._session.execute(
            text(
                "SELECT campaign_name, channel, win_rate, closed_revenue_inr,"
                "       proposals_sent, proposals_accepted, avg_days_to_accept,"
                "       recipients_count"
                " FROM analytics_campaign_summary"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                "   AND proposals_sent >= 5"
                " ORDER BY closed_revenue_inr DESC"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        rows = rows_result.mappings().all()

        if len(rows) < 3:
            return None, (1 if rows else 0)

        best = rows[0]
        worst = rows[-1]
        best_rev = float(best["closed_revenue_inr"])
        worst_rev = float(worst["closed_revenue_inr"]) if worst["closed_revenue_inr"] else 0.0
        roi_ratio = (best_rev / worst_rev) if worst_rev > 0 else 999.0

        if roi_ratio < 1.5:
            return None, 0

        sample_n = int(best["proposals_sent"])
        score, level, strength = self._confidence(
            n=len(rows),
            n_ideal=5,
            hard_min=3,
            delta=roi_ratio - 1.0,
            noise_floor=0.5,
            signal_ceiling=2.0,
        )
        if score == 0:
            return None, 1

        item = RecommendationItem(
            type="campaign",
            title=f"Replicate '{best['campaign_name']}'",
            rationale=(
                f"'{best['campaign_name']}' ({best['channel']}) closed "
                f"₹{best_rev:,.0f} with a "
                f"{float(best['win_rate']) * 100:.0f}% win rate — "
                f"{roi_ratio:.1f}× more revenue than your lowest-performing campaign."
            ),
            action=(
                f"Model your next campaign on '{best['campaign_name']}': "
                f"same channel ({best['channel']}), same structure."
            ),
            supporting_data={
                "campaign_name": best["campaign_name"],
                "channel": best["channel"],
                "win_rate": round(float(best["win_rate"]), 4),
                "closed_revenue_inr": best_rev,
                "proposals_sent": sample_n,
                "roi_ratio": round(roi_ratio, 2),
                "qualifying_campaigns": len(rows),
            },
            confidence_score=score,
            confidence_level=level,
            evidence_strength=strength,
            sample_size=sample_n,
            low_confidence=score < 40,
            generated_at=now,
        )
        return item, 0

    async def _rec_channel(
        self,
        workspace_id: uuid.UUID,
        now: datetime,
    ) -> tuple[RecommendationItem | None, int]:
        """Channel selection recommendation.

        Aggregates analytics_campaign_summary by channel — no new migration needed.
        Requires ≥2 channels each with ≥5 proposals_sent in aggregate.
        """
        ctx = get_tenant_context()
        rows_result = await self._session.execute(
            text(
                "SELECT channel,"
                "  SUM(proposals_sent)     AS total_sent,"
                "  SUM(proposals_accepted) AS total_accepted,"
                "  SUM(closed_revenue_inr) AS total_revenue"
                " FROM analytics_campaign_summary"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                " GROUP BY channel"
                " HAVING SUM(proposals_sent) >= 5"
                " ORDER BY total_revenue DESC"
            ),
            {"tid": ctx.org_id, "wid": workspace_id},
        )
        rows = rows_result.mappings().all()

        if len(rows) < 2:
            return None, (1 if rows else 0)

        best = rows[0]
        second = rows[1]
        best_sent = int(best["total_sent"])
        best_accepted = int(best["total_accepted"])
        second_sent = int(second["total_sent"])
        second_accepted = int(second["total_accepted"])

        best_wr = round(best_accepted / best_sent, 4) if best_sent else 0.0
        second_wr = round(second_accepted / second_sent, 4) if second_sent else 0.0
        delta = best_wr - second_wr

        if delta < 0.05:
            return None, 0

        score, level, strength = self._confidence(
            n=best_sent,
            n_ideal=20,
            hard_min=5,
            delta=delta,
            noise_floor=0.05,
            signal_ceiling=0.20,
        )
        if score == 0:
            return None, 1

        item = RecommendationItem(
            type="channel",
            title=f"{best['channel'].title()} outperforms other channels",
            rationale=(
                f"{best['channel'].title()} closes at {best_wr * 100:.0f}% "
                f"vs {second['channel'].title()} at {second_wr * 100:.0f}% — "
                f"{delta * 100:.0f}pp higher win rate."
            ),
            action=f"Prioritise {best['channel'].title()} for your next outreach campaign.",
            supporting_data={
                "channel": best["channel"],
                "win_rate": best_wr,
                "runner_up_channel": second["channel"],
                "runner_up_win_rate": second_wr,
                "delta_pp": round(delta * 100, 1),
                "proposals_sent": best_sent,
                "closed_revenue_inr": float(best["total_revenue"]) if best["total_revenue"] else 0.0,
                "qualifying_channels": len(rows),
            },
            confidence_score=score,
            confidence_level=level,
            evidence_strength=strength,
            sample_size=best_sent,
            low_confidence=score < 40,
            generated_at=now,
        )
        return item, 0

    async def get_recommendations(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> RecommendationsOut:
        """Return all 5 deterministic recommendations for a workspace.

        All recommendations are computed from existing Sprint 19 pre-computed
        tables and live intelligence queries.  No LLM involved.
        Redis-cached 4 hours per workspace — recommendations change slowly.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:recommendations"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecommendationsOut.model_validate_json(cached)
        except Exception:
            pass

        now = datetime.now(UTC)
        recommendations: list[RecommendationItem] = []
        suppressed_count = 0

        for coro in [
            self._rec_industry(workspace_id, now),
            self._rec_topic(workspace_id, now),
            self._rec_pricing(workspace_id, now),
            self._rec_campaign(workspace_id, now),
            self._rec_channel(workspace_id, now),
        ]:
            try:
                item, suppressed = await coro
                if item:
                    recommendations.append(item)
                suppressed_count += suppressed
            except Exception:
                pass  # partial failure — skip this recommendation type gracefully

        out = RecommendationsOut(
            workspace_id=str(workspace_id),
            generated_at=now,
            period_days=90,
            recommendations=recommendations,
            suppressed_count=suppressed_count,
            total=len(recommendations),
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=14400)  # 4 h
        except Exception:
            pass

        # Persist snapshots silently — failure must never degrade the response
        try:
            await self._persist_snapshots(
                tenant_id=ctx.org_id,
                workspace_id=workspace_id,
                recommendations=recommendations,
                snapshot_date=now.date(),
            )
        except Exception:
            pass

        log.info(
            "analytics.recommendations.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            total=len(recommendations),
            suppressed=suppressed_count,
        )
        return out

    async def _persist_snapshots(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        recommendations: list[RecommendationItem],
        snapshot_date: date,
    ) -> None:
        """Upsert one recommendation_snapshots row per item.

        Called on every cache miss so that feedback and outcome tracking have
        stable snapshot IDs to reference.  ON CONFLICT DO UPDATE on
        (tenant_id, workspace_id, rec_type, snapshot_date) makes re-runs safe.
        """
        repo = RecommendationSnapshotRepo(self._session)
        for item in recommendations:
            try:
                await repo.upsert_snapshot(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    snapshot_date=snapshot_date,
                    rec_type=item.type,
                    confidence_score=item.confidence_score,
                    confidence_level=item.confidence_level,
                    title=item.title,
                    supporting_data=item.supporting_data,
                    generated_at=item.generated_at,
                )
            except Exception:
                pass  # partial failure — skip this item, don't abort the loop


# ── Sprint 20B — AI Insight Layer ────────────────────────────────────────────


class AnalyticsInsightService:
    """Wraps deterministic recommendations with a single cheap LLM narrative call.

    The AI receives only the serialised RecommendationsOut payload — it cannot
    access raw DB data, alter confidence scores, or invent new recommendations.
    This class is the sole LLM consumer in the analytics module.
    """

    _INSUFFICIENT_DATA_SUMMARY = (
        "Insufficient data to generate insights. "
        "Run more campaigns and record deal outcomes to unlock AI-powered analysis."
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _build_context(recs: RecommendationsOut) -> dict[str, object]:
        """Serialise RecommendationsOut into a prompt-safe context dict.

        The AI only sees what this method returns — nothing else from the DB.
        """
        return {
            "workspace_id": recs.workspace_id,
            "period_days": recs.period_days,
            "generated_at": recs.generated_at.isoformat(),
            "total_recommendations": recs.total,
            "suppressed_count": recs.suppressed_count,
            "recommendations": [
                {
                    "type": r.type,
                    "title": r.title,
                    "rationale": r.rationale,
                    "action": r.action,
                    "confidence_level": r.confidence_level,
                    "evidence_strength": r.evidence_strength,
                    "confidence_score": r.confidence_score,
                    "sample_size": r.sample_size,
                    "low_confidence": r.low_confidence,
                    "supporting_data": r.supporting_data,
                }
                for r in recs.recommendations
            ],
        }

    @staticmethod
    def _parse_response(content: str, recs: RecommendationsOut) -> AnalyticsInsightOut:
        """Parse LLM JSON output. Falls back gracefully on any parsing error.

        The fallback uses the deterministic recommendation titles and rationales
        directly — the result is still accurate, just not AI-narrated.
        """
        now = datetime.now(UTC)
        try:
            data = json.loads(content)
            return AnalyticsInsightOut(
                generated_at=now,
                executive_summary=str(data.get("executive_summary", "")),
                top_opportunities=[
                    InsightOpportunity(
                        title=str(opp.get("title", "")),
                        rationale=str(opp.get("rationale", "")),
                        confidence_level=str(opp.get("confidence_level", "low")),
                    )
                    for opp in data.get("top_opportunities", [])
                    if isinstance(opp, dict)
                ],
                risks=[
                    InsightRisk(
                        title=str(r.get("title", "")),
                        description=str(r.get("description", "")),
                    )
                    for r in data.get("risks", [])
                    if isinstance(r, dict)
                ],
                data_limitations=[
                    lim
                    for lim in data.get("data_limitations", [])
                    if isinstance(lim, str)
                ],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Deterministic fallback — surfaces recommendation data without AI narrative
            limitations: list[str] = []
            if recs.suppressed_count > 0:
                limitations.append(
                    f"{recs.suppressed_count} recommendation(s) are suppressed — "
                    "more data needed to activate them."
                )
            return AnalyticsInsightOut(
                generated_at=now,
                executive_summary=(
                    f"Based on {recs.total} active recommendation(s) "
                    f"covering the last {recs.period_days} days."
                ),
                top_opportunities=[
                    InsightOpportunity(
                        title=r.title,
                        rationale=r.rationale,
                        confidence_level=r.confidence_level,
                    )
                    for r in recs.recommendations[:5]
                ],
                risks=[],
                data_limitations=limitations,
            )

    async def get_insights(self, *, workspace_id: uuid.UUID) -> AnalyticsInsightOut:
        """Return AI narrative insights built on top of deterministic recommendations.

        Flow:
          1. Check Redis cache (4h TTL).
          2. Fetch deterministic recommendations via AnalyticsService.
          3. If empty: return a canned "insufficient data" response — no LLM call.
          4. Build prompt context (AI cannot see DB directly).
          5. Call EuriClient with task=analytics_narrative.
          6. Parse and validate the JSON response; fall back gracefully.
          7. Cache the result for 4 hours.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:insights"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return AnalyticsInsightOut.model_validate_json(cached)
        except Exception:
            pass

        # Step 2: deterministic recommendations (may hit their own 4h cache)
        recs = await AnalyticsService(self._session).get_recommendations(
            workspace_id=workspace_id
        )

        # Step 3: skip LLM when there is nothing to narrate
        if not recs.recommendations:
            limitations = []
            if recs.suppressed_count > 0:
                limitations.append(
                    f"{recs.suppressed_count} recommendation(s) are suppressed — "
                    "build more campaign data to unlock them."
                )
            limitations.append(
                "Run campaigns and record deal outcomes to generate meaningful insights."
            )
            out = AnalyticsInsightOut(
                generated_at=datetime.now(UTC),
                executive_summary=self._INSUFFICIENT_DATA_SUMMARY,
                top_opportunities=[],
                risks=[],
                data_limitations=limitations,
            )
        else:
            # Step 4-6: LLM narrative
            context = self._build_context(recs)
            try:
                result = await EuriClient(self._session).chat(
                    task="analytics_narrative",
                    prompt_name="analytics.analytics_narrative",
                    prompt_inputs={"recommendations_json": json.dumps(context, indent=2)},
                    tenant_id=ctx.org_id,
                    request_id=str(uuid.uuid4()),
                    agent="AnalyticsInsightService",
                )
                out = self._parse_response(result["content"], recs)
            except Exception as exc:
                log.warning(
                    "analytics.insights.llm_failed",
                    tenant_id=str(ctx.org_id),
                    workspace_id=str(workspace_id),
                    error=str(exc),
                )
                out = self._parse_response("", recs)  # triggers deterministic fallback

        # Step 7: cache
        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=14400)  # 4 h
        except Exception:
            pass

        log.info(
            "analytics.insights.generated",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            opportunities=len(out.top_opportunities),
            risks=len(out.risks),
            limitations=len(out.data_limitations),
        )
        return out


# ── Sprint 21 — Recommendation Effectiveness ─────────────────────────────────


class RecommendationEffectivenessService:
    """Handles trainer feedback on recommendations and quality score reads.

    submit_feedback: finds the most recent snapshot for (workspace, rec_type)
    within 7 days, upserts a feedback row, and invalidates the insights cache
    so the badge reflects new feedback within the next TTL window.

    get_effectiveness: reads pre-computed quality_scores rows and assembles
    the RecommendationEffectivenessOut response.  quality_score is NULL when
    total_feedback < 3 (low_confidence = True).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit_feedback(
        self,
        body: RecommendationFeedbackIn,
    ) -> RecommendationFeedbackOut:
        """Record trainer feedback for a recommendation type.

        Looks up the most recent snapshot for (workspace_id, rec_type) within
        the last 7 days so feedback always attaches to a real snapshot_id
        without requiring the client to know the UUID.
        """
        ctx = get_tenant_context()
        since = date.today() - timedelta(days=7)

        snapshot_repo = RecommendationSnapshotRepo(self._session)
        snapshot = await snapshot_repo.find_recent(
            workspace_id=body.workspace_id,
            rec_type=body.rec_type,
            since_date=since,
        )
        if snapshot is None:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail=(
                    f"No recent snapshot found for rec_type='{body.rec_type}' "
                    "in the last 7 days. "
                    "Generate recommendations first."
                ),
            )

        now = datetime.now(UTC)
        feedback_repo = RecommendationFeedbackRepo(self._session)
        await feedback_repo.upsert_feedback(
            tenant_id=ctx.org_id,
            workspace_id=body.workspace_id,
            snapshot_id=snapshot.id,
            rec_type=body.rec_type,
            outcome=body.outcome,
            notes=body.notes,
            recorded_at=now,
        )

        # Invalidate insights cache so the quality badge updates promptly
        try:
            insights_key = (
                f"t:{ctx.org_id}:{body.workspace_id}:analytics:insights"
            )
            await get_redis().delete(insights_key)
        except Exception:
            pass

        log.info(
            "analytics.recommendations.feedback_recorded",
            tenant_id=str(ctx.org_id),
            workspace_id=str(body.workspace_id),
            rec_type=body.rec_type,
            outcome=body.outcome,
            snapshot_id=str(snapshot.id),
        )
        return RecommendationFeedbackOut(
            snapshot_id=snapshot.id,
            rec_type=body.rec_type,
            outcome=body.outcome,
            recorded_at=now,
        )

    async def get_effectiveness(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 30,
    ) -> RecommendationEffectivenessOut:
        """Return quality score data for all rec_types in a workspace.

        Reads from recommendation_quality_scores (pre-computed by Celery beat).
        overall_quality_score is the average of non-None per-type quality scores;
        None when all types are low_confidence (not enough feedback yet).
        """
        ctx = get_tenant_context()
        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)

        repo = RecommendationQualityScoreRepo(self._session)
        rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=to_date,
        )

        # One quality item per rec_type — use the latest row when multiple dates exist
        latest: dict[str, RecommendationQualityScore] = {}
        for row in rows:
            if row.rec_type not in latest:
                latest[row.rec_type] = row

        by_type: list[RecommendationQualityItem] = [
            RecommendationQualityItem(
                rec_type=row.rec_type,
                shown_count=row.shown_count,
                acted_count=row.acted_count,
                success_count=row.success_count,
                ignored_count=row.ignored_count,
                feedback_helpful=row.feedback_helpful,
                feedback_not_helpful=row.feedback_not_helpful,
                feedback_dismissed=row.feedback_dismissed,
                adoption_rate=float(row.adoption_rate),
                success_rate=float(row.success_rate),
                quality_score=row.quality_score,
                low_confidence=row.low_confidence,
            )
            for row in latest.values()
        ]

        scored = [item.quality_score for item in by_type if item.quality_score is not None]
        overall = round(sum(scored) / len(scored)) if scored else None

        log.info(
            "analytics.recommendations.effectiveness_read",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_found=len(by_type),
            overall_quality_score=overall,
        )
        return RecommendationEffectivenessOut(
            workspace_id=str(workspace_id),
            period_days=period_days,
            generated_at=datetime.now(UTC),
            by_type=by_type,
            overall_quality_score=overall,
        )


# ── Sprint 22A — Recommendation Health Analytics ─────────────────────────────


class RecommendationAnalyticsService:
    """Exposes effectiveness and calibration views over Sprint 21 tracking data.

    get_effectiveness: aggregates recommendation_quality_scores into a summary
    block + per-type rows + trend series.  Reads pre-computed rows only —
    never computes in the request handler.

    get_calibration: compares predicted confidence (snapshot time) vs observed
    success rate (outcome time) per type and per confidence band.  All maths
    are deterministic; no LLM involved.

    Both methods are Redis-cached 1 hour per workspace.
    """

    _MIN_ACTED_FOR_CALIBRATION = 5

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── effectiveness ─────────────────────────────────────────────────────────

    async def get_effectiveness(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 30,
    ) -> RecEffectivenessOut:
        """Return adoption/success summary + per-type table + quality trend.

        Reads recommendation_quality_scores (pre-computed by Celery beat).
        Uses the latest row per rec_type as the authoritative current state;
        all rows in the period feed the quality_trend series.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:effectiveness"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecEffectivenessOut.model_validate_json(cached)
        except Exception:
            pass

        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)

        repo = RecommendationQualityScoreRepo(self._session)
        rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=to_date,
        )

        # latest row per rec_type → by_type table
        latest: dict[str, RecommendationQualityScore] = {}
        for row in rows:
            if row.rec_type not in latest:
                latest[row.rec_type] = row

        by_type: list[RecEffectivenessTypeItemOut] = [
            RecEffectivenessTypeItemOut(
                recommendation_type=r.rec_type,
                generated=r.shown_count,
                acted=r.acted_count,
                successful=r.success_count,
                adoption_rate=float(r.adoption_rate),
                success_rate=float(r.success_rate),
                quality_score=r.quality_score,
            )
            for r in latest.values()
        ]

        # cross-type summary totals
        total_generated = sum(t.generated for t in by_type)
        total_acted = sum(t.acted for t in by_type)
        total_successful = sum(t.successful for t in by_type)
        summary = RecEffectivenessSummaryOut(
            recommendations_generated=total_generated,
            recommendations_acted=total_acted,
            recommendations_successful=total_successful,
            adoption_rate=round(total_acted / total_generated, 4) if total_generated else 0.0,
            success_rate=round(total_successful / total_acted, 4) if total_acted else 0.0,
        )

        # quality trend — all rows ordered by date asc for the chart
        quality_trend: list[QualityTrendPointOut] = [
            QualityTrendPointOut(
                score_date=r.score_date,
                rec_type=r.rec_type,
                quality_score=r.quality_score,
                adoption_rate=float(r.adoption_rate),
                success_rate=float(r.success_rate),
            )
            for r in sorted(rows, key=lambda r: r.score_date)
        ]

        now = datetime.now(UTC)
        out = RecEffectivenessOut(
            generated_at=now,
            summary=summary,
            by_type=by_type,
            quality_trend=quality_trend,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)  # 1 h
        except Exception:
            pass

        log.info(
            "analytics.rec_health.effectiveness_computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_found=len(by_type),
            total_acted=total_acted,
        )
        return out

    # ── calibration ───────────────────────────────────────────────────────────

    async def get_calibration(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> RecCalibrationOut:
        """Return predicted vs observed confidence calibration.

        predicted_confidence = AVG(confidence_score) from recommendation_snapshots.
        observed_success_rate = (success_count / acted_count) × 100 from outcomes.
        calibration_delta = observed − predicted (negative → overconfident).

        overall: success rates grouped by the snapshot's confidence_level band.

        insufficient_data = True when total acted outcomes < 5 (not enough signal
        for meaningful calibration — frontend renders an empty state).
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:calibration"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecCalibrationOut.model_validate_json(cached)
        except Exception:
            pass

        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)
        tid = ctx.org_id

        # predicted_confidence: avg confidence_score per rec_type
        pred_result = await self._session.execute(
            text(
                "SELECT rec_type, AVG(confidence_score)::float AS avg_conf"
                " FROM recommendation_snapshots"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                "   AND snapshot_date >= :from_d AND snapshot_date <= :to_d"
                " GROUP BY rec_type"
            ),
            {"tid": tid, "wid": workspace_id, "from_d": from_date, "to_d": to_date},
        )
        predicted: dict[str, float] = {
            row[0]: round(float(row[1]), 2) for row in pred_result.all()
        }

        # observed success rates: join snapshots → outcomes per rec_type
        obs_result = await self._session.execute(
            text(
                "SELECT ro.rec_type,"
                "  COUNT(*) FILTER (WHERE ro.acted)           AS acted_count,"
                "  COUNT(*) FILTER (WHERE ro.success IS TRUE) AS success_count"
                " FROM recommendation_outcomes ro"
                " JOIN recommendation_snapshots rs ON ro.snapshot_id = rs.id"
                " WHERE ro.tenant_id = :tid AND ro.workspace_id = :wid"
                "   AND rs.snapshot_date >= :from_d AND rs.snapshot_date <= :to_d"
                " GROUP BY ro.rec_type"
            ),
            {"tid": tid, "wid": workspace_id, "from_d": from_date, "to_d": to_date},
        )
        observed_rows = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in obs_result.all()}

        total_acted = sum(v[0] for v in observed_rows.values())
        insufficient = total_acted < self._MIN_ACTED_FOR_CALIBRATION

        # per-type calibration items
        all_types = set(predicted) | set(observed_rows)
        rec_types: list[RecCalibrationTypeItemOut] = []
        for rt in sorted(all_types):
            pred_conf = predicted.get(rt)
            if pred_conf is None:
                continue
            acted_n, success_n = observed_rows.get(rt, (0, 0))
            obs_rate = round(success_n / acted_n * 100, 2) if acted_n else None
            delta = round(obs_rate - pred_conf, 2) if obs_rate is not None else None
            rec_types.append(
                RecCalibrationTypeItemOut(
                    recommendation_type=rt,
                    predicted_confidence=pred_conf,
                    observed_success_rate=obs_rate,
                    calibration_delta=delta,
                )
            )

        # overall by confidence band
        band_result = await self._session.execute(
            text(
                "SELECT rs.confidence_level,"
                "  COUNT(*) FILTER (WHERE ro.acted)           AS acted_count,"
                "  COUNT(*) FILTER (WHERE ro.success IS TRUE) AS success_count"
                " FROM recommendation_snapshots rs"
                " JOIN recommendation_outcomes ro ON ro.snapshot_id = rs.id"
                " WHERE rs.tenant_id = :tid AND rs.workspace_id = :wid"
                "   AND rs.snapshot_date >= :from_d AND rs.snapshot_date <= :to_d"
                " GROUP BY rs.confidence_level"
            ),
            {"tid": tid, "wid": workspace_id, "from_d": from_date, "to_d": to_date},
        )
        bands: dict[str, tuple[int, int]] = {}
        for row in band_result.all():
            bands[row[0]] = (int(row[1] or 0), int(row[2] or 0))

        def _band_rate(level: str) -> float | None:
            a, s = bands.get(level, (0, 0))
            return round(s / a * 100, 2) if a else None

        overall = RecCalibrationOverallOut(
            high_confidence_success_rate=_band_rate("high"),
            medium_confidence_success_rate=_band_rate("medium"),
            low_confidence_success_rate=_band_rate("low"),
        )

        now = datetime.now(UTC)
        out = RecCalibrationOut(
            generated_at=now,
            overall=overall,
            recommendation_types=rec_types,
            insufficient_data=insufficient,
            minimum_acted_recommendations=self._MIN_ACTED_FOR_CALIBRATION,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)  # 1 h
        except Exception:
            pass

        log.info(
            "analytics.rec_health.calibration_computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            total_acted=total_acted,
            insufficient_data=insufficient,
        )
        return out


# ── Sprint 22B — Recommendation Quality Review ───────────────────────────────


class RecommendationReviewService:
    """Sprint 22B observational review: top/bottom performers + calibration trifecta.

    All classification is deterministic — no AI, no LLM, no new tables.
    Reads recommendation_quality_scores (pre-computed by Celery beat) for
    performer rankings and quality trend; delegates calibration classification
    to RecommendationAnalyticsService.get_calibration() so the 22A calibration
    cache is reused on the first within-TTL call.

    Redis-cached 1 hour per workspace.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _classify_calibration(
        rec_types: list[RecCalibrationTypeItemOut],
    ) -> RecCalibrationGroupSummaryOut:
        """Classify rec_types into overconfident / underconfident / well_calibrated.

        Types with calibration_delta=None (no acted outcomes) are excluded.
        Rules (delta = observed_success_rate − predicted_confidence):
          delta <= -5  → overconfident  (confidence exceeded outcome)
          delta >= +5  → underconfident (outcome exceeded confidence)
          abs(delta) < 5 → well_calibrated
        """
        overconfident: list[RecCalibrationGroupItemOut] = []
        underconfident: list[RecCalibrationGroupItemOut] = []
        well_calibrated: list[RecCalibrationGroupItemOut] = []

        for item in rec_types:
            if item.calibration_delta is None:
                continue
            entry = RecCalibrationGroupItemOut(
                recommendation_type=item.recommendation_type,
                calibration_delta=item.calibration_delta,
            )
            if item.calibration_delta <= -5:
                overconfident.append(entry)
            elif item.calibration_delta >= 5:
                underconfident.append(entry)
            else:
                well_calibrated.append(entry)

        return RecCalibrationGroupSummaryOut(
            overconfident=overconfident,
            underconfident=underconfident,
            well_calibrated=well_calibrated,
        )

    async def get_review(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> RecReviewOut:
        """Return the recommendation quality review for a workspace.

        Performer rankings use the latest quality_score row per rec_type.
        best/worst only consider types with non-null quality_score (not low_confidence).
        most_ignored uses ignored_count / shown_count (types with shown_count=0 excluded).
        most_adopted / most_successful use adoption_rate / success_rate directly.
        calibration_summary delegates to RecommendationAnalyticsService.get_calibration()
        so the 22A calibration Redis cache is reused.
        quality_trend is the daily average of non-null quality_score values.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:review"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecReviewOut.model_validate_json(cached)
        except Exception:
            pass

        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)

        repo = RecommendationQualityScoreRepo(self._session)
        rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=to_date,
        )

        now = datetime.now(UTC)

        if not rows:
            out = RecReviewOut(
                generated_at=now,
                best_performing_type=None,
                worst_performing_type=None,
                most_ignored_type=None,
                most_adopted_type=None,
                most_successful_type=None,
                calibration_summary=RecCalibrationGroupSummaryOut(
                    overconfident=[],
                    underconfident=[],
                    well_calibrated=[],
                ),
                quality_trend=[],
                insufficient_data=True,
            )
            try:
                await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
            except Exception:
                pass
            return out

        # Latest row per rec_type (repo returns desc by score_date)
        latest: dict[str, RecommendationQualityScore] = {}
        for row in rows:
            if row.rec_type not in latest:
                latest[row.rec_type] = row

        # best / worst — only types with a non-null quality_score
        scored = {rt: r for rt, r in latest.items() if r.quality_score is not None}

        best_performing_type: RecBestWorstPerformerOut | None = None
        worst_performing_type: RecBestWorstPerformerOut | None = None
        if scored:
            best_rt = max(scored, key=lambda rt: scored[rt].quality_score)  # type: ignore[arg-type]
            worst_rt = min(scored, key=lambda rt: scored[rt].quality_score)  # type: ignore[arg-type]
            best_performing_type = RecBestWorstPerformerOut(
                recommendation_type=best_rt,
                quality_score=scored[best_rt].quality_score,  # type: ignore[arg-type]
            )
            worst_performing_type = RecBestWorstPerformerOut(
                recommendation_type=worst_rt,
                quality_score=scored[worst_rt].quality_score,  # type: ignore[arg-type]
            )

        # most ignored — highest ignored_count / shown_count (exclude shown=0)
        most_ignored_type: RecIgnoredTypeOut | None = None
        shown_rows = {rt: r for rt, r in latest.items() if r.shown_count > 0}
        if shown_rows:
            most_ignored_rt = max(
                shown_rows,
                key=lambda rt: shown_rows[rt].ignored_count / shown_rows[rt].shown_count,
            )
            r_ign = shown_rows[most_ignored_rt]
            most_ignored_type = RecIgnoredTypeOut(
                recommendation_type=most_ignored_rt,
                ignored_rate=round(r_ign.ignored_count / r_ign.shown_count, 4),
            )

        # most adopted — highest adoption_rate (exclude zero)
        most_adopted_type: RecAdoptedTypeOut | None = None
        adopted_rows = {rt: r for rt, r in latest.items() if float(r.adoption_rate) > 0}
        if adopted_rows:
            most_adopted_rt = max(
                adopted_rows,
                key=lambda rt: float(adopted_rows[rt].adoption_rate),
            )
            most_adopted_type = RecAdoptedTypeOut(
                recommendation_type=most_adopted_rt,
                adoption_rate=float(adopted_rows[most_adopted_rt].adoption_rate),
            )

        # most successful — highest success_rate (exclude zero)
        most_successful_type: RecSuccessfulTypeOut | None = None
        success_rows = {rt: r for rt, r in latest.items() if float(r.success_rate) > 0}
        if success_rows:
            most_successful_rt = max(
                success_rows,
                key=lambda rt: float(success_rows[rt].success_rate),
            )
            most_successful_type = RecSuccessfulTypeOut(
                recommendation_type=most_successful_rt,
                success_rate=float(success_rows[most_successful_rt].success_rate),
            )

        # calibration classification — delegates to 22A service (cache-friendly)
        calibration = await RecommendationAnalyticsService(self._session).get_calibration(
            workspace_id=workspace_id,
            period_days=period_days,
        )
        calibration_summary = self._classify_calibration(calibration.recommendation_types)

        # quality trend — daily average of non-null quality_score values
        trend_by_date: dict[date, list[int]] = {}
        for row in rows:
            if row.quality_score is not None:
                if row.score_date not in trend_by_date:
                    trend_by_date[row.score_date] = []
                trend_by_date[row.score_date].append(row.quality_score)

        quality_trend: list[RecReviewTrendPointOut] = [
            RecReviewTrendPointOut(
                date=d,
                quality_score=round(sum(scores) / len(scores), 2),
            )
            for d, scores in sorted(trend_by_date.items())
        ]

        out = RecReviewOut(
            generated_at=now,
            best_performing_type=best_performing_type,
            worst_performing_type=worst_performing_type,
            most_ignored_type=most_ignored_type,
            most_adopted_type=most_adopted_type,
            most_successful_type=most_successful_type,
            calibration_summary=calibration_summary,
            quality_trend=quality_trend,
            insufficient_data=False,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.rec_review.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_found=len(latest),
            trend_days=len(quality_trend),
        )
        return out


# ── Sprint 23A — Calibration Validation & Quality Score Stability ─────────────


class RecommendationCalibrationService:
    """Sprint 23A observational audit: confidence accuracy + quality stability.

    Measures the confidence model — does NOT modify it.

    get_calibration_review():
      Snapshot count by confidence level band, accuracy counts, per-type
      severity classification (calibrated / warning / severe).
      Delegates to RecommendationAnalyticsService.get_calibration() for the
      per-band success rates and per-type deltas (cache-friendly).

    get_stability():
      Population std_dev of quality_score over the period per rec_type.
      Classification: stable (<5) / volatile (5–15) / unstable (>15).

    Both Redis-cached 1 hour per workspace. No new tables. No AI.
    """

    _MIN_ACTED_FOR_CALIBRATION = 5

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _classify_severity(delta: float | None) -> str | None:
        """Map calibration delta to a severity label.

        None  → None  (no acted outcomes yet)
        abs < 5      → "calibrated"
        5 ≤ abs ≤ 15 → "warning"
        abs > 15     → "severe"
        """
        if delta is None:
            return None
        abs_delta = abs(delta)
        if abs_delta < 5:
            return "calibrated"
        if abs_delta <= 15:
            return "warning"
        return "severe"

    @staticmethod
    def _classify_stability(std_dev: float) -> str:
        """Map population std_dev of quality_score to a stability rating.

        std_dev < 5   → "stable"
        5 ≤ std_dev ≤ 15 → "volatile"
        std_dev > 15  → "unstable"
        """
        if std_dev < 5:
            return "stable"
        if std_dev <= 15:
            return "volatile"
        return "unstable"

    @staticmethod
    def _population_std_dev(values: list[int]) -> float:
        """Population standard deviation; 0.0 when fewer than 2 values."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return round(math.sqrt(variance), 2)

    async def get_calibration_review(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> CalibrationReviewOut:
        """Return confidence distribution, accuracy counts, and per-type severity.

        confidence_distribution: COUNT of recommendation_snapshots by confidence_level.
        overall:                 per-band success rates (delegated to 22A calibration).
        accuracy:                directional counts — well_calibrated / overconfident /
                                 underconfident — same sign thresholds as 22B trifecta.
        recommendation_types:    per-type with new severity label (calibrated/warning/severe).
        insufficient_data:       True when 22A calibration returns insufficient_data=True.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:calibration_review"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return CalibrationReviewOut.model_validate_json(cached)
        except Exception:
            pass

        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)
        tid = ctx.org_id
        now = datetime.now(UTC)

        # Confidence distribution — COUNT snapshots by band
        dist_result = await self._session.execute(
            text(
                "SELECT confidence_level, COUNT(*) AS cnt"
                " FROM recommendation_snapshots"
                " WHERE tenant_id = :tid AND workspace_id = :wid"
                "   AND snapshot_date >= :from_d AND snapshot_date <= :to_d"
                " GROUP BY confidence_level"
            ),
            {"tid": tid, "wid": workspace_id, "from_d": from_date, "to_d": to_date},
        )
        dist_map: dict[str, int] = {}
        for row in dist_result.all():
            dist_map[row[0]] = int(row[1] or 0)

        confidence_distribution = ConfidenceDistributionOut(
            high=dist_map.get("high", 0),
            medium=dist_map.get("medium", 0),
            low=dist_map.get("low", 0),
        )

        # Delegate to 22A calibration — reuses its Redis cache on warm hit
        calibration = await RecommendationAnalyticsService(self._session).get_calibration(
            workspace_id=workspace_id,
            period_days=period_days,
        )

        # Accuracy counts (sign-based, same as 22B trifecta thresholds)
        well_calibrated_count = 0
        overconfident_count = 0
        underconfident_count = 0
        for item in calibration.recommendation_types:
            if item.calibration_delta is None:
                continue
            if item.calibration_delta <= -5:
                overconfident_count += 1
            elif item.calibration_delta >= 5:
                underconfident_count += 1
            else:
                well_calibrated_count += 1

        accuracy = CalibrationAccuracyOut(
            well_calibrated_count=well_calibrated_count,
            overconfident_count=overconfident_count,
            underconfident_count=underconfident_count,
        )

        # Per-type items with severity classification
        rec_types_out: list[CalibrationReviewTypeItemOut] = [
            CalibrationReviewTypeItemOut(
                recommendation_type=item.recommendation_type,
                predicted_confidence=item.predicted_confidence,
                observed_success_rate=item.observed_success_rate,
                calibration_delta=item.calibration_delta,
                calibration_severity=self._classify_severity(item.calibration_delta),
            )
            for item in calibration.recommendation_types
        ]

        out = CalibrationReviewOut(
            generated_at=now,
            overall=calibration.overall,
            confidence_distribution=confidence_distribution,
            accuracy=accuracy,
            recommendation_types=rec_types_out,
            insufficient_data=calibration.insufficient_data,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.calibration_review.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            insufficient_data=calibration.insufficient_data,
            types_count=len(rec_types_out),
        )
        return out

    async def get_stability(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> StabilityOut:
        """Return population std_dev of quality_score per rec_type.

        Reads recommendation_quality_scores via the existing repo.
        Groups non-null quality_score values by rec_type; computes mean
        and population std_dev in Python — no extra SQL aggregation.
        insufficient_data: True when no rows exist at all in the period.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:stability"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return StabilityOut.model_validate_json(cached)
        except Exception:
            pass

        to_date = date.today()
        from_date = to_date - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        repo = RecommendationQualityScoreRepo(self._session)
        rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=to_date,
        )

        if not rows:
            out = StabilityOut(
                generated_at=now,
                quality_score_stability=QualityScoreStabilityOut(
                    average=0.0,
                    std_dev=0.0,
                    stability_rating="stable",
                ),
                recommendation_types=[],
                insufficient_data=True,
            )
            try:
                await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
            except Exception:
                pass
            return out

        # Group non-null quality_score values by rec_type
        scores_by_type: dict[str, list[int]] = {}
        for row in rows:
            if row.quality_score is not None:
                if row.rec_type not in scores_by_type:
                    scores_by_type[row.rec_type] = []
                scores_by_type[row.rec_type].append(row.quality_score)

        # Per-type stability items (sorted alphabetically for determinism)
        stability_items: list[StabilityTypeItemOut] = []
        for rec_type, scores in sorted(scores_by_type.items()):
            avg = round(sum(scores) / len(scores), 2)
            std = self._population_std_dev(scores)
            stability_items.append(
                StabilityTypeItemOut(
                    recommendation_type=rec_type,
                    average_quality_score=avg,
                    std_dev=std,
                    stability_rating=self._classify_stability(std),
                )
            )

        # Overall stability from all non-null quality_score values
        all_scores = [s for scores in scores_by_type.values() for s in scores]
        if all_scores:
            overall_avg = round(sum(all_scores) / len(all_scores), 2)
            overall_std = self._population_std_dev(all_scores)
        else:
            overall_avg = 0.0
            overall_std = 0.0

        out = StabilityOut(
            generated_at=now,
            quality_score_stability=QualityScoreStabilityOut(
                average=overall_avg,
                std_dev=overall_std,
                stability_rating=self._classify_stability(overall_std),
            ),
            recommendation_types=stability_items,
            insufficient_data=False,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.stability.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_count=len(stability_items),
        )
        return out


# ── Sprint 23B — Confidence Drift Detection & Recommendation Reliability ──────


class RecommendationDriftService:
    """Sprint 23B observational drift and reliability layer.

    Measures whether recommendation performance is improving, stable, or declining
    by comparing the current 30-day window against the prior 30-day window.
    Pure deterministic arithmetic — no AI, no LLM, no new tables.

    get_drift():
      Compares quality_score, adoption_rate, and success_rate across two equal
      periods.  Fetches a single 2× period batch and partitions in Python.
      insufficient_data = True when the previous window has zero rows
      (workspace needs ≥ 60 days of history to detect drift).

    get_reliability():
      Computes a reliability score per rec_type from current-period data:
        reliability_score = success_rate_pct × 0.5 + adoption_rate_pct × 0.3 + quality_score × 0.2
      All inputs scaled to 0–100; quality_score=None contributes 0.0.
      Rated: high (≥ 75), medium (50–74), low (< 50).

    Both Redis-cached 1 hour per workspace.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _classify_direction(change: float) -> str:
        """Map a metric change to a drift direction label.

        change > 5   → "improving"
        change < −5  → "declining"
        otherwise    → "stable"
        """
        if change > 5:
            return "improving"
        if change < -5:
            return "declining"
        return "stable"

    @staticmethod
    def _classify_reliability(score: float) -> str:
        """Map a reliability score to a rating label.

        score ≥ 75  → "high"
        score ≥ 50  → "medium"
        score < 50  → "low"
        """
        if score >= 75:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    @staticmethod
    def _period_averages(
        rows: list[RecommendationQualityScore],
    ) -> tuple[float, float, float]:
        """Return (avg_quality_score, avg_adoption_pct, avg_success_pct) for rows.

        quality_score: average over non-None values; 0.0 when all None.
        adoption_rate / success_rate: multiplied by 100 before averaging so all
        three metrics share a 0–100 scale for the drift threshold.
        """
        quality_values = [r.quality_score for r in rows if r.quality_score is not None]
        adoption_values = [float(r.adoption_rate) * 100 for r in rows]
        success_values = [float(r.success_rate) * 100 for r in rows]

        avg_quality = round(sum(quality_values) / len(quality_values), 2) if quality_values else 0.0
        avg_adoption = round(sum(adoption_values) / len(adoption_values), 2) if adoption_values else 0.0
        avg_success = round(sum(success_values) / len(success_values), 2) if success_values else 0.0

        return avg_quality, avg_adoption, avg_success

    @classmethod
    def _make_trend(cls, current: float, previous: float) -> MetricTrendOut:
        change = round(current - previous, 2)
        return MetricTrendOut(
            current=current,
            previous=previous,
            change=change,
            direction=cls._classify_direction(change),
        )

    async def get_drift(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 30,
    ) -> DriftOut:
        """Compare current vs previous period for quality, adoption, and success.

        One list_by_workspace() call covers the full 2× period; Python partitions
        it into current and previous windows — a single DB round trip.
        insufficient_data = True when the previous window has no rows.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:drift"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return DriftOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        current_end = today
        current_start = today - timedelta(days=period_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        repo = RecommendationQualityScoreRepo(self._session)
        all_rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=previous_start,
            to_date=current_end,
        )

        current_rows = [r for r in all_rows if r.score_date >= current_start]
        previous_rows = [r for r in all_rows if r.score_date <= previous_end]

        if not previous_rows:
            out = DriftOut(
                generated_at=now,
                overall=DriftOverallOut(
                    quality_score=MetricTrendOut(current=0.0, previous=0.0, change=0.0, direction="stable"),
                    adoption_rate=MetricTrendOut(current=0.0, previous=0.0, change=0.0, direction="stable"),
                    success_rate=MetricTrendOut(current=0.0, previous=0.0, change=0.0, direction="stable"),
                ),
                by_type=[],
                insufficient_data=True,
            )
            try:
                await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
            except Exception:
                pass
            return out

        curr_q, curr_a, curr_s = self._period_averages(current_rows)
        prev_q, prev_a, prev_s = self._period_averages(previous_rows)

        overall = DriftOverallOut(
            quality_score=self._make_trend(curr_q, prev_q),
            adoption_rate=self._make_trend(curr_a, prev_a),
            success_rate=self._make_trend(curr_s, prev_s),
        )

        all_types = sorted(set(r.rec_type for r in all_rows))
        by_type: list[DriftTypeItemOut] = []
        for rt in all_types:
            curr_t, _, _ = self._period_averages([r for r in current_rows if r.rec_type == rt])
            prev_t, _, _ = self._period_averages([r for r in previous_rows if r.rec_type == rt])
            by_type.append(
                DriftTypeItemOut(
                    recommendation_type=rt,
                    quality_score=self._make_trend(curr_t, prev_t),
                )
            )

        out = DriftOut(
            generated_at=now,
            overall=overall,
            by_type=by_type,
            insufficient_data=False,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.drift.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_found=len(all_types),
        )
        return out

    async def get_reliability(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 30,
    ) -> ReliabilityOut:
        """Compute recommendation reliability from current-period quality scores.

        Uses the latest row per rec_type within the period.
        Formula (all inputs on 0–100 scale):
          reliability_score = success_rate_pct × 0.5 + adoption_rate_pct × 0.3 + quality_score × 0.2
        quality_score = None (low_confidence) contributes 0.0 to the formula.
        overall_reliability.score is the mean reliability across all rec_types.
        insufficient_data = True when no rows exist in the period.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:reliability"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return ReliabilityOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        to_date = today
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        repo = RecommendationQualityScoreRepo(self._session)
        rows = await repo.list_by_workspace(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=to_date,
        )

        if not rows:
            out = ReliabilityOut(
                generated_at=now,
                overall_reliability=ReliabilityOverallOut(score=0.0, rating="low"),
                recommendation_types=[],
                insufficient_data=True,
            )
            try:
                await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
            except Exception:
                pass
            return out

        # Latest row per rec_type (repo returns desc by score_date)
        latest: dict[str, RecommendationQualityScore] = {}
        for row in rows:
            if row.rec_type not in latest:
                latest[row.rec_type] = row

        type_items: list[ReliabilityTypeItemOut] = []
        for rt, row in sorted(latest.items()):
            success_pct = float(row.success_rate) * 100
            adoption_pct = float(row.adoption_rate) * 100
            quality_pct = float(row.quality_score) if row.quality_score is not None else 0.0
            score = round(success_pct * 0.5 + adoption_pct * 0.3 + quality_pct * 0.2, 2)
            type_items.append(
                ReliabilityTypeItemOut(
                    recommendation_type=rt,
                    reliability_score=score,
                    rating=self._classify_reliability(score),
                )
            )

        overall_score = round(
            sum(t.reliability_score for t in type_items) / len(type_items), 2
        ) if type_items else 0.0

        out = ReliabilityOut(
            generated_at=now,
            overall_reliability=ReliabilityOverallOut(
                score=overall_score,
                rating=self._classify_reliability(overall_score),
            ),
            recommendation_types=type_items,
            insufficient_data=False,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.reliability.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            types_found=len(type_items),
            overall_score=overall_score,
        )
        return out


# ── Sprint 24A — Recommendation Lifecycle Observatory ─────────────────────────

#: Canonical order for decay age buckets — preserved in every response.
_DECAY_BUCKET_ORDER = ("0-7", "8-30", "31-60", "60+")


class RecommendationLifecycleService:
    """Sprint 24A observational lifecycle and decay layer.

    Measures how quickly recommendations are acted upon, how quickly they succeed,
    and how effectiveness decays with recommendation age.  Pure deterministic
    arithmetic — no AI, no LLM, no new tables.

    get_lifecycle():
      Reads recommendation_outcomes joined with recommendation_snapshots.
      Computes timing (avg_days_to_action, avg_days_to_success) and conversion
      rates (acted_rate, success_rate) overall and per rec_type.
      insufficient_data = True when no outcome rows exist in the period.

    get_decay():
      Buckets all outcome rows by (date.today() - snapshot_date).days into
      0–7, 8–30, 31–60, 60+ day brackets.
      Per-type decay_detected = True when best_success_rate - worst_success_rate ≥ 10
      (only types with outcomes in ≥ 2 non-empty buckets are included).

    Both Redis-cached 1 hour per workspace.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _classify_age_bucket(days: int) -> str:
        """Map recommendation age in days to a decay bucket label."""
        if days <= 7:
            return "0-7"
        if days <= 30:
            return "8-30"
        if days <= 60:
            return "31-60"
        return "60+"

    @staticmethod
    def _decay_detected(best_rate: float, worst_rate: float) -> bool:
        """True when best success_rate exceeds worst by >= 10 percentage points."""
        return (best_rate - worst_rate) >= 10.0

    @staticmethod
    def _compute_lifecycle_stats(
        rows: list[OutcomeWithTiming],
    ) -> tuple[float, float, float, float]:
        """Return (avg_days_to_action, avg_days_to_success, acted_rate_pct, success_rate_pct).

        Days values are derived from acted_at / success_measured_at minus
        snapshot.generated_at.  Both timestamps are timezone-aware; the resulting
        timedelta is converted to fractional days via total_seconds() / 86400.
        Rows where the required timestamp is None are excluded from the timing
        average but included in the rate denominator.
        """
        if not rows:
            return 0.0, 0.0, 0.0, 0.0

        total = len(rows)
        acted_with_ts = [r for r in rows if r.acted and r.acted_at is not None]
        success_with_ts = [r for r in rows if r.success is True and r.success_measured_at is not None]

        days_to_action = [
            (r.acted_at - r.snapshot_generated_at).total_seconds() / 86400  # type: ignore[operator]
            for r in acted_with_ts
        ]
        days_to_success = [
            (r.success_measured_at - r.snapshot_generated_at).total_seconds() / 86400  # type: ignore[operator]
            for r in success_with_ts
        ]

        avg_action = round(sum(days_to_action) / len(days_to_action), 2) if days_to_action else 0.0
        avg_success_d = round(sum(days_to_success) / len(days_to_success), 2) if days_to_success else 0.0
        acted_rate = round(len([r for r in rows if r.acted]) / total * 100, 2)
        success_rate = round(len([r for r in rows if r.success is True]) / total * 100, 2)

        return avg_action, avg_success_d, acted_rate, success_rate

    async def get_lifecycle(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> LifecycleOut:
        """Measure recommendation progression timing over the last period_days days.

        Single list_with_snapshot() call; Python partitions by rec_type.
        insufficient_data = True when no outcome rows exist in the period.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:lifecycle"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return LifecycleOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        repo = RecommendationOutcomeRepo(self._session)
        rows = await repo.list_with_snapshot(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=today,
        )

        if not rows:
            out = LifecycleOut(
                generated_at=now,
                overall=LifecycleOverallOut(
                    avg_days_to_action=0.0,
                    avg_days_to_success=0.0,
                    acted_rate=0.0,
                    success_rate=0.0,
                ),
                recommendation_types=[],
                insufficient_data=True,
            )
            try:
                await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
            except Exception:
                pass
            return out

        avg_a, avg_s, act_r, suc_r = self._compute_lifecycle_stats(rows)
        overall = LifecycleOverallOut(
            avg_days_to_action=avg_a,
            avg_days_to_success=avg_s,
            acted_rate=act_r,
            success_rate=suc_r,
        )

        all_types = sorted(set(r.rec_type for r in rows))
        type_items: list[LifecycleTypeItemOut] = []
        for rt in all_types:
            type_rows = [r for r in rows if r.rec_type == rt]
            t_a, t_s, t_ar, t_sr = self._compute_lifecycle_stats(type_rows)
            type_items.append(
                LifecycleTypeItemOut(
                    recommendation_type=rt,
                    avg_days_to_action=t_a,
                    avg_days_to_success=t_s,
                    acted_rate=t_ar,
                    success_rate=t_sr,
                )
            )

        out = LifecycleOut(
            generated_at=now,
            overall=overall,
            recommendation_types=type_items,
            insufficient_data=False,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.lifecycle.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            total_outcomes=len(rows),
            types_found=len(type_items),
        )
        return out

    async def get_decay(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 180,
    ) -> DecayOut:
        """Bucket recommendations by age and measure effectiveness per bracket.

        Age = date.today() - snapshot.snapshot_date (integer days).
        Always emits all 4 buckets in canonical order; empty buckets have sample_size=0.
        Per-type decay detection only includes types with outcomes in >= 2 non-empty buckets.
        decay_detected = True when best_success_rate - worst_success_rate >= 10 points.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:decay"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return DecayOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        repo = RecommendationOutcomeRepo(self._session)
        rows = await repo.list_with_snapshot(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=today,
        )

        # ── Build aggregate bucket counts ─────────────────────────────────────
        # bucket_data: {bucket_label: {acted, success, total}}
        bucket_data: dict[str, dict[str, int]] = {
            b: {"acted": 0, "success": 0, "total": 0} for b in _DECAY_BUCKET_ORDER
        }
        # type_bucket_data: {rec_type: {bucket_label: {acted, success, total}}}
        type_bucket_data: dict[str, dict[str, dict[str, int]]] = {}

        for row in rows:
            age_days = (today - row.snapshot_date).days
            bucket = self._classify_age_bucket(age_days)
            bucket_data[bucket]["total"] += 1
            if row.acted:
                bucket_data[bucket]["acted"] += 1
            if row.success is True:
                bucket_data[bucket]["success"] += 1

            if row.rec_type not in type_bucket_data:
                type_bucket_data[row.rec_type] = {
                    b: {"acted": 0, "success": 0, "total": 0} for b in _DECAY_BUCKET_ORDER
                }
            type_bucket_data[row.rec_type][bucket]["total"] += 1
            if row.acted:
                type_bucket_data[row.rec_type][bucket]["acted"] += 1
            if row.success is True:
                type_bucket_data[row.rec_type][bucket]["success"] += 1

        # ── Overall buckets ───────────────────────────────────────────────────
        buckets: list[DecayBucketOut] = []
        for b in _DECAY_BUCKET_ORDER:
            d = bucket_data[b]
            total = d["total"]
            acted_rate = round(d["acted"] / total * 100, 2) if total > 0 else 0.0
            success_rate = round(d["success"] / total * 100, 2) if total > 0 else 0.0
            buckets.append(
                DecayBucketOut(
                    age_bucket=b,
                    acted_rate=acted_rate,
                    success_rate=success_rate,
                    sample_size=total,
                )
            )

        # ── Per-type decay detection ──────────────────────────────────────────
        type_decay: list[DecayTypeItemOut] = []
        for rt in sorted(type_bucket_data):
            td = type_bucket_data[rt]
            non_empty = [
                (b, round(td[b]["success"] / td[b]["total"] * 100, 2))
                for b in _DECAY_BUCKET_ORDER
                if td[b]["total"] > 0
            ]
            if len(non_empty) < 2:
                # Cannot compare without at least 2 non-empty brackets
                continue
            best_b, best_rate = max(non_empty, key=lambda x: x[1])
            worst_b, worst_rate = min(non_empty, key=lambda x: x[1])
            type_decay.append(
                DecayTypeItemOut(
                    recommendation_type=rt,
                    best_bucket=best_b,
                    worst_bucket=worst_b,
                    decay_detected=self._decay_detected(best_rate, worst_rate),
                )
            )

        out = DecayOut(
            generated_at=now,
            buckets=buckets,
            recommendation_types=type_decay,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.decay.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            total_outcomes=len(rows),
            types_with_decay=len(type_decay),
        )
        return out


# ── Sprint 24B — Recommendation Portfolio & Coverage ─────────────────────────

_KNOWN_REC_TYPES: tuple[str, ...] = (
    "campaign",
    "channel",
    "industry",
    "pricing",
    "topic",
)
_PORTFOLIO_STALE_DAYS = 30


class RecommendationPortfolioService:
    """Sprint 24B observational portfolio and coverage analysis.

    Measures recommendation composition (distribution, Shannon entropy, balance)
    and coverage (which types have been generated, when, and whether they are stale).
    All calculations are pure deterministic Python — no AI, no new tables.
    Reads recommendation_snapshots and recommendation_outcomes only.
    Redis-cached 1 hour per workspace.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _shannon_entropy(counts: list[int]) -> float:
        """Return H = -Σ(pi × ln(pi)) for a list of counts.

        Returns 0.0 for empty lists or lists with a single non-zero entry.
        """
        total = sum(counts)
        if total == 0:
            return 0.0
        H = 0.0
        for c in counts:
            if c > 0:
                pi = c / total
                H -= pi * math.log(pi)
        return H

    @staticmethod
    def _normalize_entropy(H: float, n_types: int) -> float:
        """Normalize Shannon entropy to 0–100 scale.

        Divides by ln(n_types) — the maximum entropy for n equally-distributed
        types — then scales to 100.  Returns 0.0 when n_types <= 1.
        """
        if n_types <= 1:
            return 0.0
        H_max = math.log(n_types)
        if H_max == 0.0:
            return 0.0
        return round(H / H_max * 100, 2)

    @staticmethod
    def _balance_rating(diversity_index: float) -> str:
        """Classify a 0–100 diversity index into a balance rating.

        80–100 → excellent
        60–79  → good
        40–59  → moderate
        <40    → poor
        """
        if diversity_index >= 80:
            return "excellent"
        if diversity_index >= 60:
            return "good"
        if diversity_index >= 40:
            return "moderate"
        return "poor"

    async def get_portfolio(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> PortfolioOut:
        """Return recommendation composition for the workspace.

        Computes per-type count, percentage, acted/success rates, dominant/least-used
        types, and a Shannon-entropy-based diversity index.
        insufficient_data=True when no snapshot rows exist in the period.
        Redis-cached 1 hour.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:portfolio"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return PortfolioOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        snap_repo = RecommendationSnapshotRepo(self._session)
        outcome_repo = RecommendationOutcomeRepo(self._session)

        type_counts = await snap_repo.list_type_counts(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=today,
        )
        outcome_map = await outcome_repo.aggregate_by_type_for_period(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=today,
        )

        total = sum(c for _, c in type_counts)

        if total == 0:
            out = PortfolioOut(
                generated_at=now,
                total_recommendations=0,
                recommendation_types=[],
                dominant_type=None,
                least_used_type=None,
                portfolio_balance=PortfolioBalanceOut(
                    diversity_index=0.0,
                    balance_rating="poor",
                ),
                insufficient_data=True,
            )
        else:
            items: list[PortfolioTypeItemOut] = []
            for rt, cnt in type_counts:
                pct = round(cnt / total * 100, 2)
                total_out, acted, success = outcome_map.get(rt, (0, 0, 0))
                acted_rate = round(acted / total_out * 100, 2) if total_out else 0.0
                success_rate = round(success / total_out * 100, 2) if total_out else 0.0
                items.append(
                    PortfolioTypeItemOut(
                        recommendation_type=rt,
                        count=cnt,
                        percentage=pct,
                        acted_rate=acted_rate,
                        success_rate=success_rate,
                    )
                )

            counts_only = [i.count for i in items]
            H = self._shannon_entropy(counts_only)
            diversity_index = self._normalize_entropy(H, len(items))
            balance_rating = self._balance_rating(diversity_index)

            dominant_type = max(items, key=lambda i: i.count).recommendation_type
            least_used_type = min(items, key=lambda i: i.count).recommendation_type

            out = PortfolioOut(
                generated_at=now,
                total_recommendations=total,
                recommendation_types=items,
                dominant_type=dominant_type,
                least_used_type=least_used_type,
                portfolio_balance=PortfolioBalanceOut(
                    diversity_index=diversity_index,
                    balance_rating=balance_rating,
                ),
                insufficient_data=False,
            )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.portfolio.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            total_recommendations=out.total_recommendations,
            insufficient_data=out.insufficient_data,
        )
        return out

    async def get_coverage(
        self,
        *,
        workspace_id: uuid.UUID,
        period_days: int = 90,
    ) -> CoverageOut:
        """Return coverage status for all known recommendation types.

        For each type in _KNOWN_REC_TYPES, reports whether it has ever been
        generated, when it was last generated, and whether it is stale
        (days_since_last_generated > _PORTFOLIO_STALE_DAYS).
        period_days controls the count column only; staleness is based on all-time last seen.
        Redis-cached 1 hour.
        """
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:coverage"

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return CoverageOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)

        snap_repo = RecommendationSnapshotRepo(self._session)

        # period counts for the count column
        period_type_counts = await snap_repo.list_type_counts(
            workspace_id=workspace_id,
            from_date=from_date,
            to_date=today,
        )
        period_counts: dict[str, int] = dict(period_type_counts)

        # all-time latest snapshot_date per type for staleness
        latest_dates = await snap_repo.find_latest_snapshot_date_per_type(
            workspace_id=workspace_id,
        )

        coverage: list[CoverageItemOut] = []
        missing_types: list[str] = []
        stale_types: list[str] = []

        for rt in sorted(_KNOWN_REC_TYPES):
            last_date = latest_dates.get(rt)
            present = last_date is not None
            count = period_counts.get(rt, 0)
            days_since = (today - last_date).days if last_date is not None else None

            coverage.append(
                CoverageItemOut(
                    recommendation_type=rt,
                    present=present,
                    count=count,
                    last_generated_at=last_date,
                    days_since_last_generated=days_since,
                )
            )

            if not present:
                missing_types.append(rt)
            elif days_since is not None and days_since > _PORTFOLIO_STALE_DAYS:
                stale_types.append(rt)

        out = CoverageOut(
            generated_at=now,
            coverage=coverage,
            missing_types=missing_types,
            stale_types=stale_types,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.coverage.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            period_days=period_days,
            missing_types=len(missing_types),
            stale_types=len(stale_types),
        )
        return out


# ── Sprint 25A — Recommendation Evidence Explorer ────────────────────────────


class RecommendationEvidenceService:
    """Sprint 25A explainability layer for a single recommendation type.

    Pure orchestrator — delegates to all existing Sprint 21–24 analytics services
    and extracts the per-type slice.  No new tables, no new repo methods, no AI.

    All 7 upstream service calls hit Redis on a warm cache (1h TTL), making the
    evidence endpoint effectively a fan-in of 7 Redis reads + 3 indexed DB queries.
    Redis-cached 1 hour per (workspace, recommendation_type).
    """

    _VALID_REC_TYPES: frozenset[str] = frozenset(
        {"campaign", "channel", "industry", "pricing", "topic"}
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _coverage_status(cov_item: CoverageItemOut | None) -> str:
        """Derive coverage_status string from a CoverageItemOut row."""
        if cov_item is None or not cov_item.present:
            return "missing"
        if cov_item.days_since_last_generated is not None and cov_item.days_since_last_generated > 30:
            return "stale"
        return "healthy"

    @staticmethod
    def _calibration_status(delta: float | None) -> str | None:
        """Map calibration_delta to a severity label (same thresholds as Sprint 23A)."""
        if delta is None:
            return None
        abs_delta = abs(delta)
        if abs_delta < 5:
            return "calibrated"
        if abs_delta <= 15:
            return "warning"
        return "severe"

    async def get_evidence(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_type: str,
        period_days: int = 90,
    ) -> EvidenceOut:
        """Assemble evidence for a single recommendation type.

        Orchestrates 7 upstream services (all cached) and 3 repo queries.
        All service instances share the session — safe under asyncio's single-
        threaded cooperative scheduling.  Uses sequential awaits to avoid
        potential session-level serialization issues under DB pressure.
        """
        ctx = get_tenant_context()
        cache_key = (
            f"t:{ctx.org_id}:{workspace_id}:analytics:evidence:{recommendation_type}"
        )

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return EvidenceOut.model_validate_json(cached)
        except Exception:
            pass

        today = date.today()
        from_date = today - timedelta(days=period_days - 1)
        now = datetime.now(UTC)
        rt = recommendation_type

        # ── Upstream service calls (mostly Redis hits) ────────────────────────
        portfolio = await RecommendationPortfolioService(self._session).get_portfolio(
            workspace_id=workspace_id, period_days=period_days
        )
        coverage_out = await RecommendationPortfolioService(self._session).get_coverage(
            workspace_id=workspace_id, period_days=period_days
        )
        calibration = await RecommendationAnalyticsService(self._session).get_calibration(
            workspace_id=workspace_id, period_days=period_days
        )
        stability = await RecommendationCalibrationService(self._session).get_stability(
            workspace_id=workspace_id, period_days=period_days
        )
        drift = await RecommendationDriftService(self._session).get_drift(
            workspace_id=workspace_id, period_days=period_days
        )
        reliability = await RecommendationDriftService(self._session).get_reliability(
            workspace_id=workspace_id, period_days=period_days
        )
        lifecycle = await RecommendationLifecycleService(self._session).get_lifecycle(
            workspace_id=workspace_id, period_days=period_days
        )

        # ── Direct repo queries (3 indexed queries) ───────────────────────────
        snap_repo = RecommendationSnapshotRepo(self._session)
        qual_repo = RecommendationQualityScoreRepo(self._session)
        outcome_repo = RecommendationOutcomeRepo(self._session)

        generated_count = await snap_repo.count_by_workspace_type(
            workspace_id=workspace_id, rec_type=rt,
            from_date=from_date, to_date=today,
        )
        qual_rows = await qual_repo.list_by_workspace(
            workspace_id=workspace_id, from_date=from_date, to_date=today
        )
        outcome_map = await outcome_repo.aggregate_by_type_for_period(
            workspace_id=workspace_id, from_date=from_date, to_date=today
        )

        # ── Extract per-type slices ───────────────────────────────────────────

        # Quality score — latest row for this type (repo returns desc by score_date)
        quality_score: int | None = None
        for row in qual_rows:
            if row.rec_type == rt:
                quality_score = row.quality_score
                break

        # Acted / success rates
        total_out, acted_c, success_c = outcome_map.get(rt, (0, 0, 0))
        acted_rate = round(acted_c / total_out * 100, 2) if total_out else 0.0
        success_rate = round(success_c / total_out * 100, 2) if total_out else 0.0

        # Reliability
        rel_item = next(
            (i for i in reliability.recommendation_types if i.recommendation_type == rt), None
        )
        reliability_score = rel_item.reliability_score if rel_item else None
        reliability_rating = rel_item.rating if rel_item else None

        # Lifecycle timing
        lc_item = next(
            (i for i in lifecycle.recommendation_types if i.recommendation_type == rt), None
        )
        avg_days_to_action = lc_item.avg_days_to_action if lc_item else 0.0
        avg_days_to_success = lc_item.avg_days_to_success if lc_item else 0.0

        # Drift direction — quality_score direction for this type
        drift_item = next(
            (i for i in drift.by_type if i.recommendation_type == rt), None
        )
        drift_direction = drift_item.quality_score.direction if drift_item else None

        # Quality score stability
        stab_item = next(
            (i for i in stability.recommendation_types if i.recommendation_type == rt), None
        )
        stability_rating = stab_item.stability_rating if stab_item else None

        # Confidence average + calibration status
        cal_item = next(
            (i for i in calibration.recommendation_types if i.recommendation_type == rt), None
        )
        confidence_average = cal_item.predicted_confidence if cal_item else None
        calibration_status = self._calibration_status(
            cal_item.calibration_delta if cal_item else None
        )

        # Portfolio share
        port_item = next(
            (i for i in portfolio.recommendation_types if i.recommendation_type == rt), None
        )
        portfolio_percentage = port_item.percentage if port_item else 0.0

        # Coverage
        cov_item = next(
            (i for i in coverage_out.coverage if i.recommendation_type == rt), None
        )
        last_generated_at = cov_item.last_generated_at if cov_item else None
        days_since_last_generated = cov_item.days_since_last_generated if cov_item else None
        coverage_status = self._coverage_status(cov_item)

        # Insufficient data: no snapshots in period AND never been generated
        insufficient_data = generated_count == 0 and last_generated_at is None

        summary = EvidenceSummaryOut(
            generated_count=generated_count,
            portfolio_percentage=portfolio_percentage,
            confidence_average=confidence_average,
            quality_score=quality_score,
            acted_rate=acted_rate,
            success_rate=success_rate,
            reliability_score=reliability_score,
            reliability_rating=reliability_rating,
            avg_days_to_action=avg_days_to_action,
            avg_days_to_success=avg_days_to_success,
            drift_direction=drift_direction,
            stability_rating=stability_rating,
            calibration_status=calibration_status,
            coverage_status=coverage_status,
            last_generated_at=last_generated_at,
            days_since_last_generated=days_since_last_generated,
        )

        supporting_metrics: list[EvidenceMetricOut] = [
            EvidenceMetricOut(
                name="Quality Score",
                value=float(quality_score) if quality_score is not None else None,
                source="recommendation_quality_scores",
            ),
            EvidenceMetricOut(
                name="Success Rate",
                value=round(success_rate, 2),
                source="recommendation_outcomes",
            ),
            EvidenceMetricOut(
                name="Acted Rate",
                value=round(acted_rate, 2),
                source="recommendation_outcomes",
            ),
            EvidenceMetricOut(
                name="Reliability Score",
                value=reliability_score,
                source="recommendation_quality_scores",
            ),
            EvidenceMetricOut(
                name="Confidence Average",
                value=confidence_average,
                source="recommendation_snapshots",
            ),
            EvidenceMetricOut(
                name="Portfolio Share",
                value=round(portfolio_percentage, 2),
                source="recommendation_snapshots",
            ),
            EvidenceMetricOut(
                name="Avg Days to Action",
                value=avg_days_to_action,
                source="recommendation_outcomes",
            ),
            EvidenceMetricOut(
                name="Avg Days to Success",
                value=avg_days_to_success,
                source="recommendation_outcomes",
            ),
            EvidenceMetricOut(
                name="Generated Count",
                value=float(generated_count),
                source="recommendation_snapshots",
            ),
        ]

        out = EvidenceOut(
            generated_at=now,
            recommendation_type=rt,
            summary=summary,
            supporting_metrics=supporting_metrics,
            insufficient_data=insufficient_data,
        )

        try:
            await get_redis().set(cache_key, out.model_dump_json(), ex=3600)
        except Exception:
            pass

        log.info(
            "analytics.evidence.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_type=rt,
            period_days=period_days,
            generated_count=generated_count,
            insufficient_data=insufficient_data,
        )
        return out


# ── Sprint 25B — Recommendation Action Center ────────────────────────────────

_ACTION_CACHE_TTL = 300  # 5 minutes — action list changes frequently


class RecommendationActionService:
    """Records and retrieves trainer-initiated actions on recommendations.

    accept / dismiss / snooze create or replace a recommendation_actions row.
    list_actions groups all rows by status, computing 'expired' at read time
    (snoozed rows whose snooze_until < today) without a background job.

    No automatic work is triggered by any action — human execution only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_status(row: "RecommendationAction") -> str:  # type: ignore[name-defined]
        from datetime import date as _date

        if row.action_type == "snoozed" and row.snooze_until is not None:
            if row.snooze_until <= _date.today():
                return "expired"
        return row.action_type

    def _to_out(self, row: "RecommendationAction") -> "RecommendationActionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import RecommendationActionOut

        return RecommendationActionOut(
            id=row.id,
            recommendation_id=row.recommendation_id,
            action_type=row.action_type,
            status=self._compute_status(row),
            reason=row.reason,
            snooze_until=row.snooze_until,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _validate_snapshot(
        self,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> None:
        from corpmind.modules.analytics.repo import RecommendationSnapshotRepo

        snap = await RecommendationSnapshotRepo(self._session).find_by_id(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
        if snap is None:
            raise ValueError(f"recommendation {recommendation_id} not found")

    async def _invalidate_cache(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        cache_key = f"t:{org_id}:{workspace_id}:analytics:recommendation_actions"
        try:
            await get_redis().delete(cache_key)
        except Exception:
            pass

    # ── public ────────────────────────────────────────────────────────────────

    async def accept(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> "AcceptOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import AcceptOut
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        await self._validate_snapshot(workspace_id, recommendation_id)
        row = await RecommendationActionRepo(self._session).upsert(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            action_type="accepted",
            reason=None,
            snooze_until=None,
        )
        await self._invalidate_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.action.accepted",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return AcceptOut(
            status="accepted",
            accepted_at=row.updated_at,
            recommendation_id=recommendation_id,
        )

    async def dismiss(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        reason: str | None,
    ) -> "RecommendationActionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        await self._validate_snapshot(workspace_id, recommendation_id)
        row = await RecommendationActionRepo(self._session).upsert(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            action_type="dismissed",
            reason=reason,
            snooze_until=None,
        )
        await self._invalidate_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.action.dismissed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return self._to_out(row)

    async def snooze(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        until: "date",  # type: ignore[name-defined]
    ) -> "RecommendationActionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        await self._validate_snapshot(workspace_id, recommendation_id)
        row = await RecommendationActionRepo(self._session).upsert(
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            action_type="snoozed",
            reason=None,
            snooze_until=until,
        )
        await self._invalidate_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.action.snoozed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
            snooze_until=str(until),
        )
        return self._to_out(row)

    async def list_actions(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> "RecommendationActionsListOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import RecommendationActionsListOut
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:recommendation_actions"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecommendationActionsListOut.model_validate_json(cached)
        except Exception:
            pass

        rows = await RecommendationActionRepo(self._session).list_by_workspace(
            workspace_id=workspace_id,
        )

        buckets: dict[str, list] = {
            "accepted": [],
            "dismissed": [],
            "snoozed": [],
            "completed": [],
            "expired": [],
        }
        for row in rows:
            status = self._compute_status(row)
            out = self._to_out(row)
            buckets[status].append(out)

        result = RecommendationActionsListOut(
            accepted=buckets["accepted"],
            dismissed=buckets["dismissed"],
            snoozed=buckets["snoozed"],
            completed=buckets["completed"],
            expired=buckets["expired"],
            total=len(rows),
        )
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_ACTION_CACHE_TTL)
        except Exception:
            pass
        return result


# ── Sprint 26A — Recommendation Work Queue ────────────────────────────────────

_QUEUE_CACHE_TTL = 300  # 5 minutes — same as action cache

# Valid execution_status transitions.  None means "accepted but not started yet".
_VALID_TRANSITIONS: dict[str | None, list[str]] = {
    None: ["in_progress", "cancelled"],
    "in_progress": ["completed", "blocked"],
    "blocked": ["in_progress", "cancelled"],
    "completed": [],
    "cancelled": [],
}


class RecommendationExecutionService:
    """Manages the execution workflow for accepted recommendations.

    Transitions: accepted(None) → in_progress → completed (terminal)
                 in_progress → blocked → in_progress → completed
                 accepted(None)/blocked → cancelled (terminal)

    No automatic work is triggered — every transition is trainer-initiated.
    Starting, blocking, completing, or cancelling never launches campaigns,
    sends messages, modifies CRM records, or updates analytics metrics.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def validate_transition(current: str | None, target: str) -> None:
        allowed = _VALID_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise ValueError(
                f"invalid transition: {current!r} → {target!r}; "
                f"allowed from {current!r}: {allowed}"
            )

    @staticmethod
    def _to_execution_out(row: "RecommendationAction") -> "ExecutionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import ExecutionOut

        return ExecutionOut(
            recommendation_id=row.recommendation_id,
            action_type=row.action_type,
            execution_status=row.execution_status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            blocked_at=row.blocked_at,
            cancelled_at=row.cancelled_at,
            blocked_reason=row.blocked_reason,
            completion_notes=row.completion_notes,
        )

    @staticmethod
    def _to_queue_item(
        row: "RecommendationAction",  # type: ignore[name-defined]
        title: str,
    ) -> "WorkQueueGroupOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import WorkQueueGroupOut

        return WorkQueueGroupOut(
            recommendation_id=row.recommendation_id,
            title=title,
            action_type=row.action_type,
            execution_status=row.execution_status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            blocked_at=row.blocked_at,
            cancelled_at=row.cancelled_at,
            blocked_reason=row.blocked_reason,
            completion_notes=row.completion_notes,
            accepted_at=row.created_at,
        )

    async def _require_accepted_row(
        self,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> "RecommendationAction":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        row = await RecommendationActionRepo(self._session).find_by_recommendation(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
        if row is None or row.action_type != "accepted":
            raise ValueError(
                f"recommendation {recommendation_id} has not been accepted"
            )
        return row

    async def _invalidate_queue_cache(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        cache_key = f"t:{org_id}:{workspace_id}:analytics:recommendation_work_queue"
        try:
            await get_redis().delete(cache_key)
        except Exception:
            pass

    # ── public ────────────────────────────────────────────────────────────────

    async def start(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> "ExecutionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        row = await self._require_accepted_row(workspace_id, recommendation_id)
        self.validate_transition(row.execution_status, "in_progress")
        now = datetime.now(UTC)
        updated = await RecommendationActionRepo(self._session).update_execution(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            fields={"execution_status": "in_progress", "started_at": now},
        )
        assert updated is not None
        await self._invalidate_queue_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.execution.started",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return self._to_execution_out(updated)

    async def block(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        reason: str,
    ) -> "ExecutionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        row = await self._require_accepted_row(workspace_id, recommendation_id)
        self.validate_transition(row.execution_status, "blocked")
        now = datetime.now(UTC)
        updated = await RecommendationActionRepo(self._session).update_execution(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            fields={
                "execution_status": "blocked",
                "blocked_at": now,
                "blocked_reason": reason,
            },
        )
        assert updated is not None
        await self._invalidate_queue_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.execution.blocked",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return self._to_execution_out(updated)

    async def complete(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        notes: str | None,
    ) -> "ExecutionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        row = await self._require_accepted_row(workspace_id, recommendation_id)
        self.validate_transition(row.execution_status, "completed")
        now = datetime.now(UTC)
        updated = await RecommendationActionRepo(self._session).update_execution(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            fields={
                "execution_status": "completed",
                "completed_at": now,
                "completion_notes": notes,
            },
        )
        assert updated is not None
        await self._invalidate_queue_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.execution.completed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return self._to_execution_out(updated)

    async def cancel(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        reason: str | None,
    ) -> "ExecutionOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        ctx = get_tenant_context()
        row = await self._require_accepted_row(workspace_id, recommendation_id)
        self.validate_transition(row.execution_status, "cancelled")
        now = datetime.now(UTC)
        updated = await RecommendationActionRepo(self._session).update_execution(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            fields={
                "execution_status": "cancelled",
                "cancelled_at": now,
                "blocked_reason": reason,  # reuse blocked_reason as cancel_reason
            },
        )
        assert updated is not None
        await self._invalidate_queue_cache(ctx.org_id, workspace_id)
        log.info(
            "analytics.execution.cancelled",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            recommendation_id=str(recommendation_id),
        )
        return self._to_execution_out(updated)

    async def list_queue(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> "WorkQueueOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import WorkQueueOut
        from corpmind.modules.analytics.repo import (
            RecommendationActionRepo,
            RecommendationSnapshotRepo,
        )

        ctx = get_tenant_context()
        cache_key = (
            f"t:{ctx.org_id}:{workspace_id}:analytics:recommendation_work_queue"
        )
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return WorkQueueOut.model_validate_json(cached)
        except Exception:
            pass

        # Only accepted rows participate in the work queue
        all_rows = await RecommendationActionRepo(self._session).list_by_workspace(
            workspace_id=workspace_id,
        )
        accepted_rows = [r for r in all_rows if r.action_type == "accepted"]

        # Build a title lookup from snapshot IDs
        snap_repo = RecommendationSnapshotRepo(self._session)
        titles: dict[uuid.UUID, str] = {}
        for row in accepted_rows:
            snap = await snap_repo.find_by_id(
                workspace_id=workspace_id,
                recommendation_id=row.recommendation_id,
            )
            titles[row.recommendation_id] = snap.title if snap else str(row.recommendation_id)

        buckets: dict[str, list] = {
            "ready": [],
            "in_progress": [],
            "blocked": [],
            "completed": [],
            "cancelled": [],
        }
        for row in accepted_rows:
            item = self._to_queue_item(row, titles.get(row.recommendation_id, ""))
            status = row.execution_status or "ready"
            buckets[status].append(item)

        # Timeline: all non-ready rows, newest updated_at first
        timeline = sorted(
            [r for r in accepted_rows if r.execution_status is not None],
            key=lambda r: r.updated_at,
            reverse=True,
        )
        timeline_items = [
            self._to_queue_item(r, titles.get(r.recommendation_id, ""))
            for r in timeline
        ]

        result = WorkQueueOut(
            ready=buckets["ready"],
            in_progress=buckets["in_progress"],
            blocked=buckets["blocked"],
            completed=buckets["completed"],
            cancelled=buckets["cancelled"],
            timeline=timeline_items,
            total=len(accepted_rows),
        )
        try:
            await get_redis().set(
                cache_key, result.model_dump_json(), ex=_QUEUE_CACHE_TTL
            )
        except Exception:
            pass
        return result


# ── Sprint 26B — Recommendation Outcome Tracking ─────────────────────────────

_OVERDUE_THRESHOLD_DAYS = 14
_OUTCOME_CACHE_TTL = 300


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


class RecommendationOutcomeService:
    """Read-only analytics layer measuring what happened after recommendation acceptance.

    All metrics are derived deterministically from execution timestamps on
    recommendation_actions rows.  This service NEVER starts work, completes work,
    cancels work, modifies CRM records, creates campaigns, or sends messages.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_accepted_rows(
        self, workspace_id: uuid.UUID
    ) -> "list[RecommendationAction]":  # type: ignore[name-defined]
        from corpmind.modules.analytics.repo import RecommendationActionRepo

        all_rows = await RecommendationActionRepo(self._session).list_by_workspace(
            workspace_id=workspace_id,
        )
        return [r for r in all_rows if r.action_type == "accepted"]

    async def get_execution_summary(
        self, workspace_id: uuid.UUID
    ) -> "ExecutionSummaryOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import ExecutionSummaryOut

        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:execution_summary"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return ExecutionSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        rows = await self._get_accepted_rows(workspace_id)
        now = datetime.now(UTC)
        accepted = len(rows)

        completed_rows = [r for r in rows if r.execution_status == "completed"]
        blocked_rows = [r for r in rows if r.execution_status == "blocked"]
        cancelled_rows = [r for r in rows if r.execution_status == "cancelled"]
        in_progress_rows = [r for r in rows if r.execution_status == "in_progress"]
        started_rows = [r for r in rows if r.started_at is not None]

        overdue_count = len(
            [
                r
                for r in in_progress_rows
                if r.started_at
                and (now - r.started_at).days >= _OVERDUE_THRESHOLD_DAYS
            ]
        )

        completion_rate = len(completed_rows) / accepted if accepted > 0 else 0.0
        cancellation_rate = len(cancelled_rows) / accepted if accepted > 0 else 0.0
        block_rate = len(blocked_rows) / accepted if accepted > 0 else 0.0

        days_to_start = [
            (r.started_at - r.created_at).total_seconds() / 86400
            for r in started_rows
            if r.started_at
        ]
        days_to_complete = [
            (r.completed_at - r.started_at).total_seconds() / 86400
            for r in completed_rows
            if r.completed_at and r.started_at
        ]

        blocked_durations: list[float] = []
        for r in rows:
            if r.blocked_at:
                if r.execution_status == "blocked":
                    blocked_durations.append(
                        (now - r.blocked_at).total_seconds() / 86400
                    )
                elif r.execution_status == "completed" and r.completed_at:
                    blocked_durations.append(
                        (r.completed_at - r.blocked_at).total_seconds() / 86400
                    )

        days_cancelled = [
            (r.cancelled_at - r.created_at).total_seconds() / 86400
            for r in cancelled_rows
            if r.cancelled_at
        ]

        result = ExecutionSummaryOut(
            accepted=accepted,
            started=len(started_rows),
            completed=len(completed_rows),
            blocked=len(blocked_rows),
            cancelled=len(cancelled_rows),
            completion_rate=round(completion_rate, 4),
            cancellation_rate=round(cancellation_rate, 4),
            block_rate=round(block_rate, 4),
            avg_days_to_start=round(_mean(days_to_start), 2),
            avg_days_to_complete=round(_mean(days_to_complete), 2),
            avg_days_blocked=round(_mean(blocked_durations), 2),
            avg_days_cancelled=round(_mean(days_cancelled), 2),
            work_in_progress=len(in_progress_rows),
            overdue=overdue_count,
            insufficient_data=accepted < 5,
        )
        try:
            await get_redis().set(
                cache_key, result.model_dump_json(), ex=_OUTCOME_CACHE_TTL
            )
        except Exception:
            pass
        log.info(
            "analytics.outcomes.execution_summary",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            accepted=accepted,
            completed=len(completed_rows),
        )
        return result

    async def get_outcomes(
        self, workspace_id: uuid.UUID
    ) -> "RecommendationOutcomesOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import RecommendationOutcomesOut, OutcomeTypeItemOut
        from corpmind.modules.analytics.repo import RecommendationSnapshotRepo

        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:recommendation_outcomes"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RecommendationOutcomesOut.model_validate_json(cached)
        except Exception:
            pass

        rows = await self._get_accepted_rows(workspace_id)
        snap_repo = RecommendationSnapshotRepo(self._session)

        rec_types: dict[uuid.UUID, str] = {}
        for row in rows:
            snap = await snap_repo.find_by_id(
                workspace_id=workspace_id,
                recommendation_id=row.recommendation_id,
            )
            rec_types[row.recommendation_id] = snap.rec_type if snap else "unknown"

        completed_count = len([r for r in rows if r.execution_status == "completed"])
        blocked_count = len([r for r in rows if r.execution_status == "blocked"])
        cancelled_count = len([r for r in rows if r.execution_status == "cancelled"])
        in_progress_count = len([r for r in rows if r.execution_status == "in_progress"])
        ready_count = len([r for r in rows if r.execution_status is None])

        type_groups: dict[str, list] = {}
        for row in rows:
            rt = rec_types[row.recommendation_id]
            type_groups.setdefault(rt, []).append(row)

        by_rec_type: list[OutcomeTypeItemOut] = []
        for rt, type_rows in sorted(type_groups.items()):
            accepted_n = len(type_rows)
            completed_n = len([r for r in type_rows if r.execution_status == "completed"])
            cancelled_n = len([r for r in type_rows if r.execution_status == "cancelled"])
            blocked_n = len([r for r in type_rows if r.execution_status == "blocked"])
            completion_rate_t = completed_n / accepted_n if accepted_n > 0 else 0.0

            t_days_to_complete = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in type_rows
                if r.execution_status == "completed" and r.completed_at and r.started_at
            ]
            t_days_to_start = [
                (r.started_at - r.created_at).total_seconds() / 86400
                for r in type_rows
                if r.started_at
            ]

            by_rec_type.append(
                OutcomeTypeItemOut(
                    rec_type=rt,
                    accepted=accepted_n,
                    completed=completed_n,
                    cancelled=cancelled_n,
                    blocked=blocked_n,
                    completion_rate=round(completion_rate_t, 4),
                    avg_days_to_complete=round(_mean(t_days_to_complete), 2),
                    avg_days_to_start=round(_mean(t_days_to_start), 2),
                )
            )

        result = RecommendationOutcomesOut(
            completed=completed_count,
            blocked=blocked_count,
            cancelled=cancelled_count,
            in_progress=in_progress_count,
            ready=ready_count,
            by_rec_type=by_rec_type,
            insufficient_data=len(rows) < 5,
        )
        try:
            await get_redis().set(
                cache_key, result.model_dump_json(), ex=_OUTCOME_CACHE_TTL
            )
        except Exception:
            pass
        log.info(
            "analytics.outcomes.get_outcomes",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            accepted=len(rows),
            types=len(by_rec_type),
        )
        return result


# ── Sprint 27 — Recommendation Learning & Versioning ─────────────────────────

_LEARNING_CACHE_TTL = 3600          # 1 hour — versions change at most daily
_LEARNING_MIN_VERSIONS = 2          # need ≥ 2 epochs to compute a delta
_QUALITY_MATCH_WINDOW_DAYS = 7      # days before snapshot_date to look for quality score


class RecommendationLearningService:
    """Read-only analytics layer comparing recommendation performance across versions.

    A "version" is one recommendation generation epoch, identified by snapshot_date.
    Each call to get_recommendations() that produces snapshots creates a new epoch.
    No AI, no writes, no recommendation generation changes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_delta(current: float | None, previous: float | None) -> float | None:
        if current is None or previous is None:
            return None
        return round(current - previous, 2)

    @staticmethod
    def _adoption_rate(acted: int, generated: int) -> float | None:
        if generated == 0:
            return None
        return round(acted / generated * 100, 2)

    @staticmethod
    def _success_rate(successful: int, acted: int) -> float | None:
        if acted == 0:
            return None
        return round(successful / acted * 100, 2)

    @staticmethod
    def _execution_rate(successful: int, generated: int) -> float | None:
        if generated == 0:
            return None
        return round(successful / generated * 100, 2)

    @classmethod
    def _compare_versions(
        cls,
        current: "LearningVersionOut",  # type: ignore[name-defined]
        previous: "LearningVersionOut",  # type: ignore[name-defined]
    ) -> "LearningComparisonOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import LearningComparisonOut

        return LearningComparisonOut(
            quality_delta=cls._compute_delta(current.quality_score, previous.quality_score),
            success_delta=cls._compute_delta(
                cls._success_rate(current.successful, current.acted),
                cls._success_rate(previous.successful, previous.acted),
            ),
            confidence_delta=cls._compute_delta(current.avg_confidence, previous.avg_confidence),
            adoption_delta=cls._compute_delta(
                cls._adoption_rate(current.acted, current.recommendations_generated),
                cls._adoption_rate(previous.acted, previous.recommendations_generated),
            ),
            execution_delta=cls._compute_delta(
                cls._execution_rate(current.successful, current.recommendations_generated),
                cls._execution_rate(previous.successful, previous.recommendations_generated),
            ),
        )

    @staticmethod
    def _build_summary(
        comparison: "LearningComparisonOut | None",  # type: ignore[name-defined]
    ) -> "LearningSummaryOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import LearningSummaryOut

        if comparison is None:
            return LearningSummaryOut(lines=["Insufficient data to compare versions."])

        lines: list[str] = []

        q = comparison.quality_delta
        if q is not None:
            if q >= 5:
                lines.append(f"Quality improved by {q:.0f} points.")
            elif q <= -5:
                lines.append(f"Quality declined by {abs(q):.0f} points.")
            else:
                lines.append("Quality unchanged.")

        a = comparison.adoption_delta
        if a is not None:
            if a >= 5:
                lines.append(f"Adoption increased by {a:.1f}%.")
            elif a <= -5:
                lines.append(f"Adoption decreased by {abs(a):.1f}%.")
            else:
                lines.append("Adoption unchanged.")

        s = comparison.success_delta
        if s is not None:
            if s >= 5:
                lines.append(f"Success rate improved by {s:.1f}%.")
            elif s <= -5:
                lines.append(f"Success rate declined by {abs(s):.1f}%.")
            else:
                lines.append("Success rate stable.")

        c = comparison.confidence_delta
        if c is not None:
            if c >= 3:
                lines.append("Confidence increased slightly.")
            elif c <= -3:
                lines.append("Confidence decreased slightly.")

        if not lines:
            lines = ["All metrics stable across versions."]

        return LearningSummaryOut(lines=lines)

    # ── private data loader ───────────────────────────────────────────────────

    async def _load_version_rows(
        self,
        workspace_id: uuid.UUID,
    ) -> "list[LearningVersionOut]":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import LearningVersionOut
        from corpmind.modules.analytics.repo import (
            RecommendationOutcomeRepo,
            RecommendationQualityScoreRepo,
            RecommendationSnapshotRepo,
        )

        snap_repo = RecommendationSnapshotRepo(self._session)
        outcome_repo = RecommendationOutcomeRepo(self._session)
        quality_repo = RecommendationQualityScoreRepo(self._session)

        versions_raw = await snap_repo.list_versions(workspace_id=workspace_id)
        outcome_map = await outcome_repo.aggregate_by_version(workspace_id=workspace_id)
        quality_map = await quality_repo.aggregate_by_version(workspace_id=workspace_id)

        result: list[LearningVersionOut] = []
        for snap_date, generated, avg_conf in versions_raw:
            acted, successful = outcome_map.get(snap_date, (0, 0))
            # Use quality score from the same date; fall back to nearest within window
            quality: float | None = quality_map.get(snap_date)
            if quality is None:
                for delta_days in range(1, _QUALITY_MATCH_WINDOW_DAYS + 1):
                    candidate = snap_date - timedelta(days=delta_days)
                    if candidate in quality_map:
                        quality = quality_map[candidate]
                        break

            result.append(
                LearningVersionOut(
                    version=snap_date.isoformat(),
                    first_seen=snap_date,
                    last_seen=snap_date,
                    recommendations_generated=generated,
                    acted=acted,
                    completed=successful,   # outcome.success = True → completed/successful
                    successful=successful,
                    avg_confidence=round(avg_conf, 2),
                    quality_score=round(quality, 2) if quality is not None else None,
                )
            )
        return result

    # ── public methods ────────────────────────────────────────────────────────

    async def get_learning(self, workspace_id: uuid.UUID) -> "LearningOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import LearningOut

        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:learning"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return LearningOut.model_validate_json(cached)
        except Exception:
            pass

        versions = await self._load_version_rows(workspace_id)
        insufficient = len(versions) < _LEARNING_MIN_VERSIONS

        current_version: str | None = versions[0].version if versions else None
        previous_version: str | None = versions[1].version if len(versions) >= 2 else None

        comparison = (
            self._compare_versions(versions[0], versions[1])
            if not insufficient
            else None
        )
        summary = self._build_summary(comparison)

        result = LearningOut(
            generated_at=datetime.now(UTC),
            current_version=current_version,
            previous_version=previous_version,
            comparison=comparison,
            summary=summary,
            insufficient_data=insufficient,
        )
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_LEARNING_CACHE_TTL)
        except Exception:
            pass
        log.info(
            "analytics.learning.get_learning",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            total_versions=len(versions),
        )
        return result

    async def get_version_history(self, workspace_id: uuid.UUID) -> "VersionHistoryOut":  # type: ignore[name-defined]
        from corpmind.modules.analytics.schemas import VersionHistoryOut

        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:analytics:version_history"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return VersionHistoryOut.model_validate_json(cached)
        except Exception:
            pass

        versions = await self._load_version_rows(workspace_id)
        result = VersionHistoryOut(
            versions=versions,
            total_versions=len(versions),
            insufficient_data=len(versions) < _LEARNING_MIN_VERSIONS,
        )
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_LEARNING_CACHE_TTL)
        except Exception:
            pass
        log.info(
            "analytics.learning.version_history",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            total_versions=len(versions),
        )
        return result
