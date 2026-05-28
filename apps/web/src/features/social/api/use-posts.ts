"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SocialPost, SocialPostCreate, SocialPostListOut } from "@/features/social/types";

const LIST_KEY = (workspaceId: string) => ["social", "posts", workspaceId] as const;

export function useSocialPosts(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: LIST_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SocialPostListOut>(
        `/api/v1/social/posts?workspace_id=${workspaceId}&limit=50`
      ),
    enabled: !!workspaceId,
    staleTime: 30 * 1000,
  });
}

export function useCreatePost(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: SocialPostCreate) =>
      api.post<SocialPost>("/api/v1/social/posts", req),
    onSuccess: () => {
      if (workspaceId) void qc.invalidateQueries({ queryKey: LIST_KEY(workspaceId) });
    },
  });
}

export function useDeletePost(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (postId: string) =>
      api.delete<void>(`/api/v1/social/posts/${postId}`),
    onSuccess: () => {
      if (workspaceId) void qc.invalidateQueries({ queryKey: LIST_KEY(workspaceId) });
    },
  });
}
