"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CancelEngagement,
  CompleteEngagement,
  CoordinatorAssign,
  TrainerAssign,
  TrainingEngagement,
  TrainingEngagementCreate,
  TrainingEngagementFilters,
  TrainingEngagementListOut,
  TrainingEngagementUpdate,
} from "@/features/training/types";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<TrainingEngagementFilters>) =>
  ["training", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["training", "detail", id] as const;

function useInvalidateTraining(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (engagementId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["training", "list", workspaceId] });
    }
    if (engagementId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(engagementId) });
  };
}

export function useTrainingEngagements(filters: TrainingEngagementFilters | null | undefined) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: TrainingEngagementListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.status) params.set("status", filters.status);
      if (filters?.trainer_id) params.set("trainer_id", filters.trainer_id);
      if (filters?.customer_id) params.set("customer_id", filters.customer_id);
      if (filters?.delivery_mode) params.set("delivery_mode", filters.delivery_mode);
      if (filters?.date_from) params.set("date_from", filters.date_from);
      if (filters?.date_to) params.set("date_to", filters.date_to);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingEngagementListOut }>(
        `/api/v1/training-engagements?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useTrainingEngagement(engagementId: string | null | undefined) {
  return useQuery<{ data: TrainingEngagement }>({
    queryKey: DETAIL_KEY(engagementId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${engagementId}`
      ),
    staleTime: STALE_MS,
    enabled: !!engagementId,
  });
}

export function useCreateTrainingEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<{ data: TrainingEngagement }, Error, TrainingEngagementCreate>({
    mutationFn: (body) =>
      api.post<{ data: TrainingEngagement }>("/api/v1/training-engagements/", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateTrainingEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: TrainingEngagementUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useStartEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<{ data: TrainingEngagement }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/start`,
        {}
      ),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useCompleteEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CompleteEngagement }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/complete`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useCancelEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CancelEngagement }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/cancel`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useAssignTrainer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: TrainerAssign }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/assign-trainer`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useAssignCoordinator(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CoordinatorAssign }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/assign-coordinator`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}
