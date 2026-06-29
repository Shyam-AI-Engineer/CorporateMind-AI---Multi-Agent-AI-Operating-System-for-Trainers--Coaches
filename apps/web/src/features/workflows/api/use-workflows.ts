"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  BlockStepIn,
  CompleteStepIn,
  ReorderStepsIn,
  SkipStepIn,
  WorkflowRunIn,
  WorkflowRunListPage,
  WorkflowRunOut,
  WorkflowRunStepOut,
  WorkflowStepIn,
  WorkflowStepOut,
  WorkflowStepUpdate,
  WorkflowTemplateIn,
  WorkflowTemplateListPage,
  WorkflowTemplateOut,
  WorkflowTemplateUpdate,
} from "@/features/workflows/types";

const TEMPLATES_STALE_MS = 5 * 60 * 1000; // 300s — matches backend list/detail cache TTL

// ── Query key factories ───────────────────────────────────────────────────────

const TEMPLATE_LIST_KEY = (
  workspaceId: string,
  cursor?: string,
  filters?: Record<string, string | boolean | undefined>,
) => ["workflow-templates", "list", workspaceId, cursor ?? "first", filters ?? {}] as const;

const TEMPLATE_DETAIL_KEY = (templateId: string) =>
  ["workflow-templates", "detail", templateId] as const;

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useWorkflowTemplates(
  workspaceId: string | null | undefined,
  options?: {
    cursor?: string;
    category?: string;
    is_active?: boolean;
  },
) {
  const { cursor, category, is_active } = options ?? {};
  return useQuery({
    queryKey: TEMPLATE_LIST_KEY(workspaceId ?? "", cursor, { category, is_active: is_active?.toString() }),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      if (category) params.set("category", category);
      if (is_active !== undefined) params.set("is_active", String(is_active));
      return api.get<WorkflowTemplateListPage>(`/api/v1/workflow-templates?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: TEMPLATES_STALE_MS,
  });
}

export function useWorkflowTemplate(templateId: string | null | undefined) {
  return useQuery({
    queryKey: TEMPLATE_DETAIL_KEY(templateId ?? ""),
    queryFn: () =>
      api.get<WorkflowTemplateOut>(`/api/v1/workflow-templates/${templateId}`),
    enabled: !!templateId,
    staleTime: TEMPLATES_STALE_MS,
  });
}

// ── Mutation hooks ────────────────────────────────────────────────────────────

export function useCreateTemplate(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: WorkflowTemplateIn) =>
      api.post<WorkflowTemplateOut>("/api/v1/workflow-templates", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
    },
  });
}

export function useUpdateTemplate(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: WorkflowTemplateUpdate }) =>
      api.patch<WorkflowTemplateOut>(`/api/v1/workflow-templates/${id}`, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: TEMPLATE_DETAIL_KEY(id) });
    },
  });
}

export function useDeleteTemplate(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (templateId: string) =>
      api.delete<void>(`/api/v1/workflow-templates/${templateId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
    },
  });
}

export function useDuplicateTemplate(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (templateId: string) =>
      api.post<WorkflowTemplateOut>(
        `/api/v1/workflow-templates/${templateId}/duplicate?workspace_id=${workspaceId}`,
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
    },
  });
}

export function useAddStep(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: WorkflowStepIn }) =>
      api.post<WorkflowStepOut>(
        `/api/v1/workflow-templates/${templateId}/steps`,
        data,
      ),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: TEMPLATE_DETAIL_KEY(result.workflow_template_id) });
    },
  });
}

export function useUpdateStep(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, data, templateId }: { stepId: string; data: WorkflowStepUpdate; templateId: string }) =>
      api.patch<WorkflowStepOut>(`/api/v1/workflow-steps/${stepId}`, data),
    onSuccess: (_, { templateId }) => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: TEMPLATE_DETAIL_KEY(templateId) });
    },
  });
}

export function useDeleteStep(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, templateId }: { stepId: string; templateId: string }) =>
      api.delete<void>(`/api/v1/workflow-steps/${stepId}`),
    onSuccess: (_, { templateId }) => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: TEMPLATE_DETAIL_KEY(templateId) });
    },
  });
}

export function useReorderSteps(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReorderStepsIn }) =>
      api.post<WorkflowTemplateOut>(
        `/api/v1/workflow-templates/${templateId}/reorder`,
        data,
      ),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["workflow-templates", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: TEMPLATE_DETAIL_KEY(result.id) });
    },
  });
}

// ── Execution Engine hooks — Sprint 34 ───────────────────────────────────────

const RUNS_STALE_MS = 5 * 60 * 1000; // 300s — matches backend cache TTL

const RUN_LIST_KEY = (
  workspaceId: string,
  cursor?: string,
  statusFilter?: string,
) => ["workflow-runs", "list", workspaceId, cursor ?? "first", statusFilter ?? "all"] as const;

const RUN_DETAIL_KEY = (runId: string) =>
  ["workflow-runs", "detail", runId] as const;

export function useWorkflowRuns(
  workspaceId: string | null | undefined,
  options?: { cursor?: string; status_filter?: string },
) {
  const { cursor, status_filter } = options ?? {};
  return useQuery({
    queryKey: RUN_LIST_KEY(workspaceId ?? "", cursor, status_filter),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      if (status_filter) params.set("status_filter", status_filter);
      return api.get<WorkflowRunListPage>(`/api/v1/workflow-runs?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: RUNS_STALE_MS,
  });
}

export function useWorkflowRun(runId: string | null | undefined) {
  return useQuery({
    queryKey: RUN_DETAIL_KEY(runId ?? ""),
    queryFn: () => api.get<WorkflowRunOut>(`/api/v1/workflow-runs/${runId}`),
    enabled: !!runId,
    staleTime: RUNS_STALE_MS,
  });
}

export function useStartRun(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: WorkflowRunIn) =>
      api.post<WorkflowRunOut>("/api/v1/workflow-runs", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-runs", "list", workspaceId] });
    },
  });
}

export function useCancelRun(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<WorkflowRunOut>(`/api/v1/workflow-runs/${runId}/cancel`, {}),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["workflow-runs", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(result.id) });
    },
  });
}

export function useCompleteStep(workspaceId: string, runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, data }: { stepId: string; data: CompleteStepIn }) =>
      api.post<WorkflowRunStepOut>(`/api/v1/workflow-run-steps/${stepId}/complete`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(runId) });
      qc.invalidateQueries({ queryKey: ["workflow-runs", "list", workspaceId] });
    },
  });
}

export function useReopenStep(workspaceId: string, runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stepId: string) =>
      api.post<WorkflowRunStepOut>(`/api/v1/workflow-run-steps/${stepId}/reopen`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(runId) });
      qc.invalidateQueries({ queryKey: ["workflow-runs", "list", workspaceId] });
    },
  });
}

export function useSkipStep(workspaceId: string, runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, data }: { stepId: string; data: SkipStepIn }) =>
      api.post<WorkflowRunStepOut>(`/api/v1/workflow-run-steps/${stepId}/skip`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(runId) });
    },
  });
}

export function useBlockStep(workspaceId: string, runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, data }: { stepId: string; data: BlockStepIn }) =>
      api.post<WorkflowRunStepOut>(`/api/v1/workflow-run-steps/${stepId}/block`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(runId) });
    },
  });
}

export function useResumeStep(workspaceId: string, runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stepId: string) =>
      api.post<WorkflowRunStepOut>(`/api/v1/workflow-run-steps/${stepId}/resume`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: RUN_DETAIL_KEY(runId) });
    },
  });
}
