"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { PipelineStats } from "@/features/crm/types";

export function usePipelineStats(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: ["crm", "stats", workspaceId],
    queryFn: () =>
      api.get<PipelineStats>(`/api/v1/crm/stats?workspace_id=${workspaceId}`),
    enabled: !!workspaceId,
    staleTime: 30 * 1000,
  });
}
