"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AddRecipientsResponse,
  Campaign,
  CampaignCreate,
  CampaignLaunchResponse,
  CampaignListOut,
} from "@/features/campaigns/types";

const LIST_KEY = (workspaceId: string) => ["campaigns", "list", workspaceId] as const;
const DETAIL_KEY = (id: string) => ["campaigns", "detail", id] as const;

interface UseCampaignsOptions {
  status?: string;
  limit?: number;
}

export function useCampaigns(
  workspaceId: string | null | undefined,
  options: UseCampaignsOptions = {}
) {
  const { status, limit = 5 } = options;
  const params = new URLSearchParams({ workspace_id: workspaceId ?? "", limit: String(limit) });
  if (status) params.set("status", status);

  return useQuery({
    queryKey: ["campaigns", workspaceId, options],
    queryFn: () => api.get<CampaignListOut>(`/api/v1/campaigns/?${params}`),
    enabled: !!workspaceId,
    staleTime: 30 * 1000,
  });
}

export function useCampaignList(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: LIST_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<CampaignListOut>(
        `/api/v1/campaigns/?workspace_id=${workspaceId}&limit=50`
      ),
    enabled: !!workspaceId,
    staleTime: 20 * 1000,
  });
}

function useInvalidateCampaigns(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (campaignId?: string) => {
    if (workspaceId) void qc.invalidateQueries({ queryKey: LIST_KEY(workspaceId) });
    if (campaignId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(campaignId) });
  };
}

export function useCreateCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (data: CampaignCreate & { workspace_id: string }) =>
      api.post<Campaign>("/api/v1/campaigns/", data),
    onSuccess: () => invalidate(),
  });
}

export function useLockCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (campaignId: string) =>
      api.post<Campaign>(`/api/v1/campaigns/${campaignId}/lock`, {}),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useLaunchCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (campaignId: string) =>
      api.post<CampaignLaunchResponse>(`/api/v1/campaigns/${campaignId}/launch`, {}),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function usePauseCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (campaignId: string) =>
      api.patch<void>(`/api/v1/campaigns/${campaignId}/status`, { status: "paused" }),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useResumeCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (campaignId: string) =>
      api.patch<void>(`/api/v1/campaigns/${campaignId}/status`, { status: "resumed" }),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useCancelCampaign(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: (campaignId: string) =>
      api.patch<void>(`/api/v1/campaigns/${campaignId}/status`, { status: "cancelled" }),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useAddRecipients(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCampaigns(workspaceId);
  return useMutation({
    mutationFn: ({
      campaignId,
      contactIds,
    }: {
      campaignId: string;
      contactIds: string[];
    }) =>
      api.post<AddRecipientsResponse>(
        `/api/v1/campaigns/${campaignId}/recipients`,
        { contact_ids: contactIds }
      ),
    onSuccess: (_, { campaignId }) => invalidate(campaignId),
  });
}
