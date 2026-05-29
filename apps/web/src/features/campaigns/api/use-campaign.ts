"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Campaign, CampaignRecipient } from "@/features/campaigns/types";

export function useCampaign(campaignId: string | null | undefined) {
  return useQuery({
    queryKey: ["campaigns", "detail", campaignId],
    queryFn: () => api.get<Campaign>(`/api/v1/campaigns/${campaignId}`),
    enabled: !!campaignId,
    staleTime: 15 * 1000,
    refetchInterval: (query) => {
      // Poll more frequently while campaign is actively running
      const status = query.state.data?.status;
      return status === "running" ? 10_000 : false;
    },
  });
}

export function useCampaignRecipients(
  campaignId: string | null | undefined,
  limit = 50,
  campaignStatus?: string
) {
  return useQuery({
    queryKey: ["campaigns", "recipients", campaignId, limit],
    queryFn: () =>
      api.get<CampaignRecipient[]>(
        `/api/v1/campaigns/${campaignId}/recipients?limit=${limit}`
      ),
    enabled: !!campaignId,
    staleTime: 15 * 1000,
    refetchInterval: campaignStatus === "running" ? 10_000 : false,
  });
}
