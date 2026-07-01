"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CompletionImpactOut,
  DurationImpactOut,
  EffectivenessEntityOut,
  EffectivenessSummaryOut,
  EffectivenessTemplateOut,
} from "@/features/workflows/types";

const EFF_STALE_MS = 15 * 60 * 1000; // 900s — matches backend TTL

// ── Query key factories ───────────────────────────────────────────────────────

const EFF_SUMMARY_KEY = (workspaceId: string) =>
  ["workflow-effectiveness", "summary", workspaceId] as const;

const EFF_TEMPLATES_KEY = (workspaceId: string) =>
  ["workflow-effectiveness", "templates", workspaceId] as const;

const EFF_ENTITIES_KEY = (workspaceId: string) =>
  ["workflow-effectiveness", "entities", workspaceId] as const;

const EFF_DURATION_KEY = (workspaceId: string) =>
  ["workflow-effectiveness", "duration", workspaceId] as const;

const EFF_COMPLETION_KEY = (workspaceId: string) =>
  ["workflow-effectiveness", "completion", workspaceId] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useEffectivenessSummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EFF_SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<EffectivenessSummaryOut>(
        `/api/v1/workflow-effectiveness/summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: EFF_STALE_MS,
  });
}

export function useEffectivenessTemplates(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EFF_TEMPLATES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<EffectivenessTemplateOut>(
        `/api/v1/workflow-effectiveness/templates?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: EFF_STALE_MS,
  });
}

export function useEffectivenessEntities(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EFF_ENTITIES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<EffectivenessEntityOut>(
        `/api/v1/workflow-effectiveness/entity-types?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: EFF_STALE_MS,
  });
}

export function useEffectivenessDuration(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EFF_DURATION_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<DurationImpactOut>(
        `/api/v1/workflow-effectiveness/duration-impact?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: EFF_STALE_MS,
  });
}

export function useEffectivenessCompletion(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: EFF_COMPLETION_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<CompletionImpactOut>(
        `/api/v1/workflow-effectiveness/completion-impact?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: EFF_STALE_MS,
  });
}
