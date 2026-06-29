export interface AnalyticsSummary {
  period_days: number;
  total_sent: number;
  total_delivered: number;
  total_replied: number;
  reply_rate: number;
  delivery_rate: number;
  total_spend_inr: number;
  meetings_scheduled: number;
  meetings_completed: number;
  leads_created: number;
  leads_booked: number;
  proposals_generated: number;
  proposals_approved: number;
  proposals_sent: number;
  proposal_approval_rate: number;
  booking_rate: number;
  // Sprint 18A revenue fields
  proposals_accepted: number;
  closed_revenue_inr: number;
  win_rate: number;
}

export interface DailyRollup {
  rollup_date: string;
  outreach_sent: number;
  outreach_replied: number;
  leads_created: number;
  leads_booked: number;
  proposals_sent: number;
  ai_spend_inr: number;
}

export interface AnalyticsFunnel {
  contacts: number;
  outreach_sent: number;
  replies: number;
  meetings: number;
  proposals: number;
  bookings: number;
  // Sprint 18A revenue fields
  proposals_accepted: number;
  pipeline_value_inr: number;
  closed_revenue_inr: number;
  win_rate: number;
}

export interface AnalyticsChannelSummary {
  channel: string;
  period_days: number;
  sent: number;
  delivered: number;
  opened: number;
  failed: number;
  compliance_blocks: number;
  delivery_rate: number;  // 0.0–1.0
  read_rate: number;      // 0.0–1.0
}

// ── Sprint 19 — Campaign ROI ──────────────────────────────────────────────────

export interface CampaignROISummary {
  campaign_id: string;
  campaign_name: string;
  channel: string;
  campaign_status: string;
  recipients_count: number;
  messages_sent: number;
  messages_delivered: number;
  replies_received: number;
  leads_created: number;
  proposals_sent: number;
  proposals_accepted: number;
  win_rate: number;
  closed_revenue_inr: number;
  avg_deal_size_inr: number | null;
  avg_days_to_accept: number | null;
  last_refreshed_at: string;
  sample_size: number;
  low_confidence: boolean;
}

export interface CampaignROIListOut {
  items: CampaignROISummary[];
  total: number;
  /** Always "all_touch" — revenue is credited to every campaign a contact appeared in. */
  attribution_model: string;
}

// ── Sprint 19 — Intelligence endpoints ───────────────────────────────────────

export interface TopicStat {
  topic: string;
  proposals_sent: number;
  proposals_accepted: number;
  win_rate: number;
  closed_revenue_inr: number;
}

export interface TopicPerformanceOut {
  items: TopicStat[];
  workspace_id: string;
  generated_at: string;
  sample_size: number;
  low_confidence: boolean;
}

export interface IndustryStat {
  industry: string;
  proposals_sent: number;
  proposals_accepted: number;
  win_rate: number;
  closed_revenue_inr: number;
}

export interface IndustryPerformanceOut {
  items: IndustryStat[];
  workspace_id: string;
  generated_at: string;
  unknown_count: number;
  sample_size: number;
  low_confidence: boolean;
}

export interface PricingCalibrationOut {
  workspace_id: string;
  stated_min_inr: number | null;
  stated_max_inr: number | null;
  actual_min_inr: number | null;
  actual_max_inr: number | null;
  actual_avg_inr: number | null;
  actual_median_inr: number | null;
  avg_days_to_accept: number | null;
  sample_size: number;
  low_confidence: boolean;
  generated_at: string;
}

// ── Sprint 20B — AI Insight Layer ────────────────────────────────────────────

export interface InsightOpportunity {
  title: string;
  rationale: string;
  /** Mirrors confidence_level from source recommendation — never altered by AI. */
  confidence_level: string;  // "low" | "medium" | "high"
}

export interface InsightRisk {
  title: string;
  description: string;
}

export interface AnalyticsInsightOut {
  generated_at: string;
  executive_summary: string;
  top_opportunities: InsightOpportunity[];
  risks: InsightRisk[];
  data_limitations: string[];
}

// ── Sprint 20A — Deterministic Recommendations ───────────────────────────────

export interface RecommendationItem {
  /** "industry" | "topic" | "pricing" | "campaign" | "channel" */
  type: string;
  title: string;
  rationale: string;
  action: string;
  /** Raw numbers backing the recommendation — type depends on `type` field. */
  supporting_data: Record<string, number | string | null>;
  confidence_score: number;         // 0–100
  confidence_level: string;         // "low" | "medium" | "high"
  evidence_strength: string;        // "weak" | "moderate" | "strong"
  sample_size: number;
  low_confidence: boolean;
  generated_at: string;
}

export interface RecommendationsOut {
  workspace_id: string;
  generated_at: string;
  period_days: number;
  recommendations: RecommendationItem[];
  suppressed_count: number;
  total: number;
}

// ── Sprint 21 — Recommendation Tracking ──────────────────────────────────────

export type RecommendationFeedbackOutcome = "helpful" | "not_helpful" | "dismissed";

export interface RecommendationFeedbackIn {
  workspace_id: string;
  rec_type: string;
  outcome: RecommendationFeedbackOutcome;
  notes?: string | null;
}

export interface RecommendationFeedbackOut {
  snapshot_id: string;
  rec_type: string;
  outcome: RecommendationFeedbackOutcome;
  recorded_at: string;
}

export interface RecommendationQualityItem {
  rec_type: string;
  shown_count: number;
  acted_count: number;
  success_count: number;
  ignored_count: number;
  feedback_helpful: number;
  feedback_not_helpful: number;
  feedback_dismissed: number;
  adoption_rate: number;
  success_rate: number;
  /** null when total_feedback < 3 (low_confidence = true) */
  quality_score: number | null;
  low_confidence: boolean;
}

export interface RecommendationEffectivenessOut {
  workspace_id: string;
  period_days: number;
  generated_at: string;
  by_type: RecommendationQualityItem[];
  /** null when all types are low_confidence */
  overall_quality_score: number | null;
}

// ── Sprint 22A — Recommendation Health Analytics ──────────────────────────────

export interface RecEffectivenessSummary {
  recommendations_generated: number;
  recommendations_acted: number;
  recommendations_successful: number;
  adoption_rate: number;   // 0.0–1.0
  success_rate: number;    // 0.0–1.0
}

export interface RecEffectivenessTypeItem {
  recommendation_type: string;
  generated: number;
  acted: number;
  successful: number;
  adoption_rate: number;
  success_rate: number;
  /** null when low_confidence (total_feedback < 3) */
  quality_score: number | null;
}

export interface QualityTrendPoint {
  score_date: string;
  rec_type: string;
  quality_score: number | null;
  adoption_rate: number;
  success_rate: number;
}

export interface RecEffectivenessOut {
  generated_at: string;
  summary: RecEffectivenessSummary;
  by_type: RecEffectivenessTypeItem[];
  /** All quality score rows in the period, ordered date asc — for the trend chart. */
  quality_trend: QualityTrendPoint[];
}

export interface RecCalibrationOverall {
  high_confidence_success_rate: number | null;
  medium_confidence_success_rate: number | null;
  low_confidence_success_rate: number | null;
}

export interface RecCalibrationTypeItem {
  recommendation_type: string;
  predicted_confidence: number;
  /** null when no acted outcomes exist for this type yet */
  observed_success_rate: number | null;
  /** observed − predicted; negative = overconfident; null when no outcomes */
  calibration_delta: number | null;
}

export interface RecCalibrationOut {
  generated_at: string;
  overall: RecCalibrationOverall;
  recommendation_types: RecCalibrationTypeItem[];
  insufficient_data: boolean;
  minimum_acted_recommendations: number;
}

// ── Sprint 22B — Recommendation Quality Review ────────────────────────────────

export interface RecBestWorstPerformer {
  recommendation_type: string;
  quality_score: number;
}

export interface RecIgnoredType {
  recommendation_type: string;
  /** ignored_count / shown_count (0.0–1.0) */
  ignored_rate: number;
}

export interface RecAdoptedType {
  recommendation_type: string;
  adoption_rate: number;
}

export interface RecSuccessfulType {
  recommendation_type: string;
  success_rate: number;
}

export interface RecCalibrationGroupItem {
  recommendation_type: string;
  calibration_delta: number;
}

export interface RecCalibrationGroupSummary {
  overconfident: RecCalibrationGroupItem[];
  underconfident: RecCalibrationGroupItem[];
  well_calibrated: RecCalibrationGroupItem[];
}

export interface RecReviewTrendPoint {
  date: string;
  /** Average quality_score across all rec_types for the day */
  quality_score: number;
}

export interface RecReviewOut {
  generated_at: string;
  best_performing_type: RecBestWorstPerformer | null;
  worst_performing_type: RecBestWorstPerformer | null;
  most_ignored_type: RecIgnoredType | null;
  most_adopted_type: RecAdoptedType | null;
  most_successful_type: RecSuccessfulType | null;
  calibration_summary: RecCalibrationGroupSummary;
  quality_trend: RecReviewTrendPoint[];
  insufficient_data: boolean;
}

// ── Sprint 23A — Calibration Analysis ────────────────────────────────────────

export interface ConfidenceDistribution {
  /** Count of recommendation_snapshots with confidence_level = "high" */
  high: number;
  medium: number;
  low: number;
}

export interface CalibrationAccuracy {
  /** abs(delta) < 5 */
  well_calibrated_count: number;
  /** delta <= -5 */
  overconfident_count: number;
  /** delta >= +5 */
  underconfident_count: number;
}

export interface CalibrationReviewTypeItem {
  recommendation_type: string;
  predicted_confidence: number;
  /** null when no acted outcomes exist for this type yet */
  observed_success_rate: number | null;
  /** observed − predicted; null when no outcomes */
  calibration_delta: number | null;
  /** "calibrated" | "warning" | "severe" | null (null when delta is null) */
  calibration_severity: string | null;
}

export interface CalibrationReviewOut {
  generated_at: string;
  /** Per-band success rates — reuses RecCalibrationOverall from Sprint 22A */
  overall: RecCalibrationOverall;
  confidence_distribution: ConfidenceDistribution;
  accuracy: CalibrationAccuracy;
  recommendation_types: CalibrationReviewTypeItem[];
  insufficient_data: boolean;
}

export interface QualityScoreStability {
  average: number;
  std_dev: number;
  /** "stable" | "volatile" | "unstable" */
  stability_rating: string;
}

export interface StabilityTypeItem {
  recommendation_type: string;
  average_quality_score: number;
  std_dev: number;
  /** "stable" | "volatile" | "unstable" */
  stability_rating: string;
}

export interface StabilityOut {
  generated_at: string;
  quality_score_stability: QualityScoreStability;
  /** Per-type stability items, sorted alphabetically */
  recommendation_types: StabilityTypeItem[];
  insufficient_data: boolean;
}

// ── Sprint 23B — Confidence Drift & Recommendation Reliability ───────────────

export interface MetricTrend {
  /** Average value in the current period (0–100 scale). */
  current: number;
  /** Average value in the prior period (0–100 scale). */
  previous: number;
  /** current − previous; positive = improvement. */
  change: number;
  /** "improving" (change > 5) | "stable" | "declining" (change < −5). */
  direction: string;
}

export interface DriftOverall {
  quality_score: MetricTrend;
  /** adoption_rate converted to percentage (fraction × 100). */
  adoption_rate: MetricTrend;
  /** success_rate converted to percentage (fraction × 100). */
  success_rate: MetricTrend;
}

export interface DriftTypeItem {
  recommendation_type: string;
  quality_score: MetricTrend;
}

export interface DriftOut {
  generated_at: string;
  overall: DriftOverall;
  by_type: DriftTypeItem[];
  /** True when previous window has no data (< 60 days of history). */
  insufficient_data: boolean;
}

export interface ReliabilityOverall {
  /** Weighted composite 0–100: success_rate×50 + adoption_rate×30 + quality_score×20. */
  score: number;
  /** "high" (≥ 75) | "medium" (50–74) | "low" (< 50). */
  rating: string;
}

export interface ReliabilityTypeItem {
  recommendation_type: string;
  reliability_score: number;
  rating: string;
}

export interface ReliabilityOut {
  generated_at: string;
  overall_reliability: ReliabilityOverall;
  /** Per-type scores sorted alphabetically. */
  recommendation_types: ReliabilityTypeItem[];
  insufficient_data: boolean;
}

// ── Sprint 24A — Recommendation Lifecycle Observatory ────────────────────────

export interface LifecycleTypeItem {
  recommendation_type: string;
  /** Mean days between snapshot.generated_at and acted_at (acted=true rows only). */
  avg_days_to_action: number;
  /** Mean days between snapshot.generated_at and success_measured_at (success=true rows). */
  avg_days_to_success: number;
  /** acted count / total * 100. */
  acted_rate: number;
  /** success=true count / total * 100. */
  success_rate: number;
}

export interface LifecycleOverall {
  avg_days_to_action: number;
  avg_days_to_success: number;
  acted_rate: number;
  success_rate: number;
}

export interface LifecycleOut {
  generated_at: string;
  overall: LifecycleOverall;
  /** Per-type stats sorted alphabetically by rec_type. */
  recommendation_types: LifecycleTypeItem[];
  insufficient_data: boolean;
}

export interface DecayBucket {
  /** "0-7" | "8-30" | "31-60" | "60+" */
  age_bucket: string;
  /** acted count / sample_size * 100 (0.0 when sample_size === 0). */
  acted_rate: number;
  /** success count / sample_size * 100 (0.0 when sample_size === 0). */
  success_rate: number;
  sample_size: number;
}

export interface DecayTypeItem {
  recommendation_type: string;
  /** Age bucket with highest success_rate among non-empty buckets. */
  best_bucket: string;
  /** Age bucket with lowest success_rate among non-empty buckets. */
  worst_bucket: string;
  /** True when best_success_rate − worst_success_rate ≥ 10 points. */
  decay_detected: boolean;
}

export interface DecayOut {
  generated_at: string;
  /** All 4 age brackets in canonical order (0-7, 8-30, 31-60, 60+). */
  buckets: DecayBucket[];
  /** Types with outcomes in ≥ 2 non-empty buckets; sorted alphabetically. */
  recommendation_types: DecayTypeItem[];
}

// ── Sprint 24B — Recommendation Portfolio & Coverage ─────────────────────────

export interface PortfolioTypeItem {
  recommendation_type: string;
  count: number;
  /** count / total_recommendations * 100. */
  percentage: number;
  /** acted outcomes / total outcomes for the type * 100; 0 when no outcomes. */
  acted_rate: number;
  /** success outcomes / total outcomes for the type * 100; 0 when no outcomes. */
  success_rate: number;
}

export interface PortfolioBalance {
  /** Normalized Shannon entropy H / ln(n_types) * 100 (0–100). */
  diversity_index: number;
  /** "excellent" (80–100) | "good" (60–79) | "moderate" (40–59) | "poor" (<40). */
  balance_rating: string;
}

export interface PortfolioOut {
  generated_at: string;
  total_recommendations: number;
  /** Per-type distribution sorted by count DESC. */
  recommendation_types: PortfolioTypeItem[];
  /** Type with the highest snapshot count; null when no data. */
  dominant_type: string | null;
  /** Type with the lowest snapshot count; null when no data. */
  least_used_type: string | null;
  portfolio_balance: PortfolioBalance;
  insufficient_data: boolean;
}

export interface CoverageItem {
  recommendation_type: string;
  /** True when at least one snapshot exists (all time). */
  present: boolean;
  /** Snapshot count in the analysis period. */
  count: number;
  /** Most recent snapshot_date (ISO date "YYYY-MM-DD"); null when not present. */
  last_generated_at: string | null;
  /** today − last_generated_at in days; null when not present. */
  days_since_last_generated: number | null;
}

export interface CoverageOut {
  generated_at: string;
  /** One row per known recommendation type, sorted alphabetically. */
  coverage: CoverageItem[];
  /** Types with no snapshots ever. */
  missing_types: string[];
  /** Types where days_since_last_generated > 30. */
  stale_types: string[];
}

// ── Sprint 25A — Recommendation Evidence Explorer ────────────────────────────

export interface EvidenceMetric {
  name: string;
  value: number | null;
  source: string;
}

export interface EvidenceSummary {
  generated_count: number;
  portfolio_percentage: number;
  confidence_average: number | null;
  quality_score: number | null;
  acted_rate: number;
  success_rate: number;
  reliability_score: number | null;
  reliability_rating: string | null;
  avg_days_to_action: number;
  avg_days_to_success: number;
  drift_direction: string | null;
  stability_rating: string | null;
  calibration_status: string | null;
  coverage_status: string;
  last_generated_at: string | null;
  days_since_last_generated: number | null;
}

export interface EvidenceOut {
  generated_at: string;
  recommendation_type: string;
  summary: EvidenceSummary;
  supporting_metrics: EvidenceMetric[];
  insufficient_data: boolean;
}

// ── Sprint 25B — Recommendation Action Center ────────────────────────────────

export interface RecommendationAction {
  id: string;
  recommendation_id: string;
  action_type: string;
  status: string;
  reason: string | null;
  snooze_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecommendationActionsListOut {
  accepted: RecommendationAction[];
  dismissed: RecommendationAction[];
  snoozed: RecommendationAction[];
  completed: RecommendationAction[];
  expired: RecommendationAction[];
  total: number;
}

export interface AcceptOut {
  status: string;
  accepted_at: string;
  recommendation_id: string;
}

// Sprint 26A — Recommendation Work Queue

export interface ExecutionOut {
  recommendation_id: string;
  action_type: string;
  execution_status: string | null;
  started_at: string | null;
  completed_at: string | null;
  blocked_at: string | null;
  cancelled_at: string | null;
  blocked_reason: string | null;
  completion_notes: string | null;
}

export interface WorkQueueGroupItem {
  recommendation_id: string;
  title: string;
  action_type: string;
  execution_status: string | null;
  started_at: string | null;
  completed_at: string | null;
  blocked_at: string | null;
  cancelled_at: string | null;
  blocked_reason: string | null;
  completion_notes: string | null;
  accepted_at: string;
}

export interface WorkQueueOut {
  ready: WorkQueueGroupItem[];
  in_progress: WorkQueueGroupItem[];
  blocked: WorkQueueGroupItem[];
  completed: WorkQueueGroupItem[];
  cancelled: WorkQueueGroupItem[];
  timeline: WorkQueueGroupItem[];
  total: number;
}

// ── Sprint 26B — Recommendation Outcome Tracking ─────────────────────────────

export interface ExecutionSummaryOut {
  accepted: number;
  started: number;
  completed: number;
  blocked: number;
  cancelled: number;
  completion_rate: number;
  cancellation_rate: number;
  block_rate: number;
  avg_days_to_start: number;
  avg_days_to_complete: number;
  avg_days_blocked: number;
  avg_days_cancelled: number;
  work_in_progress: number;
  overdue: number;
  insufficient_data: boolean;
}

export interface OutcomeTypeItemOut {
  rec_type: string;
  accepted: number;
  completed: number;
  cancelled: number;
  blocked: number;
  completion_rate: number;
  avg_days_to_complete: number;
  avg_days_to_start: number;
}

export interface RecommendationOutcomesOut {
  completed: number;
  blocked: number;
  cancelled: number;
  in_progress: number;
  ready: number;
  by_rec_type: OutcomeTypeItemOut[];
  insufficient_data: boolean;
}

// ── Sprint 27 — Recommendation Learning & Versioning ─────────────────────────

export interface LearningVersionOut {
  version: string;           // ISO date: "2026-06-15"
  first_seen: string;
  last_seen: string;
  recommendations_generated: number;
  acted: number;
  completed: number;
  successful: number;
  avg_confidence: number;
  quality_score: number | null;
}

export interface LearningComparisonOut {
  quality_delta: number | null;
  success_delta: number | null;
  confidence_delta: number | null;
  adoption_delta: number | null;
  execution_delta: number | null;
}

export interface LearningSummaryOut {
  lines: string[];
}

export interface VersionHistoryOut {
  versions: LearningVersionOut[];
  total_versions: number;
  insufficient_data: boolean;
}

export interface LearningOut {
  generated_at: string;
  current_version: string | null;
  previous_version: string | null;
  comparison: LearningComparisonOut | null;
  summary: LearningSummaryOut;
  insufficient_data: boolean;
}
