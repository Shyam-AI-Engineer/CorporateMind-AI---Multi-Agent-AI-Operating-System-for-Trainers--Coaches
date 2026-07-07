"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ExecutiveAlert,
  ExecutiveDashboard,
  ExecutiveKPIs,
  ExecutiveTrend,
  TrendPeriod,
} from "@/features/executive/types-executive";

const STALE_MS = 900_000; // match backend TTL

const DASHBOARD_KEY = (workspaceId: string) =>
  ["executive-dashboard", workspaceId] as const;

const KPIS_KEY = (workspaceId: string) =>
  ["executive-kpis", workspaceId] as const;

const ALERTS_KEY = (workspaceId: string) =>
  ["executive-alerts", workspaceId] as const;

const TRENDS_KEY = (workspaceId: string, days: TrendPeriod) =>
  ["executive-trends", workspaceId, days] as const;

export function useExecutiveDashboard(
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: ExecutiveDashboard }>({
    queryKey: DASHBOARD_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<{ data: ExecutiveDashboard }>(
        `/api/v1/executive-dashboard?workspace_id=${workspaceId}`
      ),
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useExecutiveKPIs(workspaceId: string | null | undefined) {
  return useQuery<{ data: ExecutiveKPIs }>({
    queryKey: KPIS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<{ data: ExecutiveKPIs }>(
        `/api/v1/executive-dashboard/kpis?workspace_id=${workspaceId}`
      ),
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useExecutiveAlerts(workspaceId: string | null | undefined) {
  return useQuery<{ data: ExecutiveAlert[] }>({
    queryKey: ALERTS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<{ data: ExecutiveAlert[] }>(
        `/api/v1/executive-dashboard/alerts?workspace_id=${workspaceId}`
      ),
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useExecutiveTrends(
  workspaceId: string | null | undefined,
  days: TrendPeriod = 30
) {
  return useQuery<{ data: ExecutiveTrend[] }>({
    queryKey: TRENDS_KEY(workspaceId ?? "", days),
    queryFn: () =>
      api.get<{ data: ExecutiveTrend[] }>(
        `/api/v1/executive-dashboard/trends?workspace_id=${workspaceId}&days=${days}`
      ),
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}
