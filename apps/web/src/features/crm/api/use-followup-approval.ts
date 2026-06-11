"use client";

/**
 * TanStack Query hooks for the Sprint 8C follow-up HITL approval surface.
 *
 * Lives in the existing CRM feature folder alongside use-activities.ts.
 * All mutations invalidate the follow-up list (so rows move between tabs) and
 * the activity timeline (approve/reject write activity rows), plus the per-task
 * review query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  FollowupApproveResponse,
  FollowupDraftView,
  FollowupReview,
  FollowUpTask,
} from "@/features/crm/types";

const REVIEW_KEY = (taskId: string) => ["crm", "followup-review", taskId] as const;

export function useFollowupReview(taskId: string | null) {
  return useQuery({
    queryKey: REVIEW_KEY(taskId ?? ""),
    queryFn: () =>
      api.get<FollowupReview>(`/api/v1/crm/follow-ups/${taskId}/review`),
    enabled: !!taskId,
    staleTime: 10 * 1000,
  });
}

function useInvalidateApproval() {
  const qc = useQueryClient();
  return (taskId?: string) => {
    // Prefix match invalidates every follow-up list query regardless of params.
    void qc.invalidateQueries({ queryKey: ["crm", "follow-ups"] });
    void qc.invalidateQueries({ queryKey: ["crm", "activities"] });
    if (taskId) void qc.invalidateQueries({ queryKey: REVIEW_KEY(taskId) });
  };
}

export function useApproveFollowup() {
  const invalidate = useInvalidateApproval();
  return useMutation({
    mutationFn: (taskId: string) =>
      api.post<FollowupApproveResponse>(
        `/api/v1/crm/follow-ups/${taskId}/approve`,
        {}
      ),
    onSuccess: (_res, taskId) => invalidate(taskId),
  });
}

export function useRejectFollowup() {
  const invalidate = useInvalidateApproval();
  return useMutation({
    mutationFn: (vars: { taskId: string; reason?: string }) =>
      api.post<FollowUpTask>(`/api/v1/crm/follow-ups/${vars.taskId}/reject`, {
        reason: vars.reason ?? null,
      }),
    onSuccess: (_res, vars) => invalidate(vars.taskId),
  });
}

export function useEditFollowupDraft() {
  const invalidate = useInvalidateApproval();
  return useMutation({
    mutationFn: (vars: {
      taskId: string;
      subject: string | null;
      body: string;
    }) =>
      api.patch<FollowupDraftView>(
        `/api/v1/crm/follow-ups/${vars.taskId}/draft`,
        { subject: vars.subject, body: vars.body }
      ),
    onSuccess: (_res, vars) => invalidate(vars.taskId),
  });
}
