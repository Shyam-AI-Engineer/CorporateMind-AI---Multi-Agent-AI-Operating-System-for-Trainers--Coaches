"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  SLAOverdueOut,
  SLAOwnerOut,
  SLASummaryOut,
  SLATemplateOut,
  SLATrendOut,
} from "@/features/workflows/types";

const SLA_STALE_MS = 15 * 60 * 1000; // 900s — matches backend TTL

// ── Query key factories ───────────────────────────────────────────────────────

const SLA_SUMMARY_KEY = (workspaceId: string) =>
  ["workflow-sla", "summary", workspaceId] as const;

const SLA_OVERDUE_KEY = (workspaceId: string) =>
  ["workflow-sla", "overdue", workspaceId] as const;

const SLA_TEMPLATES_KEY = (workspaceId: string) =>
  ["workflow-sla", "templates", workspaceId] as const;

const SLA_OWNER_KEY = (workspaceId: string) =>
  ["workflow-sla", "owner", workspaceId] as const;

const SLA_TREND_KEY = (workspaceId: string, period: number) =>
  ["workflow-sla", "trend", workspaceId, period] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useSLASummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SLA_SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SLASummaryOut>(
        `/api/v1/workflow-sla/summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: SLA_STALE_MS,
  });
}

export function useSLAOverdue(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SLA_OVERDUE_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SLAOverdueOut>(
        `/api/v1/workflow-sla/overdue?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: SLA_STALE_MS,
  });
}

export function useSLATemplates(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SLA_TEMPLATES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SLATemplateOut>(
        `/api/v1/workflow-sla/by-template?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: SLA_STALE_MS,
  });
}

export function useSLAOwner(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: SLA_OWNER_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SLAOwnerOut>(
        `/api/v1/workflow-sla/by-owner?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: SLA_STALE_MS,
  });
}

export function useSLATrend(
  workspaceId: string | null | undefined,
  period: number = 30,
) {
  return useQuery({
    queryKey: SLA_TREND_KEY(workspaceId ?? "", period),
    queryFn: () =>
      api.get<SLATrendOut>(
        `/api/v1/workflow-sla/trend?workspace_id=${workspaceId}&period=${period}`,
      ),
    enabled: !!workspaceId,
    staleTime: SLA_STALE_MS,
  });
}
