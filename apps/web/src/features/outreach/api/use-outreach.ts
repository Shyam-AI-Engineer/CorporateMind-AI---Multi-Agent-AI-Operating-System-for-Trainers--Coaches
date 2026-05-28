"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  GenerateOutreachRequest,
  OutboundMessage,
  SendMessageResponse,
} from "@/features/outreach/types";

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
