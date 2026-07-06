"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AssignOwner,
  CustomerSuccess,
  CustomerSuccessCreate,
  CustomerSuccessFilters,
  CustomerSuccessListOut,
  CustomerSuccessUpdate,
  ScheduleFollowup,
  UpdateHealth,
} from "@/features/customers/types-success";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<CustomerSuccessFilters>) =>
  ["customer-success", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["customer-success", "detail", id] as const;

const CUSTOMER_KEY = (customerId: string) =>
  ["customer-success", "customer", customerId] as const;

function useInvalidateSuccess(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (recordId?: string, customerId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["customer-success", "list", workspaceId] });
    }
    if (recordId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(recordId) });
    if (customerId) void qc.invalidateQueries({ queryKey: CUSTOMER_KEY(customerId) });
  };
}

export function useCustomerSuccessList(
  filters: CustomerSuccessFilters | null | undefined
) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: CustomerSuccessListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.health_status) params.set("health_status", filters.health_status);
      if (filters?.risk_level) params.set("risk_level", filters.risk_level);
      if (filters?.owner_user_id) params.set("owner_user_id", filters.owner_user_id);
      if (filters?.renewal_date_from) params.set("renewal_date_from", filters.renewal_date_from);
      if (filters?.renewal_date_to) params.set("renewal_date_to", filters.renewal_date_to);
      if (filters?.followup_due_by) params.set("followup_due_by", filters.followup_due_by);
      if (filters?.expansion_opportunity !== undefined)
        params.set("expansion_opportunity", String(filters.expansion_opportunity));
      if (filters?.search) params.set("search", filters.search);
      if (filters?.include_archived) params.set("include_archived", "true");
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: CustomerSuccessListOut }>(
        `/api/v1/customer-success?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useCustomerSuccessDetail(recordId: string | null | undefined) {
  return useQuery<{ data: CustomerSuccess }>({
    queryKey: DETAIL_KEY(recordId ?? ""),
    queryFn: () =>
      api.get<{ data: CustomerSuccess }>(`/api/v1/customer-success/${recordId}`),
    staleTime: STALE_MS,
    enabled: !!recordId,
  });
}

export function useCustomerSuccessByCustomer(customerId: string | null | undefined) {
  return useQuery<{ data: CustomerSuccess }>({
    queryKey: CUSTOMER_KEY(customerId ?? ""),
    queryFn: () =>
      api.get<{ data: CustomerSuccess }>(
        `/api/v1/customers/${customerId}/success`
      ),
    staleTime: STALE_MS,
    enabled: !!customerId,
  });
}

export function useCreateCustomerSuccess(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<{ data: CustomerSuccess }, Error, CustomerSuccessCreate>({
    mutationFn: (body) =>
      api.post<{ data: CustomerSuccess }>("/api/v1/customer-success", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateCustomerSuccess(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<
    { data: CustomerSuccess },
    Error,
    { id: string; body: CustomerSuccessUpdate; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: CustomerSuccess }>(`/api/v1/customer-success/${id}`, body),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useAssignSuccessOwner(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<
    { data: CustomerSuccess },
    Error,
    { id: string; body: AssignOwner; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerSuccess }>(
        `/api/v1/customer-success/${id}/assign-owner`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useUpdateSuccessHealth(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<
    { data: CustomerSuccess },
    Error,
    { id: string; body: UpdateHealth; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerSuccess }>(
        `/api/v1/customer-success/${id}/update-health`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useScheduleFollowup(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<
    { data: CustomerSuccess },
    Error,
    { id: string; body: ScheduleFollowup; customerId?: string }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: CustomerSuccess }>(
        `/api/v1/customer-success/${id}/schedule-followup`,
        body
      ),
    onSuccess: (_, { id, customerId }) => invalidate(id, customerId),
  });
}

export function useArchiveCustomerSuccess(workspaceId: string) {
  const invalidate = useInvalidateSuccess(workspaceId);
  return useMutation<{ data: CustomerSuccess }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: CustomerSuccess }>(
        `/api/v1/customer-success/${id}/archive`,
        {}
      ),
    onSuccess: (_, id) => invalidate(id),
  });
}
