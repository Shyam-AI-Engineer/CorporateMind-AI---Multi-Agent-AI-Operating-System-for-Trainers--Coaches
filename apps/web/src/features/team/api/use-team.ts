"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ActivityFeedPage,
  CommentIn,
  CommentOut,
  MemberAcceptIn,
  MemberInviteIn,
  MemberListOut,
  MemberRoleUpdate,
  TaskAssignIn,
  WorkspaceMemberOut,
} from "@/features/team/types";
import type { BusinessTaskOut } from "@/features/operations/types";

const MEMBERS_STALE_MS = 10 * 60 * 1000; // 10 minutes — matches backend Redis TTL
const ACTIVITY_STALE_MS = 5 * 60 * 1000; // 5 minutes
const COMMENTS_STALE_MS = 5 * 60 * 1000; // 5 minutes

// ── Query key factories ───────────────────────────────────────────────────────

const MEMBERS_KEY = (workspaceId: string) =>
  ["team", "members", workspaceId] as const;

const ACTIVITY_KEY = (workspaceId: string, cursor?: string) =>
  ["team", "activity", workspaceId, cursor ?? "first"] as const;

const COMMENTS_KEY = (workspaceId: string, taskId: string) =>
  ["team", "comments", workspaceId, taskId] as const;

// ── Member query hooks ────────────────────────────────────────────────────────

export function useTeamMembers(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: MEMBERS_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<MemberListOut>(`/api/v1/team/members?workspace_id=${workspaceId}`),
    enabled: !!workspaceId,
    staleTime: MEMBERS_STALE_MS,
  });
}

export function useActivityFeed(
  workspaceId: string | null | undefined,
  cursor?: string,
) {
  return useQuery({
    queryKey: ACTIVITY_KEY(workspaceId ?? "", cursor),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      return api.get<ActivityFeedPage>(`/api/v1/team/activity?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: ACTIVITY_STALE_MS,
  });
}

export function useTaskComments(
  workspaceId: string | null | undefined,
  taskId: string | null | undefined,
) {
  return useQuery({
    queryKey: COMMENTS_KEY(workspaceId ?? "", taskId ?? ""),
    queryFn: () =>
      api.get<CommentOut[]>(
        `/api/v1/operations/tasks/${taskId}/comments?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId && !!taskId,
    staleTime: COMMENTS_STALE_MS,
  });
}

// ── Member mutation hooks ─────────────────────────────────────────────────────

export function useInviteMember(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MemberInviteIn) =>
      api.post<WorkspaceMemberOut>("/api/v1/team/invite", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY(workspaceId) });
    },
  });
}

export function useAcceptInvitation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MemberAcceptIn) =>
      api.post<WorkspaceMemberOut>("/api/v1/team/accept", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY(workspaceId) });
    },
  });
}

export function useChangeMemberRole(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      memberId,
      data,
    }: {
      memberId: string;
      data: MemberRoleUpdate;
    }) =>
      api.patch<WorkspaceMemberOut>(
        `/api/v1/team/${memberId}/role?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY(workspaceId) });
    },
  });
}

export function useRemoveMember(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) =>
      api.delete(
        `/api/v1/team/${memberId}?workspace_id=${workspaceId}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MEMBERS_KEY(workspaceId) });
    },
  });
}

// ── Comment mutation hooks ────────────────────────────────────────────────────

export function useCreateComment(workspaceId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CommentIn) =>
      api.post<CommentOut>(
        `/api/v1/operations/tasks/${taskId}/comments?workspace_id=${workspaceId}`,
        data,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COMMENTS_KEY(workspaceId, taskId) });
      qc.invalidateQueries({ queryKey: ACTIVITY_KEY(workspaceId) });
    },
  });
}

export function useDeleteComment(workspaceId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) =>
      api.delete(
        `/api/v1/operations/comments/${commentId}?workspace_id=${workspaceId}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COMMENTS_KEY(workspaceId, taskId) });
    },
  });
}

export function useAssignTask(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      data,
    }: {
      taskId: string;
      data: TaskAssignIn;
    }) =>
      api.patch<BusinessTaskOut>(
        `/api/v1/operations/tasks/${taskId}/assign`,
        data,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["operations", "tasks", workspaceId] });
    },
  });
}
