"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ApprovalAssignIn,
  ApprovalDecisionIn,
  ApprovalListPage,
  ApprovalRequestIn,
  ApprovalRequestOut,
  ApprovalTimelineEventOut,
} from "@/features/approvals/types";

const APPROVALS_STALE_MS = 5 * 60 * 1000; // 300s — matches backend Redis TTL

// ── Query key factories ───────────────────────────────────────────────────────

const APPROVAL_LIST_KEY = (workspaceId: string, cursor?: string, filters?: Record<string, string | undefined>) =>
  ["approvals", "list", workspaceId, cursor ?? "first", filters ?? {}] as const;

const APPROVAL_MY_REVIEWS_KEY = (workspaceId: string, cursor?: string) =>
  ["approvals", "my-reviews", workspaceId, cursor ?? "first"] as const;

const APPROVAL_DETAIL_KEY = (approvalId: string) =>
  ["approvals", "detail", approvalId] as const;

const APPROVAL_TIMELINE_KEY = (approvalId: string) =>
  ["approvals", "timeline", approvalId] as const;

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useApprovals(
  workspaceId: string | null | undefined,
  options?: {
    cursor?: string;
    status?: string;
    priority?: string;
    assigned_reviewer?: string;
  },
) {
  const { cursor, status, priority, assigned_reviewer } = options ?? {};
  return useQuery({
    queryKey: APPROVAL_LIST_KEY(workspaceId ?? "", cursor, { status, priority, assigned_reviewer }),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      if (status) params.set("status", status);
      if (priority) params.set("priority", priority);
      if (assigned_reviewer) params.set("assigned_reviewer", assigned_reviewer);
      return api.get<ApprovalListPage>(`/api/v1/approvals?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: APPROVALS_STALE_MS,
  });
}

export function useMyReviewApprovals(
  workspaceId: string | null | undefined,
  cursor?: string,
) {
  return useQuery({
    queryKey: APPROVAL_MY_REVIEWS_KEY(workspaceId ?? "", cursor),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      return api.get<ApprovalListPage>(`/api/v1/approvals/my-reviews?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: APPROVALS_STALE_MS,
  });
}

export function useApprovalDetail(
  approvalId: string | null | undefined,
  workspaceId: string | null | undefined,
) {
  return useQuery({
    queryKey: APPROVAL_DETAIL_KEY(approvalId ?? ""),
    queryFn: () =>
      api.get<ApprovalRequestOut>(
        `/api/v1/approvals/${approvalId}?workspace_id=${workspaceId}`,
      ),
    enabled: !!approvalId && !!workspaceId,
    staleTime: APPROVALS_STALE_MS,
  });
}

export function useApprovalTimeline(
  approvalId: string | null | undefined,
  workspaceId: string | null | undefined,
) {
  return useQuery({
    queryKey: APPROVAL_TIMELINE_KEY(approvalId ?? ""),
    queryFn: () =>
      api.get<ApprovalTimelineEventOut[]>(
        `/api/v1/approvals/${approvalId}/timeline?workspace_id=${workspaceId}`,
      ),
    enabled: !!approvalId && !!workspaceId,
    staleTime: APPROVALS_STALE_MS,
  });
}

// ── Mutation hooks ────────────────────────────────────────────────────────────

export function useCreateApproval(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ApprovalRequestIn) =>
      api.post<ApprovalRequestOut>("/api/v1/approvals", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals", "list", workspaceId] });
    },
  });
}

export function useAssignReviewer(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, data }: { approvalId: string; data: ApprovalAssignIn }) =>
      api.patch<ApprovalRequestOut>(
        `/api/v1/approvals/${approvalId}/assign?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: (_result, { approvalId }) => {
      qc.invalidateQueries({ queryKey: APPROVAL_DETAIL_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: ["approvals", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: ["approvals", "my-reviews", workspaceId] });
    },
  });
}

export function useApproveRequest(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, data }: { approvalId: string; data: ApprovalDecisionIn }) =>
      api.post<ApprovalRequestOut>(
        `/api/v1/approvals/${approvalId}/approve?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: (_result, { approvalId }) => {
      qc.invalidateQueries({ queryKey: APPROVAL_DETAIL_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: APPROVAL_TIMELINE_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: ["approvals", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: ["approvals", "my-reviews", workspaceId] });
    },
  });
}

export function useRejectRequest(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, data }: { approvalId: string; data: ApprovalDecisionIn }) =>
      api.post<ApprovalRequestOut>(
        `/api/v1/approvals/${approvalId}/reject?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: (_result, { approvalId }) => {
      qc.invalidateQueries({ queryKey: APPROVAL_DETAIL_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: APPROVAL_TIMELINE_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: ["approvals", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: ["approvals", "my-reviews", workspaceId] });
    },
  });
}

export function useCancelRequest(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (approvalId: string) =>
      api.post<ApprovalRequestOut>(
        `/api/v1/approvals/${approvalId}/cancel?workspace_id=${workspaceId}`,
        {},
      ),
    onSuccess: (_result, approvalId) => {
      qc.invalidateQueries({ queryKey: APPROVAL_DETAIL_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: APPROVAL_TIMELINE_KEY(approvalId) });
      qc.invalidateQueries({ queryKey: ["approvals", "list", workspaceId] });
    },
  });
}
