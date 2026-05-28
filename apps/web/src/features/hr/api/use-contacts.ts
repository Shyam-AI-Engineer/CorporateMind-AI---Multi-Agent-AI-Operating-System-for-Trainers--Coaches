"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ContactBatchImportRequest,
  ContactBatchImportResponse,
  ContactListResponse,
  HRContact,
  RankContactsRequest,
  RankContactsResponse,
} from "@/features/hr/types";

const LIST_KEY = ["hr", "contacts"] as const;
const DETAIL_KEY = (id: string) => ["hr", "contacts", id] as const;

export function useContacts(companyId?: string) {
  const params = new URLSearchParams({ limit: "100" });
  if (companyId) params.set("company_id", companyId);

  return useQuery({
    queryKey: companyId ? [...LIST_KEY, companyId] : LIST_KEY,
    queryFn: () =>
      api.get<ContactListResponse>(`/api/v1/hr/contacts?${params}`),
    staleTime: 30 * 1000,
  });
}

export function useContact(contactId: string | null | undefined) {
  return useQuery({
    queryKey: DETAIL_KEY(contactId ?? ""),
    queryFn: () => api.get<HRContact>(`/api/v1/hr/contacts/${contactId}`),
    enabled: !!contactId,
    staleTime: 60 * 1000,
  });
}

export function useImportContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ContactBatchImportRequest) =>
      api.post<ContactBatchImportResponse>("/api/v1/hr/contacts/import", req),
    onSuccess: () => void qc.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useRankContacts() {
  return useMutation({
    mutationFn: (req: RankContactsRequest) =>
      api.post<RankContactsResponse>("/api/v1/hr/contacts/rank", req),
  });
}
