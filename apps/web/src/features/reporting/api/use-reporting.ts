"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  GenerateReportRequest,
  ReportExport,
  ReportExportListResponse,
  ReportType,
} from "../types";

const BASE = "/api/v1/reports";

async function apiRequest<T>(
  input: RequestInfo,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const reportingKeys = {
  all: ["reports"] as const,
  list: (workspaceId: string, reportType?: ReportType) =>
    ["reports", "list", workspaceId, reportType ?? "all"] as const,
  detail: (reportId: string) => ["reports", "detail", reportId] as const,
};

// ── Queries ───────────────────────────────────────────────────────────────────

export function useReports(
  workspaceId: string,
  reportType?: ReportType
) {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (reportType) params.set("report_type", reportType);

  return useQuery<ReportExportListResponse>({
    queryKey: reportingKeys.list(workspaceId, reportType),
    queryFn: () =>
      apiRequest<ReportExportListResponse>(`${BASE}?${params.toString()}`),
    enabled: Boolean(workspaceId),
    staleTime: 30_000,
  });
}

export function useReport(reportId: string) {
  return useQuery<ReportExport>({
    queryKey: reportingKeys.detail(reportId),
    queryFn: () => apiRequest<ReportExport>(`${BASE}/${reportId}`),
    enabled: Boolean(reportId),
  });
}

// ── Mutations ─────────────────────────────────────────────────────────────────

export function useGenerateReport(workspaceId: string) {
  const qc = useQueryClient();

  return useMutation<ReportExport, Error, GenerateReportRequest>({
    mutationFn: (body) =>
      apiRequest<ReportExport>(`${BASE}/generate`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: reportingKeys.list(workspaceId) });
    },
  });
}

export function useDeleteReport(workspaceId: string) {
  const qc = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (reportId) =>
      apiRequest<void>(`${BASE}/${reportId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: reportingKeys.list(workspaceId) });
    },
  });
}
