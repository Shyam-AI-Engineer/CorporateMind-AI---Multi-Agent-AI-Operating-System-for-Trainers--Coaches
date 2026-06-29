"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  NotificationIn,
  NotificationListPage,
  NotificationOut,
  UnreadCountOut,
} from "@/features/notifications/types";

const NOTIFICATIONS_STALE_MS = 5 * 60 * 1000; // 300s — matches backend list cache TTL
const UNREAD_COUNT_STALE_MS = 60 * 1000;        // 60s — matches backend count cache TTL

// ── Query key factories ───────────────────────────────────────────────────────

const NOTIFICATION_LIST_KEY = (
  workspaceId: string,
  cursor?: string,
  filters?: Record<string, string | boolean | undefined>,
) => ["notifications", "list", workspaceId, cursor ?? "first", filters ?? {}] as const;

const NOTIFICATION_COUNT_KEY = (workspaceId: string) =>
  ["notifications", "count", workspaceId] as const;

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useNotifications(
  workspaceId: string | null | undefined,
  options?: {
    cursor?: string;
    is_read?: boolean;
    priority?: string;
    entity_type?: string;
  },
) {
  const { cursor, is_read, priority, entity_type } = options ?? {};
  return useQuery({
    queryKey: NOTIFICATION_LIST_KEY(workspaceId ?? "", cursor, {
      is_read: is_read?.toString(),
      priority,
      entity_type,
    }),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (cursor) params.set("cursor", cursor);
      if (is_read !== undefined) params.set("is_read", String(is_read));
      if (priority) params.set("priority", priority);
      if (entity_type) params.set("entity_type", entity_type);
      return api.get<NotificationListPage>(`/api/v1/notifications?${params}`);
    },
    enabled: !!workspaceId,
    staleTime: NOTIFICATIONS_STALE_MS,
  });
}

export function useUnreadCount(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: NOTIFICATION_COUNT_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<UnreadCountOut>(
        `/api/v1/notifications/unread-count?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: UNREAD_COUNT_STALE_MS,
    refetchInterval: UNREAD_COUNT_STALE_MS,
  });
}

// ── Mutation hooks ────────────────────────────────────────────────────────────

export function useMarkNotificationRead(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      api.patch<NotificationOut>(
        `/api/v1/notifications/${notificationId}/read`,
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: NOTIFICATION_COUNT_KEY(workspaceId) });
    },
  });
}

export function useMarkAllRead(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.patch<{ updated: number }>(
        `/api/v1/notifications/read-all?workspace_id=${workspaceId}`,
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: NOTIFICATION_COUNT_KEY(workspaceId) });
    },
  });
}

export function useDeleteNotification(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      api.delete<void>(`/api/v1/notifications/${notificationId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: NOTIFICATION_COUNT_KEY(workspaceId) });
    },
  });
}

export function useCreateNotification(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationIn) =>
      api.post<NotificationOut>("/api/v1/notifications", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", "list", workspaceId] });
      qc.invalidateQueries({ queryKey: NOTIFICATION_COUNT_KEY(workspaceId) });
    },
  });
}
