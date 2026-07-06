"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AssignRenewalOwner,
  AttachProposal,
  CustomerRenewal,
  CustomerRenewalCreate,
  CustomerRenewalFilters,
  CustomerRenewalListOut,
  CustomerRenewalUpdate,
  UpdateRenewalStatus,
} from "@/features/customers/types-renewal";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<CustomerRenewalFilters>) =>
  ["customer-renewals", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["customer-renewals", "detail", id] as const;

const CUSTOMER_KEY = (customerId: string) =>
  ["customer-renewals", "customer", customerId] as const;

function useInvalidateRenewal(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (recordId?: string, customerId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({
        queryKey: ["customer-renewals", "list", workspaceId],
      });
    }
    if (recordId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(recordId) });
    if (customerId)
      void qc.invalidateQueries({ queryKey: CUSTOMER_KEY(customerId) });
  };
}

export function useCustomerRenewalList(
  filters: CustomerRenewalFilters | null | undefined
) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: CustomerRenewalListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.customer_id) params.set("customer_id", filters.customer_id);
      if (filters?.renewal_type) params.set("renewal_type", filters.renewal_type);
      if (filters?.renewal_status) params.set("renewal_status", filters.renewal_status);
      if (filters?.owner_user_id) params.set("owner_user_id", filters.owner_user_id);
      if (filters?.renewal_date_from)
        params.set("renewal_date_from", filters.renewal_date_from);
      if (filters?.renewal_date_to)
        params.set("renewal_date_to", filters.renewal_date_to);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.include_archived) params.set("include_archived", "true");
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: CustomerRenewalListOut }>(
        `/api/v1/customer-renewals?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useCustomerRenewalDetail(recordId: string | null | undefined) {
  return useQuery<{ data: CustomerRenewal }>({
    queryKey: DETAIL_KEY(recordId ?? ""),
    queryFn: () =>
      api.get<{ data: CustomerRenewal }>(`/api/v1/customer-renewals/${recordId}`),
    staleTime: STALE_MS,
    enabled: !!recordId,
  });
}

export function useRenewalsByCustomer(
  customerId: string | null | undefined,
  workspaceId: string | null | undefined
) {
  return useQuery<{ data: CustomerRenewalListOut }>({
    queryKey: CUSTOMER_KEY(customerId ?? ""),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId! });
      return api.get<{ data: CustomerRenewalListOut }>(
        `/api/v1/customers/${customerId}/renewals?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!customerId && !!workspaceId,
  });
}

export function useCreateCustomerRenewal(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<{ data: CustomerRenewal }, Error, CustomerRenewalCreate>({
    mutationFn: (body) =>
      api.post<{ data: CustomerRenewal }>("/api/v1/customer-renewals", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateCustomerRenewal(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<
    { data: CustomerRenewal },
    Error,
    { id: string; body: CustomerRenewalUpdate; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: CustomerRenewal }>(`/api/v1/customer-renewals/${id}`, body),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useAssignRenewalOwner(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<
    { data: CustomerRenewal },
    Error,
    { id: string; body: AssignRenewalOwner; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerRenewal }>(
        `/api/v1/customer-renewals/${id}/assign-owner`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useUpdateRenewalStatus(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<
    { data: CustomerRenewal },
    Error,
    { id: string; body: UpdateRenewalStatus; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerRenewal }>(
        `/api/v1/customer-renewals/${id}/update-status`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useAttachProposal(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<
    { data: CustomerRenewal },
    Error,
    { id: string; body: AttachProposal; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerRenewal }>(
        `/api/v1/customer-renewals/${id}/attach-proposal`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useArchiveCustomerRenewal(workspaceId: string) {
  const invalidate = useInvalidateRenewal(workspaceId);
  return useMutation<{ data: CustomerRenewal }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: CustomerRenewal }>(
        `/api/v1/customer-renewals/${id}/archive`,
        {}
      ),
    onSuccess: (_, id) => invalidate(id),
  });
}
