"""BusinessHealthService — Sprint 28.

Aggregates metrics from existing analytics, proposal, CRM, and
recommendation services into a single business-health view.

Design constraints (enforced here):
- No SQL — all data flows through existing service classes (allowed cross-module
  import of service.py; blocked for repo.py / models.py per CLAUDE.md).
- No AI.  No Celery.  No background jobs.  No writes.
- Redis cache per workspace, TTL 15 minutes.
- asyncio.gather for concurrent service calls; return_exceptions=True for
  graceful partial failure.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.analytics.schemas import (
    AnalyticsChannelSummary,
    AnalyticsFunnelOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
    ExecutionSummaryOut,
)
from corpmind.modules.analytics.service import (
    AnalyticsService,
    RecommendationOutcomeService,
)
from corpmind.modules.dashboard.schemas import (
    BusinessHealthOut,
    BusinessSummaryOut,
    ComponentScore,
    OperationalAlert,
    OperationalAlertsOut,
)

log = structlog.get_logger(__name__)

# ── Cache ──────────────────────────────────────────────────────────────────────

_HEALTH_CACHE_TTL = 900      # 15 minutes — matches spec

# ── Score weights (must sum to 1.0) ───────────────────────────────────────────

_WEIGHT_PIPELINE: float = 0.20
_WEIGHT_REVENUE: float = 0.25
_WEIGHT_CAMPAIGN: float = 0.15
_WEIGHT_RECOMMENDATION: float = 0.20
_WEIGHT_COMMUNICATION: float = 0.20

# ── Scoring targets (value that yields 100 points) ────────────────────────────

_TARGET_REPLY_RATE: float = 0.10        # 10% reply rate → full pipeline pts
_TARGET_BOOKING_RATE: float = 0.05     # 5% booking rate → full pipeline pts
_TARGET_WIN_RATE: float = 0.30          # 30% win rate → full revenue pts
_TARGET_APPROVAL_RATE: float = 0.80    # 80% approval rate → full revenue pts
_TARGET_DELIVERY_RATE: float = 0.95    # 95% delivery → full campaign/comms pts
_TARGET_COMPLETION_RATE: float = 0.70  # 70% rec completion → full rec pts

# ── Alert thresholds ──────────────────────────────────────────────────────────

_ALERT_REPLY_RATE_CRITICAL: float = 0.03
_ALERT_REPLY_RATE_WARNING: float = 0.07
_ALERT_WIN_RATE_CRITICAL: float = 0.10
_ALERT_WIN_RATE_WARNING: float = 0.20
_ALERT_DELIVERY_CRITICAL: float = 0.70
_ALERT_DELIVERY_WARNING: float = 0.85
_ALERT_COMPLETION_WARNING: float = 0.30
_ALERT_OVERDUE_COUNT: int = 5

# ── Trend computation ─────────────────────────────────────────────────────────

_TREND_DAYS: int = 14
_TREND_CHANGE_THRESHOLD: float = 0.10  # ±10% week-over-week = improving/declining

# ── Internal metric bundle ────────────────────────────────────────────────────


@dataclass
class _Metrics:
    summary: AnalyticsSummary
    funnel: AnalyticsFunnelOut
    wa: AnalyticsChannelSummary
    trend: list[AnalyticsTrendOut]
    exec_summary: ExecutionSummaryOut


def _default_summary() -> AnalyticsSummary:
    return AnalyticsSummary(
        period_days=30,
        total_sent=0, total_delivered=0, total_replied=0,
        reply_rate=0.0, delivery_rate=0.0, total_spend_inr=0.0,
        meetings_scheduled=0, meetings_completed=0, leads_created=0,
        leads_booked=0, proposals_generated=0, proposals_approved=0,
        proposals_sent=0, proposals_accepted=0, closed_revenue_inr=0.0,
    )


def _default_funnel() -> AnalyticsFunnelOut:
    return AnalyticsFunnelOut(
        contacts=0, outreach_sent=0, replies=0, meetings=0,
        proposals=0, bookings=0, proposals_accepted=0,
        pipeline_value_inr=0.0, closed_revenue_inr=0.0, win_rate=0.0,
    )


def _default_wa() -> AnalyticsChannelSummary:
    return AnalyticsChannelSummary(
        channel="whatsapp", period_days=30, sent=0, delivered=0,
        opened=0, failed=0, compliance_blocks=0,
        delivery_rate=0.95,   # assume good when no data
        read_rate=0.0,
    )


def _default_exec() -> ExecutionSummaryOut:
    return ExecutionSummaryOut(
        accepted=0, started=0, completed=0, blocked=0, cancelled=0,
        completion_rate=0.0, cancellation_rate=0.0, block_rate=0.0,
        avg_days_to_start=0.0, avg_days_to_complete=0.0,
        avg_days_blocked=0.0, avg_days_cancelled=0.0,
        work_in_progress=0, overdue=0, insufficient_data=True,
    )


# ── BusinessHealthService ─────────────────────────────────────────────────────


class BusinessHealthService:
    """Read-only cross-module aggregator for the Business Health Center.

    All heavy lifting (SQL, caching) is delegated to the existing analytics
    service classes.  This service only combines, weights, and classifies.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── static score helpers ──────────────────────────────────────────────────

    @staticmethod
    def _normalize(value: float, target: float) -> float:
        """Return 0–100: value/target * 100, clamped to [0, 100]."""
        if target <= 0:
            return 0.0
        return min(value / target * 100.0, 100.0)

    @staticmethod
    def _pipeline_score(summary: AnalyticsSummary, funnel: AnalyticsFunnelOut) -> float:
        svc = BusinessHealthService
        reply = svc._normalize(summary.reply_rate, _TARGET_REPLY_RATE)
        booking = svc._normalize(summary.booking_rate, _TARGET_BOOKING_RATE)
        return round(reply * 0.6 + booking * 0.4, 1)

    @staticmethod
    def _revenue_score(summary: AnalyticsSummary) -> float:
        svc = BusinessHealthService
        win = svc._normalize(summary.win_rate, _TARGET_WIN_RATE)
        approval = svc._normalize(summary.proposal_approval_rate, _TARGET_APPROVAL_RATE)
        return round(win * 0.7 + approval * 0.3, 1)

    @staticmethod
    def _campaign_score(summary: AnalyticsSummary) -> float:
        if summary.total_sent == 0:
            return 50.0   # neutral — no campaigns yet
        return round(BusinessHealthService._normalize(summary.delivery_rate, _TARGET_DELIVERY_RATE), 1)

    @staticmethod
    def _recommendation_score(exec_summary: ExecutionSummaryOut) -> float:
        if exec_summary.insufficient_data:
            return 50.0   # neutral — no recommendations yet
        completion = BusinessHealthService._normalize(
            exec_summary.completion_rate, _TARGET_COMPLETION_RATE
        )
        overdue_penalty = min(exec_summary.overdue * 5.0, 20.0)
        return round(max(0.0, completion - overdue_penalty), 1)

    @staticmethod
    def _communication_score(
        summary: AnalyticsSummary,
        wa: AnalyticsChannelSummary,
    ) -> float:
        svc = BusinessHealthService
        reply = svc._normalize(summary.reply_rate, _TARGET_REPLY_RATE)
        wa_delivery = svc._normalize(wa.delivery_rate, _TARGET_DELIVERY_RATE)
        return round(reply * 0.4 + wa_delivery * 0.6, 1)

    @staticmethod
    def _overall_score(
        pipeline: float,
        revenue: float,
        campaign: float,
        recommendation: float,
        communication: float,
    ) -> float:
        return round(
            pipeline * _WEIGHT_PIPELINE
            + revenue * _WEIGHT_REVENUE
            + campaign * _WEIGHT_CAMPAIGN
            + recommendation * _WEIGHT_RECOMMENDATION
            + communication * _WEIGHT_COMMUNICATION,
            1,
        )

    @staticmethod
    def _health_trend(trend: list[AnalyticsTrendOut]) -> str:
        """Compare last-7-days vs prior-7-days outreach volume (newest first)."""
        if len(trend) < 7:
            return "stable"
        recent_sent = sum(r.outreach_sent for r in trend[:7])
        prior = trend[7:14]
        if not prior:
            return "stable"
        prior_sent = sum(r.outreach_sent for r in prior)
        if prior_sent == 0:
            return "stable"
        change = (recent_sent - prior_sent) / prior_sent
        if change > _TREND_CHANGE_THRESHOLD:
            return "improving"
        if change < -_TREND_CHANGE_THRESHOLD:
            return "declining"
        return "stable"

    @staticmethod
    def _classify_components(
        pipeline: float,
        revenue: float,
        campaign: float,
        recommendation: float,
        communication: float,
    ) -> tuple[list[str], list[str]]:
        mapping = [
            ("Pipeline", pipeline),
            ("Revenue Conversion", revenue),
            ("Campaign Delivery", campaign),
            ("Recommendation Adoption", recommendation),
            ("Communication", communication),
        ]
        strengths = [name for name, score in mapping if score >= 70]
        attention = [name for name, score in mapping if score < 50]
        return strengths, attention

    @staticmethod
    def _generate_alerts(
        summary: AnalyticsSummary,
        wa: AnalyticsChannelSummary,
        exec_summary: ExecutionSummaryOut,
    ) -> list[OperationalAlert]:
        now = datetime.now(UTC)
        alerts: list[OperationalAlert] = []

        # Reply rate checks
        if summary.total_sent > 0:
            if summary.reply_rate < _ALERT_REPLY_RATE_CRITICAL:
                alerts.append(OperationalAlert(
                    priority="critical", category="pipeline",
                    title="Critically low reply rate",
                    description=f"Reply rate is {summary.reply_rate * 100:.1f}% — well below the 3% floor.",
                    recommended_action="Review outreach copy, subject lines, and targeting segments.",
                    created_at=now,
                ))
            elif summary.reply_rate < _ALERT_REPLY_RATE_WARNING:
                alerts.append(OperationalAlert(
                    priority="warning", category="pipeline",
                    title="Low reply rate",
                    description=f"Reply rate is {summary.reply_rate * 100:.1f}% — below the 7% warning level.",
                    recommended_action="A/B test outreach templates and personalisation depth.",
                    created_at=now,
                ))

        if summary.total_sent == 0:
            alerts.append(OperationalAlert(
                priority="info", category="campaign",
                title="No outreach activity in 30 days",
                description="No outbound messages have been sent in the last 30 days.",
                recommended_action="Launch a campaign to re-activate your outreach pipeline.",
                created_at=now,
            ))

        # Win rate checks
        if summary.proposals_sent > 0:
            if summary.win_rate < _ALERT_WIN_RATE_CRITICAL:
                alerts.append(OperationalAlert(
                    priority="critical", category="revenue",
                    title="Very low proposal win rate",
                    description=f"Win rate is {summary.win_rate * 100:.1f}% — below the 10% floor.",
                    recommended_action="Review proposal pricing, structure, and follow-up cadence.",
                    created_at=now,
                ))
            elif summary.win_rate < _ALERT_WIN_RATE_WARNING:
                alerts.append(OperationalAlert(
                    priority="warning", category="revenue",
                    title="Low proposal win rate",
                    description=f"Win rate is {summary.win_rate * 100:.1f}% — below the 20% target.",
                    recommended_action="Investigate objections and refine proposal value proposition.",
                    created_at=now,
                ))

        # Delivery rate checks
        if summary.total_sent > 0:
            if summary.delivery_rate < _ALERT_DELIVERY_CRITICAL:
                alerts.append(OperationalAlert(
                    priority="critical", category="campaign",
                    title="Critical campaign delivery failure",
                    description=f"Only {summary.delivery_rate * 100:.1f}% of messages are being delivered.",
                    recommended_action="Check email domain reputation, WhatsApp tier limits, and channel health.",
                    created_at=now,
                ))
            elif summary.delivery_rate < _ALERT_DELIVERY_WARNING:
                alerts.append(OperationalAlert(
                    priority="warning", category="campaign",
                    title="Below-target campaign delivery",
                    description=f"Delivery rate is {summary.delivery_rate * 100:.1f}% — below the 85% target.",
                    recommended_action="Review bounce rates and verify contact list quality.",
                    created_at=now,
                ))

        # Recommendation completion
        if not exec_summary.insufficient_data:
            if exec_summary.completion_rate < _ALERT_COMPLETION_WARNING:
                alerts.append(OperationalAlert(
                    priority="warning", category="recommendation",
                    title="Low recommendation completion rate",
                    description=f"Only {exec_summary.completion_rate * 100:.1f}% of accepted recommendations are completed.",
                    recommended_action="Review the work queue and clear blocked recommendations.",
                    created_at=now,
                ))
            if exec_summary.overdue >= _ALERT_OVERDUE_COUNT:
                alerts.append(OperationalAlert(
                    priority="warning", category="recommendation",
                    title=f"{exec_summary.overdue} overdue recommendations",
                    description=f"{exec_summary.overdue} recommendations are past their expected completion date.",
                    recommended_action="Open the Recommendation Work Queue and action overdue items.",
                    created_at=now,
                ))

        # WhatsApp delivery
        if wa.sent > 0 and wa.delivery_rate < _ALERT_DELIVERY_CRITICAL:
            alerts.append(OperationalAlert(
                priority="warning", category="communication",
                title="WhatsApp delivery issues",
                description=f"WhatsApp delivery rate is {wa.delivery_rate * 100:.1f}% — below the 70% floor.",
                recommended_action="Verify Meta Cloud API credentials and template approval status.",
                created_at=now,
            ))

        # Sort: critical → warning → info
        _order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: _order.get(a.priority, 3))
        return alerts

    @staticmethod
    def _build_summary_data(
        overall: float,
        pipeline: float,
        revenue: float,
        campaign: float,
        recommendation: float,
        communication: float,
        trend: str,
    ) -> BusinessSummaryOut:
        if overall >= 80:
            assessment = "excellent"
            lines = [f"Business health is excellent at {overall:.0f}/100."]
        elif overall >= 60:
            assessment = "good"
            lines = [f"Business health is good at {overall:.0f}/100."]
        elif overall >= 40:
            assessment = "fair"
            lines = [f"Business health is fair at {overall:.0f}/100 — focus on top alerts."]
        else:
            assessment = "poor"
            lines = [f"Business health needs immediate attention at {overall:.0f}/100."]

        if pipeline >= 70:
            lines.append("Pipeline performance is strong.")
        elif pipeline < 40:
            lines.append("Pipeline needs attention — increase outreach volume and improve copy.")

        if revenue >= 70:
            lines.append("Revenue conversion is healthy.")
        elif revenue < 40:
            lines.append("Revenue conversion is low — review proposal quality and pricing.")

        if campaign >= 70:
            lines.append("Campaign delivery is reliable.")
        elif campaign < 40:
            lines.append("Campaign delivery issues detected — check channel configuration.")

        if recommendation >= 70:
            lines.append("Recommendation adoption is on track.")
        elif recommendation < 40:
            lines.append("Recommendation completion is low — review the work queue.")

        if communication >= 70:
            lines.append("Communication channels are performing well.")
        elif communication < 40:
            lines.append("Communication effectiveness needs improvement.")

        if trend == "improving":
            lines.append("Outreach activity is trending up week over week.")
        elif trend == "declining":
            lines.append("Outreach activity is declining — prioritise campaign reactivation.")

        return BusinessSummaryOut(
            generated_at=datetime.now(UTC),
            lines=lines,
            overall_assessment=assessment,
        )

    # ── private data loader ───────────────────────────────────────────────────

    async def _load_metrics(self, workspace_id: uuid.UUID) -> _Metrics:
        results = await asyncio.gather(
            AnalyticsService(self._session).get_summary(days=30),
            AnalyticsService(self._session).get_funnel(workspace_id=workspace_id),
            AnalyticsService(self._session).get_channel_summary(channel="whatsapp", days=30),
            AnalyticsService(self._session).get_trend(days=_TREND_DAYS),
            RecommendationOutcomeService(self._session).get_execution_summary(workspace_id),
            return_exceptions=True,
        )
        return _Metrics(
            summary=results[0] if not isinstance(results[0], Exception) else _default_summary(),
            funnel=results[1] if not isinstance(results[1], Exception) else _default_funnel(),
            wa=results[2] if not isinstance(results[2], Exception) else _default_wa(),
            trend=results[3] if not isinstance(results[3], Exception) else [],
            exec_summary=results[4] if not isinstance(results[4], Exception) else _default_exec(),
        )

    # ── public methods ────────────────────────────────────────────────────────

    async def get_health(self, workspace_id: uuid.UUID) -> BusinessHealthOut:
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:dashboard:business_health"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return BusinessHealthOut.model_validate_json(cached)
        except Exception:
            pass

        m = await self._load_metrics(workspace_id)
        pipeline = self._pipeline_score(m.summary, m.funnel)
        revenue = self._revenue_score(m.summary)
        campaign = self._campaign_score(m.summary)
        recommendation = self._recommendation_score(m.exec_summary)
        communication = self._communication_score(m.summary, m.wa)
        overall = self._overall_score(pipeline, revenue, campaign, recommendation, communication)
        trend = self._health_trend(m.trend)
        strengths, attention = self._classify_components(pipeline, revenue, campaign, recommendation, communication)
        alerts = self._generate_alerts(m.summary, m.wa, m.exec_summary)

        result = BusinessHealthOut(
            generated_at=datetime.now(UTC),
            overall_score=overall,
            pipeline_score=pipeline,
            revenue_score=revenue,
            campaign_score=campaign,
            recommendation_score=recommendation,
            communication_score=communication,
            components=[
                ComponentScore(name="Pipeline", score=pipeline, weight=_WEIGHT_PIPELINE),
                ComponentScore(name="Revenue Conversion", score=revenue, weight=_WEIGHT_REVENUE),
                ComponentScore(name="Campaign Delivery", score=campaign, weight=_WEIGHT_CAMPAIGN),
                ComponentScore(name="Recommendation Adoption", score=recommendation, weight=_WEIGHT_RECOMMENDATION),
                ComponentScore(name="Communication", score=communication, weight=_WEIGHT_COMMUNICATION),
            ],
            top_alerts=alerts[:3],
            top_strengths=strengths,
            areas_needing_attention=attention,
            health_trend=trend,
        )
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_HEALTH_CACHE_TTL)
        except Exception:
            pass

        log.info(
            "dashboard.business_health.computed",
            tenant_id=str(ctx.org_id),
            workspace_id=str(workspace_id),
            overall_score=overall,
            trend=trend,
        )
        return result

    async def get_alerts(self, workspace_id: uuid.UUID) -> OperationalAlertsOut:
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:dashboard:operational_alerts"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return OperationalAlertsOut.model_validate_json(cached)
        except Exception:
            pass

        m = await self._load_metrics(workspace_id)
        alerts = self._generate_alerts(m.summary, m.wa, m.exec_summary)
        result = OperationalAlertsOut(alerts=alerts, total=len(alerts))
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_HEALTH_CACHE_TTL)
        except Exception:
            pass
        return result

    async def get_summary_data(self, workspace_id: uuid.UUID) -> BusinessSummaryOut:
        ctx = get_tenant_context()
        cache_key = f"t:{ctx.org_id}:{workspace_id}:dashboard:business_summary"
        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return BusinessSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        m = await self._load_metrics(workspace_id)
        pipeline = self._pipeline_score(m.summary, m.funnel)
        revenue = self._revenue_score(m.summary)
        campaign = self._campaign_score(m.summary)
        recommendation = self._recommendation_score(m.exec_summary)
        communication = self._communication_score(m.summary, m.wa)
        overall = self._overall_score(pipeline, revenue, campaign, recommendation, communication)
        trend = self._health_trend(m.trend)
        result = self._build_summary_data(overall, pipeline, revenue, campaign, recommendation, communication, trend)
        try:
            await get_redis().set(cache_key, result.model_dump_json(), ex=_HEALTH_CACHE_TTL)
        except Exception:
            pass
        return result
