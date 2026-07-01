"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AnalyticsSummaryOut,
  BottleneckAnalyticsOut,
  TemplateAnalyticsOut,
  TrendAnalyticsOut,
  WorkloadAnalyticsOut,
} from "@/features/workflows/types";

const ANALYTICS_STALE_MS = 15 * 60 * 1000; // 900s — matches backend TTL

// ── Query key factories ───────────────────────────────────────────────────────

const SUMMARY_KEY = (workspaceId: string) =>
  ["workflow-analytics", "summary", workspaceId] as const;

const TEMPLATES_KEY = (workspaceId: string) =>
  ["workflow-analytics", "templates", workspaceId] as const;

const BOTTLENECKS_KEY = (workspaceId: string) =>
  ["workflow-analytics", "bottlenecks", workspaceId] as const;

const TRENDS_KEY = (workspaceId: string, period: number) =>
  ["workflow-analytics", "trends", workspaceId, period] as const;

const WORKLOAD_KEY = (workspaceId: string) =>
  ["workflow-analytics", "workload", workspaceId] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useAnalyticsSummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<AnalyticsSummaryOut>(
        `/api/v1/workflow-analytics/summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useAnalyticsTemplates(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: TEMPLATES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<TemplateAnalyticsOut>(
        `/api/v1/workflow-analytics/templates?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useAnalyticsBottlenecks(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: BOTTLENECKS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<BottleneckAnalyticsOut>(
        `/api/v1/workflow-analytics/bottlenecks?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useAnalyticsTrends(
  workspaceId: string | null | undefined,
  period: number = 30,
) {
  return useQuery({
    queryKey: TRENDS_KEY(workspaceId ?? "", period),
    queryFn: () =>
      api.get<TrendAnalyticsOut>(
        `/api/v1/workflow-analytics/trends?workspace_id=${workspaceId}&period=${period}`,
      ),
    enabled: !!workspaceId,
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useAnalyticsWorkload(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: WORKLOAD_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<WorkloadAnalyticsOut>(
        `/api/v1/workflow-analytics/workload?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: ANALYTICS_STALE_MS,
  });
}
