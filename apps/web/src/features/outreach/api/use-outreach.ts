"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  GenerateOutreachRequest,
  OutboundMessage,
  OutboundMessageListOut,
  SendMessageResponse,
} from "@/features/outreach/types";

export function useCampaignMessages(
  campaignId: string | null | undefined,
  limit = 10,
  offset = 0,
) {
  const params = new URLSearchParams({
    campaign_id: campaignId ?? "",
    limit: String(limit),
    offset: String(offset),
  });
  return useQuery({
    queryKey: ["outreach", "campaign", campaignId, limit, offset],
    queryFn: () => api.get<OutboundMessageListOut>(`/api/v1/outreach/?${params}`),
    enabled: !!campaignId,
    staleTime: 20 * 1000,
  });
}

export function useGenerateOutreach() {
  return useMutation({
    mutationFn: (req: GenerateOutreachRequest) =>
      api.post<OutboundMessage>("/api/v1/outreach/generate", req),
  });
}

export function useSendMessage() {
  return useMutation({
    mutationFn: (messageId: string) =>
      api.post<SendMessageResponse>(`/api/v1/outreach/${messageId}/send`, {}),
  });
}
