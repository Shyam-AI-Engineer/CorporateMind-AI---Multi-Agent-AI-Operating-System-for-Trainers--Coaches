"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  GenerateProposalRequest,
  Proposal,
  ProposalListOut,
  RejectProposalRequest,
} from "@/features/proposals/types";

const LIST_KEY = (workspaceId: string, approvalStatus?: string) =>
  ["proposals", "list", workspaceId, approvalStatus ?? "all"] as const;

const DETAIL_KEY = (id: string) => ["proposals", "detail", id] as const;

function useInvalidateProposals(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (proposalId?: string) => {
    // Invalidate all list queries for this workspace across all filter values.
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["proposals", "list", workspaceId] });
    }
    if (proposalId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(proposalId) });
  };
}

export function useProposals(
  workspaceId: string | null | undefined,
  approvalStatus?: string,
) {
  return useQuery({
    queryKey: LIST_KEY(workspaceId ?? "", approvalStatus),
    queryFn: () => {
      const params = new URLSearchParams({
        workspace_id: workspaceId!,
        limit: "50",
      });
      if (approvalStatus) params.set("approval_status", approvalStatus);
      return api.get<ProposalListOut>(`/api/v1/proposals/?${params.toString()}`);
    },
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

export function useApproveProposal(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateProposals(workspaceId);
  return useMutation({
    mutationFn: (proposalId: string) =>
      api.post<Proposal>(`/api/v1/proposals/${proposalId}/approve`, {}),
    onSuccess: (_, proposalId) => invalidate(proposalId),
  });
}

export function useRejectProposal(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateProposals(workspaceId);
  return useMutation({
    mutationFn: ({ proposalId, reason }: RejectProposalRequest) =>
      api.post<Proposal>(`/api/v1/proposals/${proposalId}/reject`, { reason }),
    onSuccess: (_, { proposalId }) => invalidate(proposalId),
  });
}

export function useDeliverProposal(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateProposals(workspaceId);
  return useMutation({
    mutationFn: (proposalId: string) =>
      api.post<Proposal>(`/api/v1/proposals/${proposalId}/send`, {}),
    onSuccess: (_, proposalId) => invalidate(proposalId),
  });
}

export function useProposalsForContact(
  workspaceId: string | null | undefined,
  contactId: string | null | undefined,
) {
  return useQuery({
    queryKey: ["proposals", "by-contact", workspaceId, contactId] as const,
    queryFn: () => {
      const params = new URLSearchParams({
        workspace_id: workspaceId!,
        contact_id: contactId!,
        limit: "20",
      });
      return api.get<ProposalListOut>(`/api/v1/proposals/?${params.toString()}`);
    },
    enabled: !!workspaceId && !!contactId,
    staleTime: 30 * 1000,
  });
}
