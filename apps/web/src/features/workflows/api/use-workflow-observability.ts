"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  BottleneckObsOut,
  FlowHealthOut,
  OwnerCapacityOut,
  StepAnalysisOut,
  TemplateCapacityOut,
} from "@/features/workflows/types";

const OBS_STALE_MS = 15 * 60 * 1000; // 900s — matches backend TTL

// ── Query key factories ───────────────────────────────────────────────────────

const OBS_BOTTLENECKS_KEY = (workspaceId: string) =>
  ["workflow-observability", "bottlenecks", workspaceId] as const;

const OBS_STEPS_KEY = (workspaceId: string) =>
  ["workflow-observability", "step-analysis", workspaceId] as const;

const OBS_OWNER_KEY = (workspaceId: string) =>
  ["workflow-observability", "owner-capacity", workspaceId] as const;

const OBS_TEMPLATES_KEY = (workspaceId: string) =>
  ["workflow-observability", "template-capacity", workspaceId] as const;

const OBS_FLOW_HEALTH_KEY = (workspaceId: string) =>
  ["workflow-observability", "flow-health", workspaceId] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useObsBottlenecks(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OBS_BOTTLENECKS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<BottleneckObsOut>(
        `/api/v1/workflow-observability/bottlenecks?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: OBS_STALE_MS,
  });
}

export function useObsStepAnalysis(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OBS_STEPS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<StepAnalysisOut>(
        `/api/v1/workflow-observability/step-analysis?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: OBS_STALE_MS,
  });
}

export function useObsOwnerCapacity(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OBS_OWNER_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<OwnerCapacityOut>(
        `/api/v1/workflow-observability/owner-capacity?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: OBS_STALE_MS,
  });
}

export function useObsTemplateCapacity(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OBS_TEMPLATES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<TemplateCapacityOut>(
        `/api/v1/workflow-observability/template-capacity?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: OBS_STALE_MS,
  });
}

export function useObsFlowHealth(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: OBS_FLOW_HEALTH_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<FlowHealthOut>(
        `/api/v1/workflow-observability/flow-health?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: OBS_STALE_MS,
  });
}
