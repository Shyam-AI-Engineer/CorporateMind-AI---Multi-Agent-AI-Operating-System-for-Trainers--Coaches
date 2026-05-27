"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { GenerateProposalRequest, Proposal, ProposalListOut } from "@/features/proposals/types";

const LIST_KEY = (workspaceId: string) => ["proposals", "list", workspaceId] as const;
const DETAIL_KEY = (id: string) => ["proposals", "detail", id] as const;

function useInvalidateProposals(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (proposalId?: string) => {
    if (workspaceId) void qc.invalidateQueries({ queryKey: LIST_KEY(workspaceId) });
    if (proposalId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(proposalId) });
  };
}

export function useProposals(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: LIST_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<ProposalListOut>(
        `/api/v1/proposals/?workspace_id=${workspaceId}&limit=50`
      ),
    enabled: !!workspaceId,
    staleTime: 20 * 1000,
  });
}

export function useProposal(proposalId: string | null | undefined) {
  return useQuery({
    queryKey: DETAIL_KEY(proposalId ?? ""),
    queryFn: () => api.get<Proposal>(`/api/v1/proposals/${proposalId}`),
    enabled: !!proposalId,
    staleTime: 30 * 1000,
  });
}

export function useGenerateProposal(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateProposals(workspaceId);
  return useMutation({
    mutationFn: (req: GenerateProposalRequest) =>
      api.post<Proposal>("/api/v1/proposals/", req),
    onSuccess: () => invalidate(),
  });
}

export function useMarkProposalSent(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateProposals(workspaceId);
  return useMutation({
    mutationFn: (proposalId: string) =>
      api.post<Proposal>(`/api/v1/proposals/${proposalId}/send`, {}),
    onSuccess: (_, id) => invalidate(id),
  });
}
