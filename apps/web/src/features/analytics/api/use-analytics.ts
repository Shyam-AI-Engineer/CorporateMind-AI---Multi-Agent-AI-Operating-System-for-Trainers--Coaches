"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AcceptOut,
  AnalyticsChannelSummary,
  AnalyticsFunnel,
  AnalyticsInsightOut,
  AnalyticsSummary,
  CalibrationReviewOut,
  CampaignROIListOut,
  CoverageOut,
  DailyRollup,
  DecayOut,
  EvidenceOut,
  DriftOut,
  IndustryPerformanceOut,
  LearningOut,
  LifecycleOut,
  PortfolioOut,
  PricingCalibrationOut,
  RecCalibrationOut,
  RecEffectivenessOut,
  RecReviewOut,
  ExecutionOut,
  RecommendationAction,
  RecommendationActionsListOut,
  RecommendationFeedbackIn,
  RecommendationFeedbackOut,
  RecommendationsOut,
  ReliabilityOut,
  StabilityOut,
  TopicPerformanceOut,
  VersionHistoryOut,
  WorkQueueOut,
  ExecutionSummaryOut,
  RecommendationOutcomesOut,
} from "@/features/analytics/types";

export function useAnalyticsSummary(days = 30) {
  return useQuery({
    queryKey: ["analytics", "summary", days] as const,
    queryFn: () =>
      api.get<AnalyticsSummary>(`/api/v1/analytics/summary?days=${days}`),
    staleTime: 5 * 60 * 1000, // 5 min — rollups only update once a day
  });
}

export function useAnalyticsTrend(days = 30) {
  return useQuery({
    queryKey: ["analytics", "trend", days] as const,
    queryFn: () =>
      api.get<DailyRollup[]>(`/api/v1/analytics/trend?days=${days}`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAnalyticsFunnel(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ["analytics", "funnel", workspaceId] as const,
    queryFn: () =>
      api.get<AnalyticsFunnel>(
        `/api/v1/analytics/funnel?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 30 * 1000, // 30 s — live transactional data
  });
}

export function useWhatsAppAnalytics(days = 30) {
  return useQuery({
    queryKey: ["analytics", "channel", "whatsapp", days] as const,
    queryFn: () =>
      api.get<AnalyticsChannelSummary>(
        `/api/v1/analytics/channel/whatsapp?days=${days}`,
      ),
    staleTime: 5 * 60 * 1000, // 5 min — pre-computed rollup data
  });
}

// ── Sprint 19 — intelligence hooks ───────────────────────────────────────────

export function useCampaignROI(
  workspaceId: string | null | undefined,
  limit = 20,
  offset = 0,
) {
  return useQuery({
    queryKey: ["analytics", "campaigns", "roi", workspaceId, limit, offset] as const,
    queryFn: () =>
      api.get<CampaignROIListOut>(
        `/api/v1/analytics/campaigns/roi?workspace_id=${workspaceId}&limit=${limit}&offset=${offset}`,
      ),
    enabled: !!workspaceId,
    staleTime: 5 * 60 * 1000, // pre-computed; refreshes when Celery beat runs
  });
}

export function useTopicPerformance(
  workspaceId: string | null | undefined,
  limit = 15,
) {
  return useQuery({
    queryKey: ["analytics", "topics", workspaceId, limit] as const,
    queryFn: () =>
      api.get<TopicPerformanceOut>(
        `/api/v1/analytics/topics?workspace_id=${workspaceId}&limit=${limit}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useIndustryPerformance(
  workspaceId: string | null | undefined,
  limit = 15,
) {
  return useQuery({
    queryKey: ["analytics", "industries", workspaceId, limit] as const,
    queryFn: () =>
      api.get<IndustryPerformanceOut>(
        `/api/v1/analytics/industries?workspace_id=${workspaceId}&limit=${limit}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000,
  });
}

export function usePricingCalibration(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ["analytics", "pricing", workspaceId] as const,
    queryFn: () =>
      api.get<PricingCalibrationOut>(
        `/api/v1/analytics/pricing-calibration?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000,
  });
}

// ── Sprint 20A — recommendations hook ────────────────────────────────────────

export function useRecommendations(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ["analytics", "recommendations", workspaceId] as const,
    queryFn: () =>
      api.get<RecommendationsOut>(
        `/api/v1/analytics/recommendations?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 4 * 60 * 60 * 1000, // 4 h — matches backend Redis TTL
  });
}

// ── Sprint 20B — AI insights hook ────────────────────────────────────────────

export function useInsights(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ["analytics", "insights", workspaceId] as const,
    queryFn: () =>
      api.get<AnalyticsInsightOut>(
        `/api/v1/analytics/insights?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 4 * 60 * 60 * 1000, // 4 h — aligned with recommendations TTL
  });
}

// ── Sprint 21 — feedback mutation + effectiveness hook ────────────────────────

export function useSubmitFeedback(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation<RecommendationFeedbackOut, Error, RecommendationFeedbackIn>({
    mutationFn: (body) =>
      api.post<RecommendationFeedbackOut>(
        "/api/v1/analytics/recommendations/feedback",
        body,
      ),
    onSuccess: () => {
      // Invalidate effectiveness so the quality badge reflects new feedback
      queryClient.invalidateQueries({
        queryKey: ["analytics", "effectiveness", workspaceId],
      });
    },
  });
}

export function useRecommendationEffectiveness(
  workspaceId: string | null | undefined,
  periodDays = 30,
) {
  return useQuery({
    queryKey: ["analytics", "effectiveness", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<RecEffectivenessOut>(
        `/api/v1/analytics/recommendations/effectiveness?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useRecCalibration(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "calibration", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<RecCalibrationOut>(
        `/api/v1/analytics/recommendations/calibration?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 22B — recommendation review hook ───────────────────────────────────

export function useRecReview(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "review", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<RecReviewOut>(
        `/api/v1/analytics/recommendations/review?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 23A — calibration review + stability hooks ─────────────────────────

export function useCalibrationReview(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "calibration-review", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<CalibrationReviewOut>(
        `/api/v1/analytics/recommendations/calibration-review?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useStability(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "stability", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<StabilityOut>(
        `/api/v1/analytics/recommendations/stability?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000,
  });
}

// ── Sprint 23B — drift + reliability hooks ────────────────────────────────────

export function useDrift(
  workspaceId: string | null | undefined,
  periodDays = 30,
) {
  return useQuery({
    queryKey: ["analytics", "drift", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<DriftOut>(
        `/api/v1/analytics/recommendations/drift?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useReliability(
  workspaceId: string | null | undefined,
  periodDays = 30,
) {
  return useQuery({
    queryKey: ["analytics", "reliability", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<ReliabilityOut>(
        `/api/v1/analytics/recommendations/reliability?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 24A — lifecycle + decay hooks ─────────────────────────────────────

export function useLifecycle(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "lifecycle", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<LifecycleOut>(
        `/api/v1/analytics/recommendations/lifecycle?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useDecay(
  workspaceId: string | null | undefined,
  periodDays = 180,
) {
  return useQuery({
    queryKey: ["analytics", "decay", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<DecayOut>(
        `/api/v1/analytics/recommendations/decay?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 24B — portfolio + coverage hooks ───────────────────────────────────

export function usePortfolio(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "portfolio", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<PortfolioOut>(
        `/api/v1/analytics/recommendations/portfolio?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useCoverage(
  workspaceId: string | null | undefined,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "coverage", workspaceId, periodDays] as const,
    queryFn: () =>
      api.get<CoverageOut>(
        `/api/v1/analytics/recommendations/coverage?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 25A — Recommendation Evidence Explorer ────────────────────────────

export function useEvidence(
  workspaceId: string | null | undefined,
  recommendationType: string,
  periodDays = 90,
) {
  return useQuery({
    queryKey: ["analytics", "evidence", workspaceId, recommendationType, periodDays] as const,
    queryFn: () =>
      api.get<EvidenceOut>(
        `/api/v1/analytics/recommendations/evidence/${recommendationType}?workspace_id=${workspaceId}&period_days=${periodDays}`,
      ),
    enabled: !!workspaceId && !!recommendationType,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

// ── Sprint 25B — Recommendation Action Center ────────────────────────────────

const ACTIONS_KEY = (workspaceId: string) =>
  ["analytics", "recommendation-actions", workspaceId] as const;

export function useRecommendationActions(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ACTIONS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<RecommendationActionsListOut>(
        `/api/v1/analytics/recommendations/actions?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 5 * 60 * 1000, // 5 min — matches backend Redis TTL
  });
}

export function useAcceptRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (recommendationId: string) =>
      api.post<AcceptOut>(
        `/api/v1/analytics/recommendations/${recommendationId}/accept?workspace_id=${workspaceId}`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ACTIONS_KEY(workspaceId) }),
  });
}

export function useDismissRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, reason }: { recommendationId: string; reason?: string }) =>
      api.post<RecommendationAction>(
        `/api/v1/analytics/recommendations/${recommendationId}/dismiss?workspace_id=${workspaceId}`,
        { reason: reason ?? null },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ACTIONS_KEY(workspaceId) }),
  });
}

export function useSnoozeRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, until }: { recommendationId: string; until: string }) =>
      api.post<RecommendationAction>(
        `/api/v1/analytics/recommendations/${recommendationId}/snooze?workspace_id=${workspaceId}`,
        { until },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ACTIONS_KEY(workspaceId) }),
  });
}

// Sprint 26A — Recommendation Work Queue

const WORK_QUEUE_KEY = (workspaceId: string) =>
  ["analytics", "recommendation-work-queue", workspaceId] as const;

export function useRecommendationWorkQueue(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: WORK_QUEUE_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<WorkQueueOut>(
        `/api/v1/analytics/recommendations/work-queue?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useStartRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId }: { recommendationId: string }) =>
      api.post<ExecutionOut>(
        `/api/v1/analytics/recommendations/${recommendationId}/start?workspace_id=${workspaceId}`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORK_QUEUE_KEY(workspaceId) }),
  });
}

export function useBlockRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, reason }: { recommendationId: string; reason: string }) =>
      api.post<ExecutionOut>(
        `/api/v1/analytics/recommendations/${recommendationId}/block?workspace_id=${workspaceId}`,
        { reason },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORK_QUEUE_KEY(workspaceId) }),
  });
}

export function useCompleteRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, notes }: { recommendationId: string; notes?: string }) =>
      api.post<ExecutionOut>(
        `/api/v1/analytics/recommendations/${recommendationId}/complete?workspace_id=${workspaceId}`,
        { notes: notes ?? null },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORK_QUEUE_KEY(workspaceId) }),
  });
}

export function useCancelRecommendation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, reason }: { recommendationId: string; reason?: string }) =>
      api.post<ExecutionOut>(
        `/api/v1/analytics/recommendations/${recommendationId}/cancel?workspace_id=${workspaceId}`,
        { reason: reason ?? null },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORK_QUEUE_KEY(workspaceId) }),
  });
}

// ── Sprint 26B — Recommendation Outcome Tracking ─────────────────────────────

const EXECUTION_SUMMARY_KEY = (workspaceId: string) =>
  ["analytics", "execution-summary", workspaceId] as const;

const OUTCOMES_KEY = (workspaceId: string) =>
  ["analytics", "recommendation-outcomes", workspaceId] as const;

export function useExecutionSummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EXECUTION_SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<ExecutionSummaryOut>(
        `/api/v1/analytics/recommendations/execution-summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecommendationOutcomes(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OUTCOMES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<RecommendationOutcomesOut>(
        `/api/v1/analytics/recommendations/outcomes?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 5 * 60 * 1000,
  });
}

// ── Sprint 27 — Recommendation Learning & Versioning ─────────────────────────

const LEARNING_KEY = (workspaceId: string) =>
  ["analytics", "recommendation-learning", workspaceId] as const;

const VERSION_HISTORY_KEY = (workspaceId: string) =>
  ["analytics", "recommendation-version-history", workspaceId] as const;

export function useRecommendationLearning(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: LEARNING_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<LearningOut>(
        `/api/v1/analytics/recommendations/learning?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}

export function useRecommendationVersionHistory(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: VERSION_HISTORY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<VersionHistoryOut>(
        `/api/v1/analytics/recommendations/version-history?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: 60 * 60 * 1000, // 1 h — matches backend Redis TTL
  });
}
