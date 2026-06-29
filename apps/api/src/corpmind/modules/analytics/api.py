"""Analytics module REST API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.analytics.schemas import (
    AcceptOut,
    AnalyticsChannelSummary,
    AnalyticsFunnelOut,
    AnalyticsInsightOut,
    AnalyticsSummary,
    AnalyticsTrendOut,
    CalibrationReviewOut,
    CampaignROIListOut,
    CoverageOut,
    DecayOut,
    DismissRequest,
    DriftOut,
    EvidenceOut,
    IndustryPerformanceOut,
    LearningOut,
    LifecycleOut,
    PortfolioOut,
    PricingCalibrationOut,
    RecCalibrationOut,
    RecEffectivenessOut,
    RecReviewOut,
    BlockRequest,
    CancelRequest,
    CompleteRequest,
    ExecutionOut,
    ExecutionSummaryOut,
    OutcomeTypeItemOut,
    RecommendationOutcomesOut,
    RecommendationActionOut,
    RecommendationActionsListOut,
    RecommendationFeedbackIn,
    RecommendationFeedbackOut,
    RecommendationsOut,
    ReliabilityOut,
    SnoozeRequest,
    StabilityOut,
    TopicPerformanceOut,
    VersionHistoryOut,
    WorkQueueOut,
)
from corpmind.modules.analytics.service import (
    AnalyticsInsightService,
    AnalyticsService,
    RecommendationActionService,
    RecommendationAnalyticsService,
    RecommendationCalibrationService,
    RecommendationDriftService,
    RecommendationEffectivenessService,
    RecommendationEvidenceService,
    RecommendationExecutionService,
    RecommendationLearningService,
    RecommendationLifecycleService,
    RecommendationOutcomeService,
    RecommendationPortfolioService,
    RecommendationReviewService,
)

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


# Channels with a per-channel rollup row in analytics_daily.
_SUPPORTED_CHANNELS = frozenset({"whatsapp"})


@router.get("/channel/{channel}", response_model=AnalyticsChannelSummary)
async def get_channel_analytics(
    channel: str,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsChannelSummary:
    """Return per-channel outreach performance summary for the last N days.

    Reads pre-computed analytics_daily channel rows for sent/delivered/opened.
    failed is queried live (no analytics_daily column for it).
    Supported channels: whatsapp.  Returns 404 for unknown channels.
    """
    if channel not in _SUPPORTED_CHANNELS:
        supported = sorted(_SUPPORTED_CHANNELS)
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel}' is not supported. Supported: {supported}",
        )
    return await AnalyticsService(session).get_channel_summary(channel=channel, days=days)


# ── Sprint 19 — intelligence endpoints ───────────────────────────────────────


@router.get("/campaigns/roi", response_model=CampaignROIListOut)
async def get_campaign_roi(
    workspace_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_session),
) -> CampaignROIListOut:
    """Return paginated campaign ROI from analytics_campaign_summary.

    Reads the pre-computed snapshot table — fast, no aggregation at request time.
    Attribution model is 'all_touch' (returned in the response for tooltip display):
    a contact in multiple campaigns has revenue credited to each campaign.
    """
    return await AnalyticsService(session).get_campaign_roi(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )


@router.get("/topics", response_model=TopicPerformanceOut)
async def get_topic_performance(
    workspace_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    session: AsyncSession = Depends(get_session),
) -> TopicPerformanceOut:
    """Return trainer topic performance ranked by revenue.

    Live query (UNNEST topics array × proposals), Redis-cached 1 hour per workspace.
    low_confidence=true when total proposals_sent < 5 in the workspace.
    """
    return await AnalyticsService(session).get_topic_performance(
        workspace_id=workspace_id,
        limit=limit,
    )


@router.get("/industries", response_model=IndustryPerformanceOut)
async def get_industry_performance(
    workspace_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    session: AsyncSession = Depends(get_session),
) -> IndustryPerformanceOut:
    """Return proposal performance broken down by client industry.

    Industry is sourced from companies.industry (proposals → hr_contacts → companies).
    NULL industry rows are grouped as 'Unknown'; unknown_count is returned separately.
    Redis-cached 1 hour per workspace.
    """
    return await AnalyticsService(session).get_industry_performance(
        workspace_id=workspace_id,
        limit=limit,
    )


@router.get("/pricing-calibration", response_model=PricingCalibrationOut)
async def get_pricing_calibration(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PricingCalibrationOut:
    """Return pricing calibration: stated trainer range vs actual accepted values.

    Includes MIN, MAX, AVG, and PERCENTILE_CONT(0.5) of actual_value_inr across
    accepted proposals, plus avg_days_to_accept for the workspace.
    low_confidence=true when fewer than 5 accepted proposals have a non-null value.
    Redis-cached 1 hour per workspace.
    """
    return await AnalyticsService(session).get_pricing_calibration(workspace_id=workspace_id)


# ── Sprint 20A — Recommendations ─────────────────────────────────────────────


@router.get("/recommendations", response_model=RecommendationsOut)
async def get_recommendations(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RecommendationsOut:
    """Return deterministic recommendations for a workspace.

    All 5 recommendation types (industry, topic, pricing, campaign, channel) are
    computed from Sprint 19 analytics data — no LLM, no AI, fully auditable.
    Items below the hard minimum sample threshold or with confidence_score < 20
    are suppressed and counted in suppressed_count.
    Redis-cached 4 hours per workspace.
    """
    return await AnalyticsService(session).get_recommendations(workspace_id=workspace_id)


# ── Sprint 20B — AI Insight Layer ─────────────────────────────────────────────


@router.get("/insights", response_model=AnalyticsInsightOut)
async def get_insights(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsInsightOut:
    """Return AI narrative insights layered over deterministic recommendations.

    The AI receives only the serialised RecommendationsOut payload — it cannot
    alter confidence scores, invent metrics, or create new recommendations.
    If recommendations are empty, a canned 'insufficient data' response is returned
    without any LLM call.
    Redis-cached 4 hours per workspace (aligned with /recommendations TTL).
    """
    return await AnalyticsInsightService(session).get_insights(workspace_id=workspace_id)


# ── Sprint 21 — Recommendation Feedback & Effectiveness ──────────────────────


@router.post("/recommendations/feedback", response_model=RecommendationFeedbackOut, status_code=201)
async def submit_recommendation_feedback(
    body: RecommendationFeedbackIn,
    session: AsyncSession = Depends(get_session),
) -> RecommendationFeedbackOut:
    """Record trainer feedback (helpful | not_helpful | dismissed) for a rec type.

    Looks up the most recent snapshot for (workspace_id, rec_type) within the
    last 7 days so callers need only pass workspace_id + rec_type — no snapshot
    UUID required.  Returns 404 when no snapshot exists (recommend first).
    ON CONFLICT DO UPDATE so trainers can change their rating.
    """
    return await RecommendationEffectivenessService(session).submit_feedback(body)


@router.get("/recommendations/effectiveness", response_model=RecEffectivenessOut)
async def get_recommendation_effectiveness(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 30,
    session: AsyncSession = Depends(get_session),
) -> RecEffectivenessOut:
    """Return adoption/success summary + per-type table + quality trend (Sprint 22A).

    Reads pre-computed recommendation_quality_scores rows.
    summary.adoption_rate and success_rate are cross-type totals.
    quality_trend contains all rows in the period ordered by date asc for charts.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationAnalyticsService(session).get_effectiveness(
        workspace_id=workspace_id,
        period_days=period_days,
    )


@router.get("/recommendations/calibration", response_model=RecCalibrationOut)
async def get_recommendation_calibration(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> RecCalibrationOut:
    """Return predicted vs observed confidence calibration (Sprint 22A).

    predicted_confidence = AVG(confidence_score) from recommendation_snapshots.
    observed_success_rate = success_count / acted_count × 100 from outcomes.
    calibration_delta = observed − predicted (negative → overconfident).
    insufficient_data = True when total acted outcomes < 5.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationAnalyticsService(session).get_calibration(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 22B — Recommendation Quality Review ───────────────────────────────


@router.get("/recommendations/review", response_model=RecReviewOut)
async def get_recommendation_review(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> RecReviewOut:
    """Return recommendation quality review: top/bottom performers + calibration trifecta (Sprint 22B).

    Observational only — no AI, no new tables, no cross-tenant comparisons.
    best/worst_performing_type: rec_types with highest/lowest quality_score (non-null only).
    most_ignored_type: rec_type with highest ignored_count / shown_count.
    most_adopted/successful_type: rec_types with highest adoption_rate / success_rate.
    calibration_summary: types grouped by calibration_delta sign and magnitude.
    quality_trend: average quality_score per day across all types.
    insufficient_data = True when no quality score rows exist in the period.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationReviewService(session).get_review(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 23A — Calibration Validation & Quality Score Stability ─────────────


@router.get("/recommendations/calibration-review", response_model=CalibrationReviewOut)
async def get_calibration_review(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> CalibrationReviewOut:
    """Return confidence distribution, accuracy counts, and per-type severity (Sprint 23A).

    Observational only — measures the confidence model, does not modify it.
    confidence_distribution: snapshot counts by confidence_level band (high/medium/low).
    overall:                 per-band success rates (from acted outcomes).
    accuracy:                well_calibrated / overconfident / underconfident counts.
    recommendation_types:    per-type with severity label (calibrated / warning / severe).
    insufficient_data:       True when total acted outcomes < 5.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationCalibrationService(session).get_calibration_review(
        workspace_id=workspace_id,
        period_days=period_days,
    )


@router.get("/recommendations/stability", response_model=StabilityOut)
async def get_recommendation_stability(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> StabilityOut:
    """Return quality score stability metrics per recommendation type (Sprint 23A).

    Observational only — computes population std_dev over quality_score history.
    quality_score_stability: overall average, std_dev, and stability_rating.
    recommendation_types:    per-type stability (stable / volatile / unstable).
    insufficient_data:       True when no quality score rows exist in the period.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationCalibrationService(session).get_stability(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 23B — Confidence Drift & Recommendation Reliability ────────────────


@router.get("/recommendations/drift", response_model=DriftOut)
async def get_recommendation_drift(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=180)] = 30,
    session: AsyncSession = Depends(get_session),
) -> DriftOut:
    """Return drift direction for quality, adoption, and success metrics (Sprint 23B).

    Observational only — compares current vs previous period, does not modify anything.
    overall: cross-type trends for quality_score, adoption_rate, success_rate.
    by_type: quality_score trend per recommendation type.
    insufficient_data: True when the previous window has no data (< 60 days of history).
    All rate metrics are presented on a 0–100 scale (fractions × 100).
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationDriftService(session).get_drift(
        workspace_id=workspace_id,
        period_days=period_days,
    )


@router.get("/recommendations/reliability", response_model=ReliabilityOut)
async def get_recommendation_reliability(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 30,
    session: AsyncSession = Depends(get_session),
) -> ReliabilityOut:
    """Return recommendation reliability scores per type (Sprint 23B).

    Observational only — deterministic weighted formula, no AI involved.
    Formula: success_rate_pct × 0.5 + adoption_rate_pct × 0.3 + quality_score × 0.2.
    overall_reliability: workspace-level composite score and rating (high/medium/low).
    recommendation_types: per-type scores sorted alphabetically.
    insufficient_data: True when no quality score rows exist in the period.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationDriftService(session).get_reliability(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 24A — Recommendation Lifecycle Observatory ────────────────────────


@router.get("/recommendations/lifecycle", response_model=LifecycleOut)
async def get_recommendation_lifecycle(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> LifecycleOut:
    """Return recommendation lifecycle timing and conversion rates (Sprint 24A).

    Observational only — measures how quickly recommendations are acted upon and
    succeed.  Joins recommendation_outcomes with recommendation_snapshots to derive
    avg_days_to_action (acted_at - snapshot.generated_at) and avg_days_to_success
    (success_measured_at - snapshot.generated_at).
    overall: workspace-level timing and conversion summary.
    recommendation_types: per-type stats sorted alphabetically.
    insufficient_data: True when no outcome rows exist in the period.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationLifecycleService(session).get_lifecycle(
        workspace_id=workspace_id,
        period_days=period_days,
    )


@router.get("/recommendations/decay", response_model=DecayOut)
async def get_recommendation_decay(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 180,
    session: AsyncSession = Depends(get_session),
) -> DecayOut:
    """Return recommendation effectiveness bucketed by age (Sprint 24A).

    Observational only — buckets all outcome rows by (today - snapshot_date) days
    into 0–7, 8–30, 31–60, 60+ brackets.  Always emits all 4 buckets in canonical
    order; empty brackets have sample_size=0 and rates 0.0.
    Per-type decay_detected = True when best_success_rate - worst_success_rate >= 10.
    Only types with outcomes in >= 2 non-empty buckets are included in recommendation_types.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationLifecycleService(session).get_decay(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 24B — Recommendation Portfolio & Coverage ────────────────────────


@router.get("/recommendations/portfolio", response_model=PortfolioOut)
async def get_recommendation_portfolio(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> PortfolioOut:
    """Return recommendation composition and diversity analysis (Sprint 24B).

    Observational only — no AI, no new tables, no cross-tenant comparisons.
    recommendation_types: per-type count, percentage, acted/success rates.
    dominant_type / least_used_type: types with highest/lowest snapshot count.
    portfolio_balance: Shannon entropy normalized to 0–100 + balance rating.
    insufficient_data: True when no snapshot rows exist in the period.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationPortfolioService(session).get_portfolio(
        workspace_id=workspace_id,
        period_days=period_days,
    )


@router.get("/recommendations/coverage", response_model=CoverageOut)
async def get_recommendation_coverage(
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> CoverageOut:
    """Return coverage status for all known recommendation types (Sprint 24B).

    Observational only — determines which recommendation categories have been
    generated, when they were last generated, and whether they are stale.
    present: True when at least one snapshot exists (all time).
    days_since_last_generated: today - last snapshot_date (all time); None if absent.
    stale_types: types where days_since_last_generated > 30.
    missing_types: types with no snapshots ever.
    period_days controls the count column only; staleness uses all-time history.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationPortfolioService(session).get_coverage(
        workspace_id=workspace_id,
        period_days=period_days,
    )


# ── Sprint 25A — Recommendation Evidence Explorer ────────────────────────────


_VALID_EVIDENCE_TYPES = frozenset({"campaign", "channel", "industry", "pricing", "topic"})


@router.get("/recommendations/evidence/{recommendation_type}", response_model=EvidenceOut)
async def get_recommendation_evidence(
    recommendation_type: str,
    workspace_id: uuid.UUID,
    period_days: Annotated[int, Query(ge=1, le=365)] = 90,
    session: AsyncSession = Depends(get_session),
) -> EvidenceOut:
    """Return all available evidence for a single recommendation type (Sprint 25A).

    Observational only — no AI, no new tables, no recommendation changes.
    Orchestrates existing Sprint 21–24 analytics services to assemble evidence:
      summary: generated_count, quality_score, reliability, confidence, lifecycle timing,
               drift direction, stability, calibration status, coverage status.
      supporting_metrics: named metrics with source attribution for full transparency.
    insufficient_data: True when no snapshots exist for this type ever.
    Valid recommendation_type values: campaign, channel, industry, pricing, topic.
    Redis-cached 1 hour per (workspace, recommendation_type).
    """
    if recommendation_type not in _VALID_EVIDENCE_TYPES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown recommendation_type '{recommendation_type}'. "
                f"Valid types: {sorted(_VALID_EVIDENCE_TYPES)}"
            ),
        )
    return await RecommendationEvidenceService(session).get_evidence(
        workspace_id=workspace_id,
        recommendation_type=recommendation_type,
        period_days=period_days,
    )


# ── Sprint 25B — Recommendation Action Center ────────────────────────────────


@router.get("/recommendations/actions", response_model=RecommendationActionsListOut)
async def list_recommendation_actions(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RecommendationActionsListOut:
    """Return all trainer actions grouped by status (Sprint 25B).

    Actions are grouped into: accepted, dismissed, snoozed, completed, expired.
    'expired' is computed at read time: snoozed rows where snooze_until < today.
    Redis-cached 5 minutes per workspace; invalidated on every mutation.
    """
    return await RecommendationActionService(session).list_actions(
        workspace_id=workspace_id,
    )


@router.post(
    "/recommendations/{recommendation_id}/accept",
    response_model=AcceptOut,
    status_code=201,
)
async def accept_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AcceptOut:
    """Record trainer acceptance of a recommendation (Sprint 25B).

    Creates an execution record only — no automatic campaign, message, or
    proposal is created.  Human action is required after acceptance.
    Returns 404 if recommendation_id does not match any snapshot.
    """
    try:
        return await RecommendationActionService(session).accept(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationActionOut,
    status_code=201,
)
async def dismiss_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: DismissRequest,
    session: AsyncSession = Depends(get_session),
) -> RecommendationActionOut:
    """Record trainer dismissal of a recommendation (Sprint 25B).

    reason is optional.  Returns 404 if recommendation_id not found.
    """
    try:
        return await RecommendationActionService(session).dismiss(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/snooze",
    response_model=RecommendationActionOut,
    status_code=201,
)
async def snooze_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: SnoozeRequest,
    session: AsyncSession = Depends(get_session),
) -> RecommendationActionOut:
    """Snooze a recommendation until a future date (Sprint 25B).

    body.until must be strictly after today; validated by SnoozeRequest.
    Returns 422 for invalid dates, 404 if recommendation_id not found.
    """
    try:
        return await RecommendationActionService(session).snooze(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            until=body.until,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Sprint 26A — Recommendation Work Queue ────────────────────────────────────


@router.get("/recommendations/work-queue", response_model=WorkQueueOut)
async def get_recommendation_work_queue(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> WorkQueueOut:
    """Return accepted recommendations grouped by execution status (Sprint 26A).

    Groups: ready (not started), in_progress, blocked, completed, cancelled.
    Redis-cached 5 minutes per workspace; invalidated on every mutation.
    Starting work never auto-creates campaigns, sends messages, or updates CRM.
    """
    return await RecommendationExecutionService(session).list_queue(
        workspace_id=workspace_id,
    )


@router.post(
    "/recommendations/{recommendation_id}/start",
    response_model=ExecutionOut,
    status_code=201,
)
async def start_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ExecutionOut:
    """Mark an accepted recommendation as in-progress (Sprint 26A).

    Valid from: accepted (execution_status=None) or blocked.
    Returns 404 if the recommendation has not been accepted.
    Returns 422 if the transition is invalid (e.g. already completed).
    Does NOT auto-create any campaign, send any message, or touch CRM.
    """
    try:
        return await RecommendationExecutionService(session).start(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/block",
    response_model=ExecutionOut,
    status_code=201,
)
async def block_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: BlockRequest,
    session: AsyncSession = Depends(get_session),
) -> ExecutionOut:
    """Mark an in-progress recommendation as blocked (Sprint 26A).

    Valid from: in_progress only.  reason is required.
    Returns 422 for invalid transitions or missing reason.
    """
    try:
        return await RecommendationExecutionService(session).block(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/complete",
    response_model=ExecutionOut,
    status_code=201,
)
async def complete_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: CompleteRequest,
    session: AsyncSession = Depends(get_session),
) -> ExecutionOut:
    """Mark an in-progress recommendation as completed (Sprint 26A).

    Valid from: in_progress only.  notes is optional.
    Completed is a terminal state — no further transitions allowed.
    """
    try:
        return await RecommendationExecutionService(session).complete(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/recommendations/{recommendation_id}/cancel",
    response_model=ExecutionOut,
    status_code=201,
)
async def cancel_recommendation(
    recommendation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: CancelRequest,
    session: AsyncSession = Depends(get_session),
) -> ExecutionOut:
    """Cancel an accepted recommendation (Sprint 26A).

    Valid from: accepted (not started) or blocked.
    Cancelled is a terminal state — no further transitions allowed.
    reason is optional.
    """
    try:
        return await RecommendationExecutionService(session).cancel(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Sprint 26B — Recommendation Outcome Tracking ─────────────────────────────


@router.get("/recommendations/execution-summary", response_model=ExecutionSummaryOut)
async def get_execution_summary(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ExecutionSummaryOut:
    """Aggregate execution metrics derived from recommendation_actions (Sprint 26B).

    Returns rates (completion, cancellation, block) and averages (days to start,
    complete, blocked, cancelled) computed deterministically from timestamps.
    Does not trigger any work, campaign, send, or CRM update.
    """
    return await RecommendationOutcomeService(session).get_execution_summary(
        workspace_id=workspace_id,
    )


@router.get("/recommendations/outcomes", response_model=RecommendationOutcomesOut)
async def get_recommendation_outcomes(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RecommendationOutcomesOut:
    """Per-type execution breakdown derived from recommendation_actions (Sprint 26B).

    Groups accepted recommendations by rec_type from the snapshot, then computes
    per-type: accepted, completed, cancelled, blocked, completion_rate,
    avg_days_to_complete, avg_days_to_start.
    Read-only — does not modify any data.
    """
    return await RecommendationOutcomeService(session).get_outcomes(
        workspace_id=workspace_id,
    )


# Silence ruff F401 — OutcomeTypeItemOut is used as a nested type in RecommendationOutcomesOut
_REFERENCED_TYPES = (OutcomeTypeItemOut,)


# ── Sprint 27 — Recommendation Learning & Versioning ─────────────────────────


@router.get("/recommendations/learning", response_model=LearningOut)
async def get_recommendation_learning(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> LearningOut:
    """Return version comparison and change summary for recommendations (Sprint 27).

    Compares the current recommendation generation epoch (snapshot_date) against
    the previous epoch.  All metrics are derived deterministically from existing
    tables — no AI, no writes, no recommendation changes.
    insufficient_data=True when fewer than 2 generation epochs exist.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationLearningService(session).get_learning(
        workspace_id=workspace_id,
    )


@router.get("/recommendations/version-history", response_model=VersionHistoryOut)
async def get_recommendation_version_history(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> VersionHistoryOut:
    """Return chronological history of all recommendation version epochs (Sprint 27).

    Each entry is one snapshot_date with aggregated acted, successful, avg_confidence,
    and quality_score metrics.  Newest epoch first.
    insufficient_data=True when fewer than 2 epochs exist.
    Redis-cached 1 hour per workspace.
    """
    return await RecommendationLearningService(session).get_version_history(
        workspace_id=workspace_id,
    )
