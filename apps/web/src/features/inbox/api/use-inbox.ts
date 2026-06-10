"use client";

/**
 * TanStack Query hooks for the Inbox feature.
 *
 * Conventions copied from features/crm/api/use-leads.ts:
 *   - All keys nested under the feature name → cache invalidation is surgical.
 *   - staleTime: 20s for lists (refresh on focus without thrash).
 *   - Mutations invalidate the matching list keys on success.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ConnectionHealth,
  InboxConnectionListOut,
  InboxMessageListOut,
  ReplyIntent,
} from "@/features/inbox/types";

const CONNECTIONS_KEY = (workspaceId: string) =>
  ["inbox", "connections", workspaceId] as const;

const MESSAGES_KEY = (params: ListMessagesParams) =>
  ["inbox", "messages", params] as const;

export interface ListMessagesParams {
  connection_id?: string;
  intent?: ReplyIntent;
  limit?: number;
  offset?: number;
}

// ── Connections ─────────────────────────────────────────────────────────────

export function useInboxConnections(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: workspaceId
      ? CONNECTIONS_KEY(workspaceId)
      : (["inbox", "connections", "pending"] as const),
    queryFn: () =>
      api.get<InboxConnectionListOut>("/api/v1/inbox/connections?limit=50"),
    enabled: !!workspaceId,
    staleTime: 20 * 1000,
  });
}

export function useDisconnectInbox(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connectionId: string) =>
      api.delete<void>(`/api/v1/inbox/connection/${connectionId}`),
    onSuccess: () => {
      if (workspaceId)
        void qc.invalidateQueries({ queryKey: CONNECTIONS_KEY(workspaceId) });
    },
  });
}

export function useCheckConnectionHealth(
  workspaceId: string | null | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connectionId: string) =>
      api.get<ConnectionHealth>(
        `/api/v1/inbox/connection/${connectionId}/health`,
      ),
    onSuccess: () => {
      // Health probe may flip status → refresh the list so badges update.
      if (workspaceId)
        void qc.invalidateQueries({ queryKey: CONNECTIONS_KEY(workspaceId) });
    },
  });
}

// ── Messages ────────────────────────────────────────────────────────────────

export function useInboxMessages(
  workspaceId: string | null | undefined,
  params: ListMessagesParams = {},
) {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  if (params.connection_id) search.set("connection_id", params.connection_id);
  if (params.intent) search.set("intent", params.intent);

  return useQuery({
    queryKey: MESSAGES_KEY(params),
    queryFn: () =>
      api.get<InboxMessageListOut>(`/api/v1/inbox/messages?${search}`),
    enabled: !!workspaceId,
    staleTime: 20 * 1000,
  });
}
