"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AnalyticsChannelSummary, AnalyticsFunnel, AnalyticsSummary, DailyRollup } from "@/features/analytics/types";

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
