"""Analytics schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, computed_field, field_validator


class DailyRollupOut(BaseModel):
    rollup_date: date
    channel: str | None
    outreach_sent: int
    outreach_delivered: int
    outreach_opened: int
    outreach_replied: int
    compliance_blocks: int
    meetings_scheduled: int
    meetings_completed: int
    leads_created: int
    leads_booked: int
    proposals_generated: int
    proposals_approved: int
    proposals_sent: int
    ai_spend_inr: float
    # Sprint 18A revenue columns
    proposals_accepted: int = 0
    closed_revenue_inr: float = 0.0
    model_config = {"from_attributes": True}


class AnalyticsSummary(BaseModel):
    period_days: int
    total_sent: int
    total_delivered: int
    total_replied: int
    reply_rate: float        # 0.0-1.0
    delivery_rate: float     # 0.0-1.0
    total_spend_inr: float
    meetings_scheduled: int
    meetings_completed: int
    leads_created: int
    leads_booked: int
    proposals_generated: int
    proposals_approved: int
    proposals_sent: int
    # Sprint 18A revenue fields
    proposals_accepted: int = 0
    closed_revenue_inr: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proposal_approval_rate(self) -> float:
        if self.proposals_generated == 0:
            return 0.0
        return round(self.proposals_approved / self.proposals_generated, 4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def booking_rate(self) -> float:
        """Ratio of booked leads to total proposals sent — the headline conversion."""
        if self.proposals_sent == 0:
            return 0.0
        return round(self.leads_booked / self.proposals_sent, 4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def win_rate(self) -> float:
        """Ratio of client-accepted proposals to proposals sent — true win rate."""
        if self.proposals_sent == 0:
            return 0.0
        return round(self.proposals_accepted / self.proposals_sent, 4)


class AnalyticsTrendOut(BaseModel):
    """One day in a trend series — used by GET /analytics/trend."""

    rollup_date: date
    outreach_sent: int
    outreach_replied: int
    leads_created: int
    leads_booked: int
    proposals_sent: int
    ai_spend_inr: float
    model_config = {"from_attributes": True}


class AnalyticsFunnelOut(BaseModel):
    """Trainer revenue funnel — live counts from transactional tables."""

    contacts: int
    outreach_sent: int
    replies: int
    meetings: int
    proposals: int
    bookings: int
    # Sprint 18A revenue fields — live from proposals table
    proposals_accepted: int = 0
    pipeline_value_inr: float = 0.0   # open proposals (sent, no client response)
    closed_revenue_inr: float = 0.0   # accepted proposals
    win_rate: float = 0.0             # proposals_accepted / proposals_sent


class AnalyticsChannelSummary(BaseModel):
    """Per-channel outreach performance summary.

    sent / delivered / opened roll up from analytics_daily (channel-specific rows).
    failed is computed live from outbound_messages because analytics_daily has
    no outreach_failed column — same pattern as get_funnel().
    delivery_rate and read_rate are computed fields clamped to [0.0, 1.0].
    """

    channel: str
    period_days: int
    sent: int
    delivered: int
    opened: int
    failed: int
    compliance_blocks: int
    delivery_rate: float   # delivered / sent
    read_rate: float       # opened / delivered


# ── Sprint 19 — Campaign ROI ──────────────────────────────────────────────────


class CampaignROISummary(BaseModel):
    """Single campaign row in the ROI table.

    sample_size / low_confidence satisfy the Amendment 2 confidence metadata
    requirement.  sample_size = proposals_sent (win_rate requires a meaningful
    denominator).  low_confidence = sample_size < 5.

    avg_days_to_accept = AVG(client_accepted_at − sent_at) in calendar days
    (Amendment 1).  None when no accepted proposals exist for this campaign.
    """

    campaign_id: uuid.UUID
    campaign_name: str
    channel: str
    campaign_status: str
    recipients_count: int
    messages_sent: int
    messages_delivered: int
    replies_received: int
    leads_created: int
    proposals_sent: int
    proposals_accepted: int
    win_rate: float
    closed_revenue_inr: float
    avg_deal_size_inr: float | None
    avg_days_to_accept: float | None
    last_refreshed_at: datetime
    # Confidence metadata (Amendment 2)
    sample_size: int
    low_confidence: bool
    model_config = {"from_attributes": True}


class CampaignROIListOut(BaseModel):
    """Paginated campaign ROI response.

    attribution_model is always 'all_touch' (Amendment 3) — surfaced in the
    response so the frontend can render a tooltip explaining the model.
    """

    items: list[CampaignROISummary]
    total: int
    attribution_model: str = "all_touch"


# ── Sprint 19 — Intelligence endpoints ───────────────────────────────────────


class TopicStat(BaseModel):
    """Revenue and win-rate performance for one trainer topic tag."""

    topic: str
    proposals_sent: int
    proposals_accepted: int
    win_rate: float
    closed_revenue_inr: float


class TopicPerformanceOut(BaseModel):
    """Response for GET /analytics/topics.

    sample_size = total proposals_sent in workspace (Amendment 2).
    low_confidence = sample_size < 5.
    """

    items: list[TopicStat]
    workspace_id: str
    generated_at: datetime
    sample_size: int
    low_confidence: bool


class IndustryStat(BaseModel):
    """Revenue and win-rate performance for one industry bucket.

    industry = 'Unknown' when companies.industry IS NULL.
    """

    industry: str
    proposals_sent: int
    proposals_accepted: int
    win_rate: float
    closed_revenue_inr: float


class IndustryPerformanceOut(BaseModel):
    """Response for GET /analytics/industries.

    unknown_count = proposals linked to contacts whose company has no industry.
    sample_size = total proposals_sent in workspace (Amendment 2).
    low_confidence = sample_size < 5.
    """

    items: list[IndustryStat]
    workspace_id: str
    generated_at: datetime
    unknown_count: int
    sample_size: int
    low_confidence: bool


class PricingCalibrationOut(BaseModel):
    """Pricing calibration: stated trainer range vs actual accepted proposal values.

    sample_size = accepted proposals with non-null actual_value_inr (Amendment 2).
    low_confidence = sample_size < 5.
    avg_days_to_accept is the workspace-wide average across all accepted proposals.
    """

    workspace_id: str
    stated_min_inr: int | None
    stated_max_inr: int | None
    actual_min_inr: float | None
    actual_max_inr: float | None
    actual_avg_inr: float | None
    actual_median_inr: float | None
    avg_days_to_accept: float | None
    sample_size: int
    low_confidence: bool
    generated_at: datetime


# ── Sprint 20A — Deterministic Recommendations ───────────────────────────────


class RecommendationItem(BaseModel):
    """A single deterministic recommendation with full confidence metadata.

    Every title and rationale string is constructed from the raw numbers in
    supporting_data — independently verifiable from first principles.
    No LLM involvement; all strings are deterministic formatted templates.

    evidence_strength is a UX-layer label for the confidence_score:
      0–39   → "weak"
      40–69  → "moderate"
      70–100 → "strong"
    """

    type: str                               # industry | topic | pricing | campaign | channel
    title: str
    rationale: str
    action: str
    supporting_data: dict[str, float | int | str | None]
    confidence_score: int                   # 0–100
    confidence_level: str                   # low | medium | high
    evidence_strength: str                  # weak | moderate | strong
    sample_size: int
    low_confidence: bool
    generated_at: datetime


class RecommendationsOut(BaseModel):
    """Response for GET /analytics/recommendations.

    All 5 recommendation types are attempted.  Items below the hard minimum
    sample threshold or with confidence_score < 20 are suppressed — excluded
    from recommendations[] and counted in suppressed_count so the frontend
    can show "N more recommendations unlock when you have more data."
    """

    workspace_id: str
    generated_at: datetime
    period_days: int
    recommendations: list[RecommendationItem]
    suppressed_count: int
    total: int


# ── Sprint 20B — AI Insight Layer ────────────────────────────────────────────


class InsightOpportunity(BaseModel):
    """A single opportunity surfaced by the AI narrative layer.

    title and confidence_level are copied verbatim from the source
    RecommendationItem — the AI may not alter confidence values.
    """

    title: str
    rationale: str
    confidence_level: str   # low | medium | high (mirrored from source recommendation)


class InsightRisk(BaseModel):
    """A risk identified by the AI narrative layer from the recommendations data."""

    title: str
    description: str


class AnalyticsInsightOut(BaseModel):
    """Response for GET /analytics/insights.

    Generated by a single cheap LLM call over the deterministic RecommendationsOut
    payload.  The AI summarises, prioritises, and explains — it never creates new
    recommendations or alters confidence scores.

    data_limitations contains one entry per low-confidence recommendation so the
    frontend can surface caveat messaging alongside each insight.
    """

    generated_at: datetime
    executive_summary: str
    top_opportunities: list[InsightOpportunity]
    risks: list[InsightRisk]
    data_limitations: list[str]


# ── Sprint 21 — Recommendation Tracking ──────────────────────────────────────

_VALID_REC_TYPES: frozenset[str] = frozenset(
    {"industry", "topic", "pricing", "campaign", "channel"}
)
_VALID_OUTCOMES: frozenset[str] = frozenset({"helpful", "not_helpful", "dismissed"})


class RecommendationFeedbackIn(BaseModel):
    """Request body for POST /analytics/recommendations/feedback.

    rec_type must be one of the 5 deterministic recommendation types.
    outcome must be helpful | not_helpful | dismissed (amendment: dismissed
    replaces the implicit 'ignored' state, which is inferred at 30-day mark).
    notes is optional free text; max 500 chars; Presidio-scrubbed at service layer.
    """

    workspace_id: uuid.UUID
    rec_type: str
    outcome: str
    notes: str | None = None

    @field_validator("rec_type")
    @classmethod
    def validate_rec_type(cls, v: str) -> str:
        if v not in _VALID_REC_TYPES:
            raise ValueError(
                f"rec_type must be one of {sorted(_VALID_REC_TYPES)}, got '{v}'"
            )
        return v

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        if v not in _VALID_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(_VALID_OUTCOMES)}, got '{v}'"
            )
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("notes must not exceed 500 characters")
        return v


class RecommendationFeedbackOut(BaseModel):
    """Response from POST /analytics/recommendations/feedback."""

    snapshot_id: uuid.UUID
    rec_type: str
    outcome: str
    recorded_at: datetime


class RecommendationQualityItem(BaseModel):
    """Quality metrics for one recommendation type in a workspace.

    In Sprint 21 quality_score is driven by feedback only:
      quality_score = round(helpful / total_feedback * 100)
      NULL when total_feedback < 3 (low_confidence = True).

    adoption_rate and success_rate are stored but zero in Sprint 21 —
    outcome detection for industry/topic/pricing types is Sprint 22.
    """

    rec_type: str
    shown_count: int
    acted_count: int
    success_count: int
    ignored_count: int
    feedback_helpful: int
    feedback_not_helpful: int
    feedback_dismissed: int
    adoption_rate: float
    success_rate: float
    quality_score: int | None        # None when low_confidence = True
    low_confidence: bool


class RecommendationEffectivenessOut(BaseModel):
    """Response for GET /analytics/recommendations/effectiveness.

    by_type: one item per rec_type that has at least one snapshot in the period.
    overall_quality_score: average of non-None quality scores; None when all types
                           are low_confidence (insufficient feedback data).
    """

    workspace_id: str
    period_days: int
    generated_at: datetime
    by_type: list[RecommendationQualityItem]
    overall_quality_score: int | None


# ── Sprint 22A — Recommendation Health Analytics ─────────────────────────────


class RecEffectivenessSummaryOut(BaseModel):
    """Cross-type adoption and success totals for the effectiveness summary card row."""

    recommendations_generated: int
    recommendations_acted: int
    recommendations_successful: int
    adoption_rate: float   # acted / generated; 0.0 when generated == 0
    success_rate: float    # successful / acted; 0.0 when acted == 0


class RecEffectivenessTypeItemOut(BaseModel):
    """Effectiveness metrics for a single recommendation type.

    quality_score is None when the type is low_confidence (total_feedback < 3).
    """

    recommendation_type: str
    generated: int
    acted: int
    successful: int
    adoption_rate: float
    success_rate: float
    quality_score: int | None


class QualityTrendPointOut(BaseModel):
    """One data point in the quality score trend chart per rec_type per day."""

    score_date: date
    rec_type: str
    quality_score: int | None
    adoption_rate: float
    success_rate: float


class RecEffectivenessOut(BaseModel):
    """Response for GET /analytics/recommendations/effectiveness (Sprint 22A).

    summary:       cross-type totals for the header KPI cards.
    by_type:       one row per rec_type that has at least one quality score row.
    quality_trend: all quality score rows in the period ordered by date asc —
                   used by the frontend trend chart without a separate fetch.
    """

    generated_at: datetime
    summary: RecEffectivenessSummaryOut
    by_type: list[RecEffectivenessTypeItemOut]
    quality_trend: list[QualityTrendPointOut]


class RecCalibrationOverallOut(BaseModel):
    """Success rates grouped by the confidence level band of the source snapshot.

    None when no acted outcomes exist for a given confidence band.
    """

    high_confidence_success_rate: float | None
    medium_confidence_success_rate: float | None
    low_confidence_success_rate: float | None


class RecCalibrationTypeItemOut(BaseModel):
    """Calibration data for one recommendation type.

    predicted_confidence: average confidence_score at generation time (0–100).
    observed_success_rate: success_count / acted_count (0.0–100.0 scale to match).
    calibration_delta: observed_success_rate − predicted_confidence.
      Negative → overconfident (we said high confidence, outcomes were worse).
      Positive → underconfident (outcomes beat our confidence estimate).
    None values when no acted outcomes exist for the type.
    """

    recommendation_type: str
    predicted_confidence: float
    observed_success_rate: float | None
    calibration_delta: float | None


class RecCalibrationOut(BaseModel):
    """Response for GET /analytics/recommendations/calibration (Sprint 22A).

    insufficient_data: True when total acted outcomes < minimum_acted_recommendations.
    minimum_acted_recommendations: the threshold used (5).
    """

    generated_at: datetime
    overall: RecCalibrationOverallOut
    recommendation_types: list[RecCalibrationTypeItemOut]
    insufficient_data: bool = False
    minimum_acted_recommendations: int = 5


# ── Sprint 22B — Recommendation Quality Review ───────────────────────────────


class RecBestWorstPerformerOut(BaseModel):
    """Best or worst performing recommendation type by quality score.

    quality_score is always non-None here — the service only returns a
    performer when at least one type has a non-null quality_score.
    """

    recommendation_type: str
    quality_score: int


class RecIgnoredTypeOut(BaseModel):
    """Most ignored recommendation type.

    ignored_rate = ignored_count / shown_count (0.0–1.0).
    """

    recommendation_type: str
    ignored_rate: float


class RecAdoptedTypeOut(BaseModel):
    """Most adopted recommendation type (highest adoption_rate)."""

    recommendation_type: str
    adoption_rate: float  # 0.0–1.0


class RecSuccessfulTypeOut(BaseModel):
    """Most successful recommendation type (highest success_rate)."""

    recommendation_type: str
    success_rate: float  # 0.0–1.0


class RecCalibrationGroupItemOut(BaseModel):
    """One entry in a calibration classification group (overconfident / underconfident / well_calibrated)."""

    recommendation_type: str
    calibration_delta: float


class RecCalibrationGroupSummaryOut(BaseModel):
    """Trifecta calibration grouping derived from Sprint 22A calibration deltas.

    overconfident:  delta <= -5 (model said high confidence; outcomes were worse)
    underconfident: delta >= +5 (outcomes beat our confidence estimate)
    well_calibrated: abs(delta) < 5
    Types with calibration_delta=None (no acted outcomes) are excluded from all groups.
    """

    overconfident: list[RecCalibrationGroupItemOut]
    underconfident: list[RecCalibrationGroupItemOut]
    well_calibrated: list[RecCalibrationGroupItemOut]


class RecReviewTrendPointOut(BaseModel):
    """Average quality score across all recommendation types for one day.

    quality_score is the mean of all non-null quality_score values on score_date.
    Days where every type is low_confidence (all nulls) are excluded from the trend.
    """

    date: date
    quality_score: float


class RecReviewOut(BaseModel):
    """Response for GET /analytics/recommendations/review (Sprint 22B).

    All fields are None / empty when no quality score rows exist (insufficient_data=True).
    The service never returns a performer field for types with low_confidence quality scores.
    calibration_summary groups are populated from Sprint 22A calibration deltas.
    quality_trend is the daily average quality score (all types aggregated).
    """

    generated_at: datetime
    best_performing_type: RecBestWorstPerformerOut | None
    worst_performing_type: RecBestWorstPerformerOut | None
    most_ignored_type: RecIgnoredTypeOut | None
    most_adopted_type: RecAdoptedTypeOut | None
    most_successful_type: RecSuccessfulTypeOut | None
    calibration_summary: RecCalibrationGroupSummaryOut
    quality_trend: list[RecReviewTrendPointOut]
    insufficient_data: bool = False


# ── Sprint 23A — Calibration Validation & Quality Score Stability ─────────────


class ConfidenceDistributionOut(BaseModel):
    """Count of recommendation snapshots in each confidence level band.

    Populated from recommendation_snapshots.confidence_level for the period.
    """

    high: int
    medium: int
    low: int


class CalibrationAccuracyOut(BaseModel):
    """Count of rec_types in each directional accuracy bucket.

    Uses the same sign-based thresholds as Sprint 22B trifecta:
      well_calibrated_count: abs(delta) < 5
      overconfident_count:   delta <= -5
      underconfident_count:  delta >= +5
    Types with calibration_delta=None are excluded from all counts.
    """

    well_calibrated_count: int
    overconfident_count: int
    underconfident_count: int


class CalibrationReviewTypeItemOut(BaseModel):
    """Per-type calibration item with Sprint 23A severity classification.

    calibration_severity (based on abs(calibration_delta)):
      "calibrated" when abs(delta) < 5
      "warning"    when 5 <= abs(delta) <= 15
      "severe"     when abs(delta) > 15
      None         when calibration_delta is None (no acted outcomes yet)
    """

    recommendation_type: str
    predicted_confidence: float
    observed_success_rate: float | None
    calibration_delta: float | None
    calibration_severity: str | None  # "calibrated" | "warning" | "severe" | None


class CalibrationReviewOut(BaseModel):
    """Response for GET /analytics/recommendations/calibration-review (Sprint 23A).

    Reuses RecCalibrationOverallOut from Sprint 22A for the per-band success rates.
    confidence_distribution: count of snapshots by confidence_level band.
    accuracy:                directional count of rec_types (overconfident/underconfident/calibrated).
    recommendation_types:    per-type items with new severity classification.
    insufficient_data:       True when total acted outcomes < 5 (same threshold as 22A).
    """

    generated_at: datetime
    overall: RecCalibrationOverallOut
    confidence_distribution: ConfidenceDistributionOut
    accuracy: CalibrationAccuracyOut
    recommendation_types: list[CalibrationReviewTypeItemOut]
    insufficient_data: bool = False


class QualityScoreStabilityOut(BaseModel):
    """Overall quality score stability computed across all rec_types.

    stability_rating (based on std_dev):
      "stable"   when std_dev < 5
      "volatile" when 5 <= std_dev <= 15
      "unstable" when std_dev > 15
    """

    average: float
    std_dev: float
    stability_rating: str  # "stable" | "volatile" | "unstable"


class StabilityTypeItemOut(BaseModel):
    """Quality score stability for a single recommendation type.

    average_quality_score and std_dev computed over non-null quality_score
    values in the period from recommendation_quality_scores.
    stability_rating uses the same thresholds as QualityScoreStabilityOut.
    """

    recommendation_type: str
    average_quality_score: float
    std_dev: float
    stability_rating: str  # "stable" | "volatile" | "unstable"


class StabilityOut(BaseModel):
    """Response for GET /analytics/recommendations/stability (Sprint 23A).

    quality_score_stability: aggregate stats across all rec_types.
    recommendation_types:    per-type stability items, sorted alphabetically.
    insufficient_data:       True when no quality score rows exist in the period.
    """

    generated_at: datetime
    quality_score_stability: QualityScoreStabilityOut
    recommendation_types: list[StabilityTypeItemOut]
    insufficient_data: bool = False


# ── Sprint 23B — Confidence Drift Detection & Recommendation Reliability ──────


class MetricTrendOut(BaseModel):
    """Trend comparison for a single metric between two equal time windows.

    current:   average value in the current period (0–100 scale).
    previous:  average value in the prior period (0–100 scale).
    change:    current − previous (positive = improvement).
    direction: "improving" (change > 5) | "stable" | "declining" (change < −5).

    adoption_rate and success_rate are stored as 0–1 fractions and converted
    to 0–100 percentage before the change threshold is applied.
    """

    current: float
    previous: float
    change: float
    direction: str  # "improving" | "stable" | "declining"


class DriftOverallOut(BaseModel):
    """Cross-type drift for quality_score, adoption_rate, and success_rate."""

    quality_score: MetricTrendOut
    adoption_rate: MetricTrendOut
    success_rate: MetricTrendOut


class DriftTypeItemOut(BaseModel):
    """Quality score drift for a single recommendation type.

    Only quality_score is included per-type; adoption_rate and success_rate
    are aggregated at the overall level only.
    """

    recommendation_type: str
    quality_score: MetricTrendOut


class DriftOut(BaseModel):
    """Response for GET /analytics/recommendations/drift (Sprint 23B).

    overall:           cross-type drift for all three key metrics.
    by_type:           quality_score drift per rec_type.
    insufficient_data: True when the previous window has no rows
                       (workspace needs ≥ 60 days of history to measure drift).
    """

    generated_at: datetime
    overall: DriftOverallOut
    by_type: list[DriftTypeItemOut]
    insufficient_data: bool = False


class ReliabilityOverallOut(BaseModel):
    """Overall workspace reliability score and rating.

    score:  weighted composite on 0–100 scale.
            Formula: success_rate_pct × 0.5 + adoption_rate_pct × 0.3 + quality_score × 0.2.
    rating: "high" (≥ 75) | "medium" (50–74) | "low" (< 50).
    When quality_score is None (low_confidence), it contributes 0.0 to the formula.
    """

    score: float
    rating: str  # "high" | "medium" | "low"


class ReliabilityTypeItemOut(BaseModel):
    """Reliability score and rating for a single recommendation type.

    reliability_score uses the same formula as ReliabilityOverallOut.score.
    """

    recommendation_type: str
    reliability_score: float
    rating: str  # "high" | "medium" | "low"


class ReliabilityOut(BaseModel):
    """Response for GET /analytics/recommendations/reliability (Sprint 23B).

    overall_reliability:   workspace-level composite score and rating.
    recommendation_types:  per-type scores sorted alphabetically by rec_type.
    insufficient_data:     True when no quality score rows exist in the period.
    """

    generated_at: datetime
    overall_reliability: ReliabilityOverallOut
    recommendation_types: list[ReliabilityTypeItemOut]
    insufficient_data: bool = False


# ── Sprint 24A — Recommendation Lifecycle Observatory ─────────────────────────


class LifecycleTypeItemOut(BaseModel):
    """Per-recommendation-type lifecycle stats (Sprint 24A).

    avg_days_to_action:   mean days between snapshot.generated_at and outcome.acted_at
                          for acted=True outcomes with non-null acted_at.
    avg_days_to_success:  mean days between snapshot.generated_at and success_measured_at
                          for success=True outcomes with non-null success_measured_at.
    acted_rate:           acted count / total outcome count * 100.
    success_rate:         success=True count / total outcome count * 100.
    """

    recommendation_type: str
    avg_days_to_action: float
    avg_days_to_success: float
    acted_rate: float
    success_rate: float


class LifecycleOverallOut(BaseModel):
    """Workspace-level aggregate lifecycle stats (Sprint 24A)."""

    avg_days_to_action: float
    avg_days_to_success: float
    acted_rate: float
    success_rate: float


class LifecycleOut(BaseModel):
    """Response for GET /analytics/recommendations/lifecycle (Sprint 24A).

    overall:               workspace-level timing and conversion summary.
    recommendation_types:  per-type stats sorted alphabetically by rec_type.
    insufficient_data:     True when no outcome rows exist in the period.
    """

    generated_at: datetime
    overall: LifecycleOverallOut
    recommendation_types: list[LifecycleTypeItemOut]
    insufficient_data: bool = False


class DecayBucketOut(BaseModel):
    """Recommendation effectiveness for one age bucket (Sprint 24A).

    age_bucket:   "0-7" | "8-30" | "31-60" | "60+"
                  (age = date.today() - snapshot_date, in days)
    acted_rate:   acted count / sample_size * 100 (0.0 when sample_size == 0).
    success_rate: success=True count / sample_size * 100 (0.0 when sample_size == 0).
    sample_size:  number of outcome rows falling into this bucket.
    """

    age_bucket: str
    acted_rate: float
    success_rate: float
    sample_size: int


class DecayTypeItemOut(BaseModel):
    """Per-type decay detection result (Sprint 24A).

    best_bucket:     age_bucket string with the highest success_rate (non-empty buckets only).
    worst_bucket:    age_bucket string with the lowest  success_rate (non-empty buckets only).
    decay_detected:  True when best_success_rate - worst_success_rate >= 10 points.
    """

    recommendation_type: str
    best_bucket: str
    worst_bucket: str
    decay_detected: bool


class DecayOut(BaseModel):
    """Response for GET /analytics/recommendations/decay (Sprint 24A).

    buckets:              all 4 age brackets in canonical order; empty buckets have
                          sample_size=0 and rates 0.0.
    recommendation_types: per-type decay detection; only types with outcomes in
                          >= 2 non-empty buckets are included.
    """

    generated_at: datetime
    buckets: list[DecayBucketOut]
    recommendation_types: list[DecayTypeItemOut]


# ── Sprint 24B — Recommendation Portfolio & Coverage ─────────────────────────


class PortfolioTypeItemOut(BaseModel):
    """Per-type recommendation distribution stats (Sprint 24B).

    percentage: count / total_recommendations * 100; 0.0 when total is 0.
    acted_rate: acted outcomes / total outcomes for the type * 100.
    success_rate: success=True outcomes / total outcomes for the type * 100.
    Both rates are 0.0 when no outcome rows exist for the type in the period.
    """

    recommendation_type: str
    count: int
    percentage: float
    acted_rate: float
    success_rate: float


class PortfolioBalanceOut(BaseModel):
    """Shannon entropy diversity index and balance rating (Sprint 24B).

    diversity_index: normalized Shannon entropy H / ln(n_types) * 100 (0–100).
    balance_rating:  "excellent" (80–100) | "good" (60–79) |
                     "moderate" (40–59) | "poor" (<40).
    """

    diversity_index: float
    balance_rating: str  # "excellent" | "good" | "moderate" | "poor"


class PortfolioOut(BaseModel):
    """Response for GET /analytics/recommendations/portfolio (Sprint 24B).

    dominant_type:   rec_type with the highest count; None when no data.
    least_used_type: rec_type with the lowest count; None when no data.
    insufficient_data: True when no snapshot rows exist in the period.
    """

    generated_at: datetime
    total_recommendations: int
    recommendation_types: list[PortfolioTypeItemOut]
    dominant_type: str | None
    least_used_type: str | None
    portfolio_balance: PortfolioBalanceOut
    insufficient_data: bool = False


class CoverageItemOut(BaseModel):
    """Coverage row for one recommendation type (Sprint 24B).

    present:                  True when at least one snapshot exists for this type.
    count:                    total snapshot count in the analysis period.
    last_generated_at:        most recent snapshot_date for this type (all time); None when absent.
    days_since_last_generated: today - last_generated_at in days; None when absent.
    """

    recommendation_type: str
    present: bool
    count: int
    last_generated_at: date | None
    days_since_last_generated: int | None


class CoverageOut(BaseModel):
    """Response for GET /analytics/recommendations/coverage (Sprint 24B).

    coverage:      one row per known recommendation type (sorted alphabetically).
    missing_types: rec_types with no snapshots ever.
    stale_types:   rec_types with days_since_last_generated > 30.
    """

    generated_at: datetime
    coverage: list[CoverageItemOut]
    missing_types: list[str]
    stale_types: list[str]


# ── Sprint 25A — Recommendation Evidence Explorer ────────────────────────────


class EvidenceMetricOut(BaseModel):
    """One row in the supporting_metrics table.

    value is float|None so all metric types (score, rate, count) share one schema.
    source identifies which table/service produced the value.
    """

    name: str
    value: float | None
    source: str


class EvidenceSummaryOut(BaseModel):
    """Aggregated evidence block for a single recommendation type (Sprint 25A).

    All fields are observational — no AI, no new persistence.
    None means the metric could not be computed (insufficient data for that signal).
    """

    generated_count: int
    portfolio_percentage: float
    confidence_average: float | None
    quality_score: int | None
    acted_rate: float
    success_rate: float
    reliability_score: float | None
    reliability_rating: str | None
    avg_days_to_action: float
    avg_days_to_success: float
    drift_direction: str | None
    stability_rating: str | None
    calibration_status: str | None
    coverage_status: str
    last_generated_at: date | None
    days_since_last_generated: int | None


class EvidenceOut(BaseModel):
    """Response for GET /analytics/recommendations/evidence/{recommendation_type} (Sprint 25A).

    Assembles all available evidence for a single recommendation type by
    orchestrating existing Sprint 21–24 analytics services.  Deterministic.
    """

    generated_at: datetime
    recommendation_type: str
    summary: EvidenceSummaryOut
    supporting_metrics: list[EvidenceMetricOut]
    insufficient_data: bool = False


# ── Sprint 25B — Recommendation Action Center ────────────────────────────────


class SnoozeRequest(BaseModel):
    """Request body for POST /recommendations/{id}/snooze."""

    until: date

    @field_validator("until")
    @classmethod
    def until_must_be_future(cls, v: date) -> date:
        from datetime import date as _date

        if v <= _date.today():
            raise ValueError("snooze until date must be in the future")
        return v


class DismissRequest(BaseModel):
    """Request body for POST /recommendations/{id}/dismiss."""

    reason: str | None = None


class RecommendationActionOut(BaseModel):
    """Single recommendation action record."""

    id: uuid.UUID
    recommendation_id: uuid.UUID
    action_type: str
    status: str
    reason: str | None
    snooze_until: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AcceptOut(BaseModel):
    """Response for POST /recommendations/{id}/accept."""

    status: str
    accepted_at: datetime
    recommendation_id: uuid.UUID


class RecommendationActionsListOut(BaseModel):
    """Grouped action list for GET /recommendations/actions."""

    accepted: list[RecommendationActionOut]
    dismissed: list[RecommendationActionOut]
    snoozed: list[RecommendationActionOut]
    completed: list[RecommendationActionOut]
    expired: list[RecommendationActionOut]
    total: int


# ── Sprint 26A — Recommendation Work Queue ────────────────────────────────────


class BlockRequest(BaseModel):
    reason: str


class CompleteRequest(BaseModel):
    notes: str | None = None


class CancelRequest(BaseModel):
    reason: str | None = None


class ExecutionOut(BaseModel):
    """Execution state for a single recommendation_actions row."""

    recommendation_id: uuid.UUID
    action_type: str
    execution_status: str | None
    started_at: datetime | None
    completed_at: datetime | None
    blocked_at: datetime | None
    cancelled_at: datetime | None
    blocked_reason: str | None
    completion_notes: str | None

    model_config = {"from_attributes": True}


class WorkQueueGroupOut(BaseModel):
    """One row in the work queue, includes snapshot title for display."""

    recommendation_id: uuid.UUID
    title: str
    action_type: str
    execution_status: str | None
    started_at: datetime | None
    completed_at: datetime | None
    blocked_at: datetime | None
    cancelled_at: datetime | None
    blocked_reason: str | None
    completion_notes: str | None
    accepted_at: datetime


class WorkQueueOut(BaseModel):
    """Grouped work queue for GET /recommendations/work-queue."""

    ready: list[WorkQueueGroupOut]
    in_progress: list[WorkQueueGroupOut]
    blocked: list[WorkQueueGroupOut]
    completed: list[WorkQueueGroupOut]
    cancelled: list[WorkQueueGroupOut]
    timeline: list[WorkQueueGroupOut]
    total: int


# ── Sprint 26B — Recommendation Outcome Tracking ─────────────────────────────


class ExecutionSummaryOut(BaseModel):
    """Aggregate execution metrics for GET /recommendations/execution-summary."""

    accepted: int
    started: int
    completed: int
    blocked: int
    cancelled: int
    completion_rate: float
    cancellation_rate: float
    block_rate: float
    avg_days_to_start: float
    avg_days_to_complete: float
    avg_days_blocked: float
    avg_days_cancelled: float
    work_in_progress: int
    overdue: int
    insufficient_data: bool


class OutcomeTypeItemOut(BaseModel):
    """Per rec_type execution breakdown row."""

    rec_type: str
    accepted: int
    completed: int
    cancelled: int
    blocked: int
    completion_rate: float
    avg_days_to_complete: float
    avg_days_to_start: float


class RecommendationOutcomesOut(BaseModel):
    """Response for GET /recommendations/outcomes."""

    completed: int
    blocked: int
    cancelled: int
    in_progress: int
    ready: int
    by_rec_type: list[OutcomeTypeItemOut]
    insufficient_data: bool


# ── Sprint 27 — Recommendation Learning & Versioning ─────────────────────────


class LearningVersionOut(BaseModel):
    """Metrics for one recommendation generation epoch.

    version = snapshot_date.isoformat() — each distinct snapshot_date is a
    version epoch representing one run of the recommendation engine.
    first_seen / last_seen are both equal to snapshot_date in the current model
    (one row per generation date); exposed as separate fields for future expansion.

    quality_score is None when no recommendation_quality_scores row exists for
    that date (low_confidence or not yet computed).
    """

    version: str               # ISO date: "2026-06-15"
    first_seen: date
    last_seen: date
    recommendations_generated: int
    acted: int
    completed: int
    successful: int
    avg_confidence: float
    quality_score: float | None


class LearningComparisonOut(BaseModel):
    """Delta between current and previous version for each key metric.

    All deltas use the convention: current − previous.
    Positive = improvement; negative = regression.
    None when the metric could not be computed for either version.

    quality_delta:    avg quality_score change (points, 0–100 scale).
    success_delta:    successful/acted rate change (percentage points).
    confidence_delta: avg_confidence change (points, 0–100 scale).
    adoption_delta:   acted/generated rate change (percentage points).
    execution_delta:  successful/generated rate change (percentage points).
    """

    quality_delta: float | None
    success_delta: float | None
    confidence_delta: float | None
    adoption_delta: float | None
    execution_delta: float | None


class LearningSummaryOut(BaseModel):
    """Human-readable deterministic summary of version changes.

    Generated by _build_summary() — pure string templates, no AI.
    Each line is one complete sentence. Empty list when no comparison is possible.
    """

    lines: list[str]


class VersionHistoryOut(BaseModel):
    """Chronological (newest first) list of all recommendation version epochs.

    insufficient_data = True when fewer than 2 version epochs exist
    (not enough history to show meaningful progression).
    """

    versions: list[LearningVersionOut]
    total_versions: int
    insufficient_data: bool


class LearningOut(BaseModel):
    """Response for GET /recommendations/learning.

    current_version / previous_version are ISO date strings.
    comparison is None when there is only one version epoch.
    summary.lines gives the human-readable change narrative.
    insufficient_data = True when fewer than 2 version epochs exist.
    """

    generated_at: datetime
    current_version: str | None
    previous_version: str | None
    comparison: LearningComparisonOut | None
    summary: LearningSummaryOut
    insufficient_data: bool
