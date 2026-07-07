"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CustomerInvoice,
  CustomerInvoiceCreate,
  CustomerInvoiceFilters,
  CustomerInvoiceListOut,
  CustomerInvoiceUpdate,
  InvoiceKPIsOut,
  MarkInvoicePaid,
} from "@/features/billing/types-billing";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<CustomerInvoiceFilters>) =>
  ["invoices", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["invoices", "detail", id] as const;

const KPIS_KEY = (workspaceId: string) => ["invoices", "kpis", workspaceId] as const;

const CUSTOMER_INVOICES_KEY = (customerId: string) =>
  ["invoices", "customer", customerId] as const;

function useInvalidateInvoice(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (recordId?: string, customerId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["invoices", "list", workspaceId] });
      void qc.invalidateQueries({ queryKey: KPIS_KEY(workspaceId) });
    }
    if (recordId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(recordId) });
    if (customerId)
      void qc.invalidateQueries({ queryKey: CUSTOMER_INVOICES_KEY(customerId) });
  };
}

export function useInvoiceKPIs(workspaceId: string | null | undefined) {
  return useQuery<{ data: InvoiceKPIsOut }>({
    queryKey: KPIS_KEY(workspaceId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: InvoiceKPIsOut }>(`/api/v1/billing/invoices/kpis?${params}`);
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useInvoiceList(filters: CustomerInvoiceFilters | null | undefined) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: CustomerInvoiceListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.customer_id) params.set("customer_id", filters.customer_id);
      if (filters?.status) params.set("status", filters.status);
      if (filters?.invoice_date_from)
        params.set("invoice_date_from", filters.invoice_date_from);
      if (filters?.invoice_date_to)
        params.set("invoice_date_to", filters.invoice_date_to);
      if (filters?.due_date_from) params.set("due_date_from", filters.due_date_from);
      if (filters?.due_date_to) params.set("due_date_to", filters.due_date_to);
      if (filters?.renewal_id) params.set("renewal_id", filters.renewal_id);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: CustomerInvoiceListOut }>(
        `/api/v1/billing/invoices?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useInvoiceDetail(recordId: string | null | undefined) {
  return useQuery<{ data: CustomerInvoice }>({
    queryKey: DETAIL_KEY(recordId ?? ""),
    queryFn: () =>
      api.get<{ data: CustomerInvoice }>(`/api/v1/billing/invoices/${recordId}`),
    staleTime: STALE_MS,
    enabled: !!recordId,
  });
}

export function useInvoicesByCustomer(
  customerId: string | null | undefined,
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: CustomerInvoiceListOut }>({
    queryKey: CUSTOMER_INVOICES_KEY(customerId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: CustomerInvoiceListOut }>(
        `/api/v1/customers/${customerId}/invoices?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!customerId && !!workspaceId,
  });
}

export function useCreateInvoice(workspaceId: string) {
  const invalidate = useInvalidateInvoice(workspaceId);
  return useMutation<{ data: CustomerInvoice }, Error, CustomerInvoiceCreate>({
    mutationFn: (body) =>
      api.post<{ data: CustomerInvoice }>("/api/v1/billing/invoices", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateInvoice(workspaceId: string) {
  const invalidate = useInvalidateInvoice(workspaceId);
  return useMutation<
    { data: CustomerInvoice },
    Error,
    { id: string; body: CustomerInvoiceUpdate; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: CustomerInvoice }>(`/api/v1/billing/invoices/${id}`, body),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useIssueInvoice(workspaceId: string) {
  const invalidate = useInvalidateInvoice(workspaceId);
  return useMutation<{ data: CustomerInvoice }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: CustomerInvoice }>(`/api/v1/billing/invoices/${id}/issue`, {}),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useMarkInvoicePaid(workspaceId: string) {
  const invalidate = useInvalidateInvoice(workspaceId);
  return useMutation<
    { data: CustomerInvoice },
    Error,
    { id: string; body: MarkInvoicePaid }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerInvoice }>(
        `/api/v1/billing/invoices/${id}/mark-paid`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useCancelInvoice(workspaceId: string) {
  const invalidate = useInvalidateInvoice(workspaceId);
  return useMutation<{ data: CustomerInvoice }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: CustomerInvoice }>(
        `/api/v1/billing/invoices/${id}/cancel`,
        {}
      ),
    onSuccess: (_, id) => invalidate(id),
  });
}
