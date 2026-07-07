"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AuditLog,
  AuditLogFilters,
  AuditLogListOut,
  AuditStatisticsOut,
} from "@/features/audit/types-audit";

const STALE_MS = 300_000;

const AUDIT_LIST_KEY = (
  workspaceId: string,
  filters?: Partial<AuditLogFilters>
) => ["audit", "events", "list", workspaceId, filters ?? {}] as const;

const AUDIT_DETAIL_KEY = (id: string) => ["audit", "events", "detail", id] as const;

const AUDIT_ENTITY_KEY = (entityType: string, entityId: string) =>
  ["audit", "entity", entityType, entityId] as const;

const AUDIT_USER_KEY = (userId: string) => ["audit", "user", userId] as const;

const AUDIT_MODULE_KEY = (module: string, workspaceId: string) =>
  ["audit", "module", module, workspaceId] as const;

const AUDIT_STATS_KEY = (workspaceId: string) =>
  ["audit", "statistics", workspaceId] as const;

export function useAuditEvents(filters: AuditLogFilters | null | undefined) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: AuditLogListOut }>({
    queryKey: AUDIT_LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.module) params.set("module", filters.module);
      if (filters?.severity) params.set("severity", filters.severity);
      if (filters?.user_id) params.set("user_id", filters.user_id);
      if (filters?.entity_type) params.set("entity_type", filters.entity_type);
      if (filters?.entity_id) params.set("entity_id", filters.entity_id);
      if (filters?.action) params.set("action", filters.action);
      if (filters?.date_from) params.set("date_from", filters.date_from);
      if (filters?.date_to) params.set("date_to", filters.date_to);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: AuditLogListOut }>(`/api/v1/audit/events?${params}`);
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useAuditEvent(logId: string | null | undefined) {
  return useQuery<{ data: AuditLog }>({
    queryKey: AUDIT_DETAIL_KEY(logId ?? ""),
    queryFn: () =>
      api.get<{ data: AuditLog }>(`/api/v1/audit/events/${logId}`),
    staleTime: STALE_MS,
    enabled: !!logId,
  });
}

export function useEntityAuditEvents(
  entityType: string | null | undefined,
  entityId: string | null | undefined,
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: AuditLog[] }>({
    queryKey: AUDIT_ENTITY_KEY(entityType ?? "", entityId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: AuditLog[] }>(
        `/api/v1/audit/entity/${entityType}/${entityId}?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!entityType && !!entityId && !!workspaceId,
  });
}

export function useUserAuditEvents(
  userId: string | null | undefined,
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: AuditLog[] }>({
    queryKey: AUDIT_USER_KEY(userId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: AuditLog[] }>(
        `/api/v1/audit/user/${userId}?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!userId && !!workspaceId,
  });
}

export function useModuleAuditEvents(
  module: string | null | undefined,
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: AuditLog[] }>({
    queryKey: AUDIT_MODULE_KEY(module ?? "", workspaceId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: AuditLog[] }>(
        `/api/v1/audit/module/${module}?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!module && !!workspaceId,
  });
}

export function useAuditStatistics(
  workspaceId: string | null | undefined,
  periodDays?: number
) {
  return useQuery<{ data: AuditStatisticsOut }>({
    queryKey: AUDIT_STATS_KEY(workspaceId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      if (periodDays) params.set("period_days", String(periodDays));
      return api.get<{ data: AuditStatisticsOut }>(
        `/api/v1/audit/statistics?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}
