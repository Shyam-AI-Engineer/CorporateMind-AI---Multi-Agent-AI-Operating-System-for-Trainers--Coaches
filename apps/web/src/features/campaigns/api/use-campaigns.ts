"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CampaignListOut } from "@/features/campaigns/types";

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
