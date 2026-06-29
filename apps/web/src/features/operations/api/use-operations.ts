"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  BusinessTaskIn,
  BusinessTaskOut,
  BusinessTaskUpdate,
  GroupedTasksOut,
  WorkloadOut,
} from "@/features/operations/types";

const STALE_MS = 5 * 60 * 1000; // 5 minutes — matches backend Redis TTL

// ── Query key factories ───────────────────────────────────────────────────────

const TASKS_KEY = (workspaceId: string) =>
  ["operations", "tasks", workspaceId] as const;

const WORKLOAD_KEY = (workspaceId: string) =>
  ["operations", "workload", workspaceId] as const;

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useOperationsTasks(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: TASKS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<GroupedTasksOut>(
        `/api/v1/operations/tasks?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function useOperationsWorkload(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: WORKLOAD_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<WorkloadOut>(
        `/api/v1/operations/workload?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

// ── Mutation hooks ────────────────────────────────────────────────────────────

export function useCreateTask(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BusinessTaskIn) =>
      api.post<BusinessTaskOut>("/api/v1/operations/tasks", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(workspaceId) });
      qc.invalidateQueries({ queryKey: WORKLOAD_KEY(workspaceId) });
    },
  });
}

export function useUpdateTask(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      data,
    }: {
      taskId: string;
      data: BusinessTaskUpdate;
    }) =>
      api.patch<BusinessTaskOut>(
        `/api/v1/operations/tasks/${taskId}?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(workspaceId) });
      qc.invalidateQueries({ queryKey: WORKLOAD_KEY(workspaceId) });
    },
  });
}

export function useDeleteTask(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      api.delete(`/api/v1/operations/tasks/${taskId}?workspace_id=${workspaceId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(workspaceId) });
      qc.invalidateQueries({ queryKey: WORKLOAD_KEY(workspaceId) });
    },
  });
}
