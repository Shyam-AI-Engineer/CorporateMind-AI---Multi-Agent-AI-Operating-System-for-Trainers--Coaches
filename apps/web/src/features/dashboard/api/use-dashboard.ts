"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  BusinessHealthOut,
  BusinessSummaryOut,
  OperationalAlertsOut,
} from "@/features/dashboard/types";

// Cache keys — workspace-scoped to match backend Redis TTL (15 min)
const HEALTH_KEY = (workspaceId: string) =>
  ["dashboard", "business-health", workspaceId] as const;
const ALERTS_KEY = (workspaceId: string) =>
  ["dashboard", "operational-alerts", workspaceId] as const;
const SUMMARY_KEY = (workspaceId: string) =>
  ["dashboard", "business-summary", workspaceId] as const;

const STALE_MS = 15 * 60 * 1000; // 15 minutes — matches backend TTL

export function useBusinessHealth(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: HEALTH_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<BusinessHealthOut>(
        `/api/v1/dashboard/business-health?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function useOperationalAlerts(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ALERTS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<OperationalAlertsOut>(
        `/api/v1/dashboard/operational-alerts?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function useBusinessSummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<BusinessSummaryOut>(
        `/api/v1/dashboard/business-summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}
