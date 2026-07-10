// Bulk Operations API hooks — Sprint 59.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  BulkArchivePayload,
  BulkAssignPayload,
  BulkOperationListOut,
  BulkOperationOut,
  BulkStatusUpdatePayload,
  CsvImportPayload,
  CsvValidatePayload,
  CsvValidationOut,
} from "@/features/bulk_operations/types";

const BASE = "/api/v1/bulk";

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const bulkOperationKeys = {
  all: ["bulk-operations"] as const,
  list: (workspaceId: string, entityType?: string, status?: string) =>
    ["bulk-operations", "list", workspaceId, entityType, status] as const,
  detail: (id: string) => ["bulk-operations", "detail", id] as const,
};

// ── Queries ────────────────────────────────────────────────────────────────

export function useBulkOperationList(
  workspaceId: string,
  entityType?: string,
  status?: string
) {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (entityType) params.set("entity_type", entityType);
  if (status) params.set("status", status);

  return useQuery<BulkOperationListOut>({
    queryKey: bulkOperationKeys.list(workspaceId, entityType, status),
    queryFn: () => apiFetch<BulkOperationListOut>(`${BASE}?${params}`),
    staleTime: 300_000,
  });
}

export function useBulkOperationDetail(id: string) {
  return useQuery<BulkOperationOut>({
    queryKey: bulkOperationKeys.detail(id),
    queryFn: () => apiFetch<BulkOperationOut>(`${BASE}/${id}`),
    staleTime: 300_000,
  });
}

// ── Mutations ──────────────────────────────────────────────────────────────

export function useValidateCsv() {
  return useMutation<CsvValidationOut, Error, CsvValidatePayload>({
    mutationFn: (payload) =>
      apiFetch<CsvValidationOut>(`${BASE}/validate`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  });
}

export function useImportCsv() {
  const qc = useQueryClient();
  return useMutation<BulkOperationOut, Error, CsvImportPayload>({
    mutationFn: (payload) =>
      apiFetch<BulkOperationOut>(`${BASE}/import`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bulkOperationKeys.all });
    },
  });
}

export function useBulkArchive() {
  const qc = useQueryClient();
  return useMutation<BulkOperationOut, Error, BulkArchivePayload>({
    mutationFn: (payload) =>
      apiFetch<BulkOperationOut>(`${BASE}/archive`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bulkOperationKeys.all });
    },
  });
}

export function useBulkAssign() {
  const qc = useQueryClient();
  return useMutation<BulkOperationOut, Error, BulkAssignPayload>({
    mutationFn: (payload) =>
      apiFetch<BulkOperationOut>(`${BASE}/assign`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bulkOperationKeys.all });
    },
  });
}

export function useBulkStatusUpdate() {
  const qc = useQueryClient();
  return useMutation<BulkOperationOut, Error, BulkStatusUpdatePayload>({
    mutationFn: (payload) =>
      apiFetch<BulkOperationOut>(`${BASE}/status`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bulkOperationKeys.all });
    },
  });
}
