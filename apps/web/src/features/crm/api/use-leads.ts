"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Lead, LeadCreate, LeadListOut, StageAdvanceResponse } from "@/features/crm/types";
import { PIPELINE_STAGES } from "@/features/crm/types";

const LEADS_KEY = (workspaceId: string) => ["crm", "leads", workspaceId] as const;
const STATS_KEY = (workspaceId: string) => ["crm", "stats", workspaceId] as const;
const LEAD_KEY = (leadId: string) => ["crm", "lead", leadId] as const;

export function usePipelineLeads(workspaceId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["crm", "leads", workspaceId],
    queryFn: () =>
      api.get<LeadListOut>(`/api/v1/crm/?workspace_id=${workspaceId}&limit=200`),
    enabled: !!workspaceId,
    staleTime: 20 * 1000,
  });

  const leadsByStage = PIPELINE_STAGES.reduce<Record<string, Lead[]>>(
    (acc, stage) => {
      acc[stage] = (query.data?.items ?? []).filter((l) => l.stage === stage);
      return acc;
    },
    {}
  );

  return { ...query, leadsByStage };
}

export function useAdvanceStage(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, notes }: { leadId: string; notes?: string }) =>
      api.post<StageAdvanceResponse>(`/api/v1/crm/${leadId}/advance`, { notes }),
    onSuccess: () => {
      if (workspaceId) {
        void queryClient.invalidateQueries({ queryKey: LEADS_KEY(workspaceId) });
        void queryClient.invalidateQueries({ queryKey: STATS_KEY(workspaceId) });
      }
    },
  });
}

export function useMarkLost(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, notes }: { leadId: string; notes?: string }) =>
      api.post<Lead>(`/api/v1/crm/${leadId}/lost`, { notes }),
    onSuccess: () => {
      if (workspaceId) {
        void queryClient.invalidateQueries({ queryKey: LEADS_KEY(workspaceId) });
        void queryClient.invalidateQueries({ queryKey: STATS_KEY(workspaceId) });
      }
    },
  });
}

export function useCreateLead(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: LeadCreate) => api.post<Lead>("/api/v1/crm/", data),
    onSuccess: () => {
      if (workspaceId) {
        void queryClient.invalidateQueries({ queryKey: LEADS_KEY(workspaceId) });
        void queryClient.invalidateQueries({ queryKey: STATS_KEY(workspaceId) });
      }
    },
  });
}

export function useGetLead(leadId: string | null | undefined) {
  return useQuery({
    queryKey: LEAD_KEY(leadId ?? ""),
    queryFn: () => api.get<Lead>(`/api/v1/crm/${leadId}`),
    enabled: !!leadId,
    staleTime: 20 * 1000,
  });
}

export function useScheduleMeeting(workspaceId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, meetingAt }: { leadId: string; meetingAt: string }) =>
      api.patch<Lead>(`/api/v1/crm/${leadId}/meeting`, { meeting_at: meetingAt }),
    onSuccess: (data) => {
      // Update the detail cache immediately so the page reflects the new time.
      queryClient.setQueryData(LEAD_KEY(data.id), data);
      if (workspaceId) {
        void queryClient.invalidateQueries({ queryKey: LEADS_KEY(workspaceId) });
      }
    },
  });
}
