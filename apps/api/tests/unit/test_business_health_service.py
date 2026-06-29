"""Unit tests for BusinessHealthService — Sprint 28.

All tests use mocked analytics/recommendation services and Redis — no DB.

Coverage areas:
  _normalize               : target=0, below, at, above target
  _pipeline_score          : zero-activity, reply-only, booking-only, combined
  _revenue_score           : zero, partial, at-target
  _campaign_score          : no campaigns (neutral), below, at target
  _recommendation_score    : insufficient_data (neutral), overdue penalty, capped
  _communication_score     : zero reply + perfect WA, combined
  _overall_score           : weights sum to 1, boundary values
  _health_trend            : < 7 days, exactly 7, improving, declining, stable, no prior
  _classify_components     : all strong, all poor, mixed
  _generate_alerts         : no alerts (healthy), critical reply, warning reply,
                             no activity, critical win rate, warning win rate,
                             critical delivery, warning delivery, rec completion,
                             overdue recs, WA delivery, alert ordering (critical first)
  _build_summary_data      : excellent / good / fair / poor; pipeline line variants;
                             revenue / campaign / rec / communication line variants;
                             trend lines (improving / declining)
  get_health               : Redis cache hit, cache miss → computes + sets cache,
                             service exception → defaults used, returns BusinessHealthOut
  get_alerts               : Redis cache hit, cache miss, returns OperationalAlertsOut
  get_summary_data         : Redis cache hit, cache miss, returns BusinessSummaryOut
  default factories        : _default_summary, _default_funnel, _default_wa, _default_exec
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    AnalyticsChannelSummary,
    AnalyticsFunnelOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
    ExecutionSummaryOut,
)
from corpmind.modules.dashboard.service import (
    BusinessHealthService,
    _HEALTH_CACHE_TTL,
    _Metrics,
    _default_exec,
    _default_funnel,
    _default_summary,
    _default_wa,
)

# ── Fixtures / helpers ────────────────────────────────────────────────────────

WORKSPACE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _mock_session() -> MagicMock:
    return MagicMock()


def _summary(
    *,
    total_sent: int = 100,
    total_delivered: int = 95,
    total_replied: int = 10,
    reply_rate: float = 0.10,
    delivery_rate: float = 0.95,
    proposals_generated: int = 10,
    proposals_approved: int = 8,
    proposals_sent: int = 10,
    proposals_accepted: int = 3,
    leads_booked: int = 5,
) -> AnalyticsSummary:
    return AnalyticsSummary(
        period_days=30,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_replied=total_replied,
        reply_rate=reply_rate,
        delivery_rate=delivery_rate,
        total_spend_inr=0.0,
        meetings_scheduled=0,
        meetings_completed=0,
        leads_created=0,
        leads_booked=leads_booked,
        proposals_generated=proposals_generated,
        proposals_approved=proposals_approved,
        proposals_sent=proposals_sent,
        proposals_accepted=proposals_accepted,
        closed_revenue_inr=0.0,
    )


def _funnel(**kwargs: int | float) -> AnalyticsFunnelOut:
    base = dict(
        contacts=10, outreach_sent=100, replies=10, meetings=5,
        proposals=10, bookings=5, proposals_accepted=3,
        pipeline_value_inr=0.0, closed_revenue_inr=0.0, win_rate=0.30,
    )
    base.update(kwargs)
    return AnalyticsFunnelOut(**base)  # type: ignore[arg-type]


def _wa(
    *,
    sent: int = 50,
    delivered: int = 48,
    delivery_rate: float = 0.96,
) -> AnalyticsChannelSummary:
    return AnalyticsChannelSummary(
        channel="whatsapp", period_days=30,
        sent=sent, delivered=delivered, opened=10, failed=2,
        compliance_blocks=0, delivery_rate=delivery_rate, read_rate=0.20,
    )


def _exec_summary(
    *,
    completion_rate: float = 0.80,
    overdue: int = 0,
    insufficient_data: bool = False,
) -> ExecutionSummaryOut:
    return ExecutionSummaryOut(
        accepted=10, started=8, completed=8, blocked=0, cancelled=0,
        completion_rate=completion_rate,
        cancellation_rate=0.0, block_rate=0.0,
        avg_days_to_start=1.0, avg_days_to_complete=3.0,
        avg_days_blocked=0.0, avg_days_cancelled=0.0,
        work_in_progress=2, overdue=overdue,
        insufficient_data=insufficient_data,
    )


def _trend_row(outreach_sent: int) -> AnalyticsTrendOut:
    return AnalyticsTrendOut(
        rollup_date=date.today(),
        outreach_sent=outreach_sent,
        outreach_replied=0, leads_created=0, leads_booked=0,
        proposals_sent=0, ai_spend_inr=0.0,
    )


def _metrics(
    summary: AnalyticsSummary | None = None,
    funnel: AnalyticsFunnelOut | None = None,
    wa: AnalyticsChannelSummary | None = None,
    trend: list[AnalyticsTrendOut] | None = None,
    exec_summary: ExecutionSummaryOut | None = None,
) -> _Metrics:
    return _Metrics(
        summary=summary or _summary(),
        funnel=funnel or _funnel(),
        wa=wa or _wa(),
        trend=trend or [],
        exec_summary=exec_summary or _exec_summary(),
    )


def _ctx_mock() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _svc() -> BusinessHealthService:
    return BusinessHealthService(_mock_session())


# ── _normalize ────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_target_zero_returns_zero(self) -> None:
        assert BusinessHealthService._normalize(50, 0) == 0.0

    def test_below_target(self) -> None:
        assert BusinessHealthService._normalize(5, 10) == 50.0

    def test_at_target(self) -> None:
        assert BusinessHealthService._normalize(10, 10) == 100.0

    def test_above_target_clamped(self) -> None:
        assert BusinessHealthService._normalize(20, 10) == 100.0

    def test_zero_value(self) -> None:
        assert BusinessHealthService._normalize(0, 10) == 0.0

    def test_fractional_rate(self) -> None:
        result = BusinessHealthService._normalize(0.05, 0.10)
        assert result == 50.0

    def test_negative_value_returns_negative(self) -> None:
        # No floor clamp — negative inputs are not expected in production (rates are 0-1)
        assert BusinessHealthService._normalize(-1, 10) < 0.0


# ── _pipeline_score ───────────────────────────────────────────────────────────


class TestPipelineScore:
    def test_zero_activity_returns_zero(self) -> None:
        s = _summary(reply_rate=0.0, proposals_sent=0, leads_booked=0)
        score = BusinessHealthService._pipeline_score(s, _funnel())
        assert score == 0.0

    def test_full_reply_rate_no_bookings(self) -> None:
        # reply_rate = 0.10 (target), booking_rate = 0 → 100*0.6 + 0*0.4 = 60
        s = _summary(reply_rate=0.10, proposals_sent=0, leads_booked=0)
        score = BusinessHealthService._pipeline_score(s, _funnel())
        assert score == 60.0

    def test_full_booking_rate_no_replies(self) -> None:
        # booking_rate = leads_booked/proposals_sent; 0.05/0.05 = 100; reply=0
        # leads_booked=5, proposals_sent=100 → booking_rate=0.05
        s = _summary(reply_rate=0.0, proposals_sent=100, leads_booked=5)
        score = BusinessHealthService._pipeline_score(s, _funnel())
        assert score == 40.0

    def test_both_at_target_returns_100(self) -> None:
        # reply=0.10, booking=0.05 → both normalized to 100
        s = _summary(reply_rate=0.10, proposals_sent=100, leads_booked=5)
        score = BusinessHealthService._pipeline_score(s, _funnel())
        assert score == 100.0

    def test_half_rates(self) -> None:
        # reply=0.05 (50%), booking=0.025 (50%) → 50*0.6 + 50*0.4 = 50
        s = _summary(reply_rate=0.05, proposals_sent=100, leads_booked=2)
        # leads_booked/proposals_sent = 0.02 → normalize(0.02, 0.05) = 40
        score = BusinessHealthService._pipeline_score(s, _funnel())
        assert 0 < score < 100


# ── _revenue_score ────────────────────────────────────────────────────────────


class TestRevenueScore:
    def test_zero_proposals_sent_returns_zero(self) -> None:
        s = _summary(proposals_sent=0, proposals_accepted=0, proposals_generated=0)
        score = BusinessHealthService._revenue_score(s)
        assert score == 0.0

    def test_at_target_win_rate_full_approval(self) -> None:
        # win_rate = 3/10 = 0.30, proposal_approval_rate = 10/10 = 1.0
        s = _summary(proposals_sent=10, proposals_accepted=3,
                     proposals_generated=10, proposals_approved=10)
        score = BusinessHealthService._revenue_score(s)
        # normalize(0.30, 0.30)*0.7 + normalize(1.0, 0.80)*0.3 = 100*0.7 + 100*0.3 = 100
        assert score == 100.0

    def test_low_win_rate(self) -> None:
        # win_rate = 1/10 = 0.10, approval_rate = 0/10 = 0.0
        # normalize(0.10, 0.30)*0.7 + normalize(0.0, 0.80)*0.3 = 33.3*0.7 + 0 = 23.3
        s = _summary(proposals_sent=10, proposals_accepted=1,
                     proposals_generated=10, proposals_approved=0)
        score = BusinessHealthService._revenue_score(s)
        assert score < 50

    def test_win_rate_normalized_above_target_clamped(self) -> None:
        # win_rate > target → clamped to 100
        s = _summary(proposals_sent=10, proposals_accepted=10,
                     proposals_generated=10, proposals_approved=10)
        score = BusinessHealthService._revenue_score(s)
        assert score == 100.0


# ── _campaign_score ───────────────────────────────────────────────────────────


class TestCampaignScore:
    def test_no_campaigns_returns_neutral_50(self) -> None:
        s = _summary(total_sent=0)
        assert BusinessHealthService._campaign_score(s) == 50.0

    def test_perfect_delivery(self) -> None:
        s = _summary(total_sent=100, delivery_rate=0.95)
        assert BusinessHealthService._campaign_score(s) == 100.0

    def test_low_delivery(self) -> None:
        s = _summary(total_sent=100, delivery_rate=0.60)
        score = BusinessHealthService._campaign_score(s)
        # normalize(0.60, 0.95) = 0.60/0.95 * 100 ≈ 63.2
        assert 60 < score < 70

    def test_above_target_delivery_clamped(self) -> None:
        s = _summary(total_sent=100, delivery_rate=1.0)
        assert BusinessHealthService._campaign_score(s) == 100.0


# ── _recommendation_score ─────────────────────────────────────────────────────


class TestRecommendationScore:
    def test_insufficient_data_returns_neutral_50(self) -> None:
        e = _exec_summary(insufficient_data=True)
        assert BusinessHealthService._recommendation_score(e) == 50.0

    def test_full_completion_no_overdue(self) -> None:
        e = _exec_summary(completion_rate=0.70, overdue=0)
        # normalize(0.70, 0.70)*1.0 - 0 penalty = 100
        assert BusinessHealthService._recommendation_score(e) == 100.0

    def test_overdue_penalty_applied(self) -> None:
        e = _exec_summary(completion_rate=0.70, overdue=4)
        score = BusinessHealthService._recommendation_score(e)
        # 100 - 4*5 = 80
        assert score == 80.0

    def test_overdue_penalty_capped_at_20(self) -> None:
        e = _exec_summary(completion_rate=0.70, overdue=100)
        score = BusinessHealthService._recommendation_score(e)
        # penalty capped at 20 → 100 - 20 = 80
        assert score == 80.0

    def test_score_cannot_go_below_zero(self) -> None:
        e = _exec_summary(completion_rate=0.0, overdue=10, insufficient_data=False)
        assert BusinessHealthService._recommendation_score(e) >= 0.0

    def test_low_completion_rate(self) -> None:
        e = _exec_summary(completion_rate=0.35, overdue=0, insufficient_data=False)
        score = BusinessHealthService._recommendation_score(e)
        # normalize(0.35, 0.70) = 50
        assert score == 50.0


# ── _communication_score ──────────────────────────────────────────────────────


class TestCommunicationScore:
    def test_zero_reply_perfect_wa(self) -> None:
        s = _summary(reply_rate=0.0)
        wa = _wa(delivery_rate=0.95)
        score = BusinessHealthService._communication_score(s, wa)
        # reply=0*0.4 + wa=100*0.6 = 60
        assert score == 60.0

    def test_full_reply_full_wa(self) -> None:
        s = _summary(reply_rate=0.10)
        wa = _wa(delivery_rate=0.95)
        score = BusinessHealthService._communication_score(s, wa)
        assert score == 100.0

    def test_poor_both(self) -> None:
        s = _summary(reply_rate=0.0)
        wa = _wa(delivery_rate=0.0)
        score = BusinessHealthService._communication_score(s, wa)
        assert score == 0.0


# ── _overall_score ────────────────────────────────────────────────────────────


class TestOverallScore:
    def test_all_zero(self) -> None:
        assert BusinessHealthService._overall_score(0, 0, 0, 0, 0) == 0.0

    def test_all_100(self) -> None:
        assert BusinessHealthService._overall_score(100, 100, 100, 100, 100) == 100.0

    def test_weights_sum_to_1(self) -> None:
        # Weights: 0.20 + 0.25 + 0.15 + 0.20 + 0.20 = 1.0
        score = BusinessHealthService._overall_score(100, 100, 100, 100, 100)
        assert score == 100.0

    def test_known_mix(self) -> None:
        # 80*0.20 + 60*0.25 + 70*0.15 + 90*0.20 + 50*0.20
        # = 16 + 15 + 10.5 + 18 + 10 = 69.5
        score = BusinessHealthService._overall_score(80, 60, 70, 90, 50)
        assert score == 69.5

    def test_revenue_has_highest_weight(self) -> None:
        # Only revenue contributes
        score = BusinessHealthService._overall_score(0, 100, 0, 0, 0)
        assert score == 25.0


# ── _health_trend ─────────────────────────────────────────────────────────────


class TestHealthTrend:
    def test_empty_list_returns_stable(self) -> None:
        assert BusinessHealthService._health_trend([]) == "stable"

    def test_less_than_7_rows_returns_stable(self) -> None:
        trend = [_trend_row(10)] * 6
        assert BusinessHealthService._health_trend(trend) == "stable"

    def test_exactly_7_rows_no_prior_returns_stable(self) -> None:
        trend = [_trend_row(10)] * 7
        assert BusinessHealthService._health_trend(trend) == "stable"

    def test_14_rows_equal_volume_returns_stable(self) -> None:
        trend = [_trend_row(10)] * 14
        assert BusinessHealthService._health_trend(trend) == "stable"

    def test_improving(self) -> None:
        # Recent 7: 120/wk; prior 7: 100/wk → +20%
        recent = [_trend_row(120 // 7 + 1)] * 7
        prior = [_trend_row(100 // 7)] * 7
        trend = recent + prior
        assert BusinessHealthService._health_trend(trend) == "improving"

    def test_declining(self) -> None:
        # Recent 7: 80/wk; prior 7: 100/wk → -20%
        recent = [_trend_row(11)] * 7
        prior = [_trend_row(14)] * 7
        trend = recent + prior
        assert BusinessHealthService._health_trend(trend) == "declining"

    def test_prior_sent_zero_returns_stable(self) -> None:
        recent = [_trend_row(10)] * 7
        prior = [_trend_row(0)] * 7
        assert BusinessHealthService._health_trend(recent + prior) == "stable"

    def test_just_over_threshold_improving(self) -> None:
        # prior = 100, recent = 111 → +11% > 10%
        prior = [_trend_row(100)] + [_trend_row(0)] * 6
        recent = [_trend_row(111)] + [_trend_row(0)] * 6
        trend = recent + prior
        assert BusinessHealthService._health_trend(trend) == "improving"

    def test_within_threshold_stable(self) -> None:
        # prior = 100, recent = 105 → +5% within ±10%
        prior = [_trend_row(100)] + [_trend_row(0)] * 6
        recent = [_trend_row(105)] + [_trend_row(0)] * 6
        trend = recent + prior
        assert BusinessHealthService._health_trend(trend) == "stable"


# ── _classify_components ──────────────────────────────────────────────────────


class TestClassifyComponents:
    def test_all_strong(self) -> None:
        strengths, attention = BusinessHealthService._classify_components(80, 80, 80, 80, 80)
        assert len(strengths) == 5
        assert len(attention) == 0

    def test_all_poor(self) -> None:
        strengths, attention = BusinessHealthService._classify_components(30, 30, 30, 30, 30)
        assert len(strengths) == 0
        assert len(attention) == 5

    def test_mixed(self) -> None:
        # pipeline=80 (strength ≥70), revenue=40 (attention <50), campaign=30 (attention <50)
        # recommendation=60 (neither), communication=50 (neither, boundary = exactly 50 not <50)
        strengths, attention = BusinessHealthService._classify_components(80, 40, 30, 60, 50)
        assert "Pipeline" in strengths
        assert "Campaign Delivery" in attention
        assert "Revenue Conversion" in attention  # 40 < 50 → needs attention
        assert "Revenue Conversion" not in strengths

    def test_exactly_at_threshold(self) -> None:
        # 70 = strength threshold, 50 = attention threshold
        strengths, attention = BusinessHealthService._classify_components(70, 50, 69, 51, 71)
        assert "Pipeline" in strengths
        assert "Communication" in strengths
        assert "Campaign Delivery" not in strengths  # 69 < 70
        assert len(attention) == 0  # none below 50


# ── _generate_alerts ──────────────────────────────────────────────────────────


class TestGenerateAlerts:
    def _healthy_summary(self) -> AnalyticsSummary:
        return _summary(
            total_sent=100, reply_rate=0.10, delivery_rate=0.96,
            proposals_sent=10, proposals_accepted=4,
        )

    def test_no_alerts_when_healthy(self) -> None:
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(),
            _wa(sent=50, delivery_rate=0.98),
            _exec_summary(completion_rate=0.80, overdue=0),
        )
        assert len(alerts) == 0

    def test_critical_reply_rate(self) -> None:
        s = _summary(total_sent=100, reply_rate=0.02)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        titles = [a.title for a in alerts]
        assert any("Critically low reply rate" in t for t in titles)
        assert any(a.priority == "critical" for a in alerts)

    def test_warning_reply_rate(self) -> None:
        s = _summary(total_sent=100, reply_rate=0.05)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        titles = [a.title for a in alerts]
        assert any("Low reply rate" in t for t in titles)

    def test_no_activity_info_alert(self) -> None:
        s = _summary(total_sent=0)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        assert any(a.priority == "info" for a in alerts)
        assert any("No outreach activity" in a.title for a in alerts)

    def test_critical_win_rate(self) -> None:
        s = _summary(proposals_sent=10, proposals_accepted=0,
                     total_sent=100, reply_rate=0.10)
        # win_rate = 0 < 0.10 critical threshold
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        assert any("Very low proposal win rate" in a.title for a in alerts)

    def test_warning_win_rate(self) -> None:
        s = _summary(proposals_sent=10, proposals_accepted=1,
                     total_sent=100, reply_rate=0.10)
        # win_rate = 0.10 < 0.20 warning
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        assert any("Low proposal win rate" in a.title for a in alerts)

    def test_critical_delivery_rate(self) -> None:
        s = _summary(total_sent=100, delivery_rate=0.60, reply_rate=0.10)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        assert any("Critical campaign delivery failure" in a.title for a in alerts)

    def test_warning_delivery_rate(self) -> None:
        s = _summary(total_sent=100, delivery_rate=0.80, reply_rate=0.10)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        assert any("Below-target campaign delivery" in a.title for a in alerts)

    def test_low_recommendation_completion(self) -> None:
        e = _exec_summary(completion_rate=0.20, overdue=0, insufficient_data=False)
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(), _wa(), e
        )
        assert any("Low recommendation completion rate" in a.title for a in alerts)

    def test_overdue_recommendations(self) -> None:
        e = _exec_summary(completion_rate=0.80, overdue=7, insufficient_data=False)
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(), _wa(), e
        )
        assert any("overdue recommendations" in a.title for a in alerts)

    def test_wa_delivery_alert(self) -> None:
        wa = _wa(sent=50, delivery_rate=0.60)
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(), wa, _exec_summary()
        )
        assert any("WhatsApp delivery issues" in a.title for a in alerts)

    def test_wa_no_alert_when_sent_is_zero(self) -> None:
        wa = _wa(sent=0, delivery_rate=0.0)
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(), wa, _exec_summary()
        )
        assert not any("WhatsApp" in a.title for a in alerts)

    def test_alert_ordering_critical_first(self) -> None:
        # critical reply + warning win rate → critical must come first
        s = _summary(total_sent=100, reply_rate=0.01,
                     proposals_sent=10, proposals_accepted=1)
        alerts = BusinessHealthService._generate_alerts(s, _wa(), _exec_summary())
        priorities = [a.priority for a in alerts]
        critical_idx = next((i for i, p in enumerate(priorities) if p == "critical"), None)
        warning_idx = next((i for i, p in enumerate(priorities) if p == "warning"), None)
        if critical_idx is not None and warning_idx is not None:
            assert critical_idx < warning_idx

    def test_insufficient_data_no_rec_alerts(self) -> None:
        e = _exec_summary(insufficient_data=True, completion_rate=0.0)
        alerts = BusinessHealthService._generate_alerts(
            self._healthy_summary(), _wa(), e
        )
        assert not any("recommendation" in a.category for a in alerts)


# ── _build_summary_data ───────────────────────────────────────────────────────


class TestBuildSummaryData:
    def test_excellent_assessment(self) -> None:
        result = BusinessHealthService._build_summary_data(
            85, 80, 80, 80, 80, 80, "stable"
        )
        assert result.overall_assessment == "excellent"
        assert any("excellent" in line for line in result.lines)

    def test_good_assessment(self) -> None:
        result = BusinessHealthService._build_summary_data(
            70, 60, 60, 60, 60, 60, "stable"
        )
        assert result.overall_assessment == "good"

    def test_fair_assessment(self) -> None:
        result = BusinessHealthService._build_summary_data(
            50, 50, 50, 50, 50, 50, "stable"
        )
        assert result.overall_assessment == "fair"

    def test_poor_assessment(self) -> None:
        result = BusinessHealthService._build_summary_data(
            30, 30, 30, 30, 30, 30, "declining"
        )
        assert result.overall_assessment == "poor"

    def test_strong_pipeline_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            80, 75, 50, 50, 50, 50, "stable"
        )
        assert any("strong" in line for line in result.lines)

    def test_weak_pipeline_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            50, 30, 50, 50, 50, 50, "stable"
        )
        assert any("attention" in line.lower() for line in result.lines)

    def test_strong_revenue_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            80, 50, 75, 50, 50, 50, "stable"
        )
        assert any("Revenue conversion is healthy" in line for line in result.lines)

    def test_weak_revenue_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            50, 50, 30, 50, 50, 50, "stable"
        )
        assert any("Revenue conversion is low" in line for line in result.lines)

    def test_improving_trend_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            70, 70, 70, 70, 70, 70, "improving"
        )
        assert any("trending up" in line for line in result.lines)

    def test_declining_trend_line(self) -> None:
        result = BusinessHealthService._build_summary_data(
            70, 70, 70, 70, 70, 70, "declining"
        )
        assert any("declining" in line for line in result.lines)

    def test_no_mid_range_extra_lines(self) -> None:
        # Scores in 50-69 range produce no extra lines for that component
        result = BusinessHealthService._build_summary_data(
            60, 55, 55, 55, 55, 55, "stable"
        )
        # Should have exactly the headline line (no component lines triggered)
        assert len(result.lines) == 1

    def test_generated_at_is_utc(self) -> None:
        result = BusinessHealthService._build_summary_data(
            70, 70, 70, 70, 70, 70, "stable"
        )
        assert result.generated_at.tzinfo is not None


# ── Default factories ─────────────────────────────────────────────────────────


class TestDefaultFactories:
    def test_default_summary_is_all_zero(self) -> None:
        s = _default_summary()
        assert s.total_sent == 0
        assert s.reply_rate == 0.0

    def test_default_funnel_is_all_zero(self) -> None:
        f = _default_funnel()
        assert f.outreach_sent == 0
        assert f.win_rate == 0.0

    def test_default_wa_has_healthy_delivery_rate(self) -> None:
        wa = _default_wa()
        # Neutral: assume good when no WA data
        assert wa.delivery_rate == 0.95
        assert wa.sent == 0

    def test_default_exec_has_insufficient_data(self) -> None:
        e = _default_exec()
        assert e.insufficient_data is True
        assert e.completion_rate == 0.0


# ── get_health (public, async) ────────────────────────────────────────────────


class TestGetHealth:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self) -> None:
        svc = _svc()
        cached_result = {
            "generated_at": datetime.now(UTC).isoformat(),
            "overall_score": 77.0, "pipeline_score": 80.0, "revenue_score": 70.0,
            "campaign_score": 75.0, "recommendation_score": 80.0,
            "communication_score": 80.0, "components": [], "top_alerts": [],
            "top_strengths": ["Pipeline"], "areas_needing_attention": [],
            "health_trend": "stable",
        }
        import json
        cached_bytes = json.dumps(cached_result).encode()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = cached_bytes
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        assert result.overall_score == 77.0
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_computes_and_sets(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary()
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        assert 0 <= result.overall_score <= 100
        assert len(result.components) == 5
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs[1].get("ex") == _HEALTH_CACHE_TTL or call_kwargs[0][2] == _HEALTH_CACHE_TTL

    @pytest.mark.asyncio
    async def test_service_exception_uses_defaults(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.side_effect = RuntimeError("db down")
        mock_analytics.get_funnel.side_effect = RuntimeError("db down")
        mock_analytics.get_channel_summary.side_effect = RuntimeError("db down")
        mock_analytics.get_trend.side_effect = RuntimeError("db down")
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.side_effect = RuntimeError("db down")

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        # Default: no sent → campaign neutral (50), recommendation neutral (50)
        assert result.campaign_score == 50.0
        assert result.recommendation_score == 50.0

    @pytest.mark.asyncio
    async def test_redis_exception_does_not_propagate(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary()
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.side_effect = ConnectionError("redis down")
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        assert result is not None

    @pytest.mark.asyncio
    async def test_health_trend_in_result(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary()
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        # 14 trend rows: recent 7 with 20/day, prior 7 with 10/day → improving
        recent = [_trend_row(20)] * 7
        prior = [_trend_row(10)] * 7
        mock_analytics.get_trend.return_value = recent + prior
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        assert result.health_trend == "improving"

    @pytest.mark.asyncio
    async def test_top_alerts_capped_at_3(self) -> None:
        svc = _svc()
        # Generate many alerts: critical reply + critical win + critical delivery + rec + overdue + wa
        s = _summary(
            total_sent=100, reply_rate=0.01, delivery_rate=0.60,
            proposals_sent=10, proposals_accepted=0,
        )
        wa = _wa(sent=50, delivery_rate=0.60)
        e = _exec_summary(completion_rate=0.20, overdue=10, insufficient_data=False)

        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = s
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = wa
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = e

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_health(workspace_id=WORKSPACE_ID)

        assert len(result.top_alerts) <= 3


# ── get_alerts (public, async) ────────────────────────────────────────────────


class TestGetAlerts:
    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        svc = _svc()
        import json
        cached = json.dumps({"alerts": [], "total": 0}).encode()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = cached
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))

            result = await svc.get_alerts(workspace_id=WORKSPACE_ID)

        assert result.total == 0
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_computes(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary(total_sent=0)
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_alerts(workspace_id=WORKSPACE_ID)

        # No activity → info alert
        assert result.total >= 1
        assert result.total == len(result.alerts)

    @pytest.mark.asyncio
    async def test_returns_operational_alerts_out(self) -> None:
        from corpmind.modules.dashboard.schemas import OperationalAlertsOut

        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary()
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_alerts(workspace_id=WORKSPACE_ID)

        assert isinstance(result, OperationalAlertsOut)


# ── get_summary_data (public, async) ─────────────────────────────────────────


class TestGetSummaryData:
    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        svc = _svc()
        import json
        cached = json.dumps({
            "generated_at": datetime.now(UTC).isoformat(),
            "lines": ["Business is excellent."],
            "overall_assessment": "excellent",
        }).encode()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = cached
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))

            result = await svc.get_summary_data(workspace_id=WORKSPACE_ID)

        assert result.overall_assessment == "excellent"
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_computes(self) -> None:
        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary(
            reply_rate=0.10, delivery_rate=0.95, proposals_sent=10, proposals_accepted=3
        )
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_summary_data(workspace_id=WORKSPACE_ID)

        assert len(result.lines) >= 1
        assert result.overall_assessment in ("excellent", "good", "fair", "poor")

    @pytest.mark.asyncio
    async def test_returns_business_summary_out(self) -> None:
        from corpmind.modules.dashboard.schemas import BusinessSummaryOut

        svc = _svc()
        mock_analytics = AsyncMock()
        mock_analytics.get_summary.return_value = _summary()
        mock_analytics.get_funnel.return_value = _funnel()
        mock_analytics.get_channel_summary.return_value = _wa()
        mock_analytics.get_trend.return_value = []
        mock_rec = AsyncMock()
        mock_rec.get_execution_summary.return_value = _exec_summary()

        with ExitStack() as stack:
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_tenant_context", return_value=_ctx_mock()))
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            stack.enter_context(patch("corpmind.modules.dashboard.service.get_redis", return_value=mock_redis))
            stack.enter_context(patch("corpmind.modules.dashboard.service.AnalyticsService", return_value=mock_analytics))
            stack.enter_context(patch("corpmind.modules.dashboard.service.RecommendationOutcomeService", return_value=mock_rec))

            result = await svc.get_summary_data(workspace_id=WORKSPACE_ID)

        assert isinstance(result, BusinessSummaryOut)
