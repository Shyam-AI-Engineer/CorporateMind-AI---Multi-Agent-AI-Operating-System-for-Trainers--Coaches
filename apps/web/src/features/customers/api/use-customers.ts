"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Customer,
  CustomerCreate,
  CustomerFilters,
  CustomerHealthUpdate,
  CustomerListOut,
  CustomerOwnerAssign,
  CustomerUpdate,
} from "@/features/customers/types";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<CustomerFilters>) =>
  ["customers", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["customers", "detail", id] as const;

function useInvalidateCustomers(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (customerId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["customers", "list", workspaceId] });
    }
    if (customerId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(customerId) });
  };
}

export function useCustomers(filters: CustomerFilters | null | undefined) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: CustomerListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.status) params.set("status", filters.status);
      if (filters?.industry) params.set("industry", filters.industry);
      if (filters?.health_status) params.set("health_status", filters.health_status);
      if (filters?.owner_id) params.set("owner_id", filters.owner_id);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: CustomerListOut }>(`/api/v1/customers?${params}`);
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useCustomer(customerId: string | null | undefined) {
  return useQuery<{ data: Customer }>({
    queryKey: DETAIL_KEY(customerId ?? ""),
    queryFn: () => api.get<{ data: Customer }>(`/api/v1/customers/${customerId}`),
    staleTime: STALE_MS,
    enabled: !!customerId,
  });
}

export function useCreateCustomer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCustomers(workspaceId);
  return useMutation<{ data: Customer }, Error, CustomerCreate>({
    mutationFn: (body) => api.post<{ data: Customer }>("/api/v1/customers/", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateCustomer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCustomers(workspaceId);
  return useMutation<{ data: Customer }, Error, { id: string; body: CustomerUpdate }>({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: Customer }>(`/api/v1/customers/${id}`, body),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useArchiveCustomer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCustomers(workspaceId);
  return useMutation<{ data: Customer }, Error, string>({
    mutationFn: (id) => api.delete<{ data: Customer }>(`/api/v1/customers/${id}`),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useAssignOwner(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCustomers(workspaceId);
  return useMutation<{ data: Customer }, Error, { id: string; body: CustomerOwnerAssign }>({
    mutationFn: ({ id, body }) =>
      api.post<{ data: Customer }>(`/api/v1/customers/${id}/assign-owner`, body),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useUpdateCustomerHealth(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCustomers(workspaceId);
  return useMutation<{ data: Customer }, Error, { id: string; body: CustomerHealthUpdate }>({
    mutationFn: ({ id, body }) =>
      api.post<{ data: Customer }>(`/api/v1/customers/${id}/health`, body),
    onSuccess: (_, { id }) => invalidate(id),
  });
}
