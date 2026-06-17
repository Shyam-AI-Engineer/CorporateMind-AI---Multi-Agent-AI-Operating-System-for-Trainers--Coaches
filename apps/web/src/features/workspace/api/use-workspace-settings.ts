"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { WorkspaceBookingWebhook } from "@/features/workspace/types";

const BOOKING_WEBHOOK_KEY = ["workspace", "booking-webhook"] as const;

export function useBookingWebhook() {
  return useQuery({
    queryKey: BOOKING_WEBHOOK_KEY,
    queryFn: () => api.get<WorkspaceBookingWebhook>("/api/v1/identity/workspace/booking-webhook"),
    staleTime: 30 * 1000,
  });
}

export function useRegenerateBookingSecret() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<WorkspaceBookingWebhook>(
        "/api/v1/identity/workspace/booking-webhook/regenerate",
        {},
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(BOOKING_WEBHOOK_KEY, data);
    },
  });
}
