"use client";

import Link from "next/link";
import { useProposals } from "@/features/proposals/api/use-proposals";
import { ProposalStatusBadge } from "@/features/proposals/ui/proposal-status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

interface ProposalListProps {
  workspaceId: string;
  onGenerate: () => void;
}

export function ProposalList({ workspaceId, onGenerate }: ProposalListProps) {
  const { data, isLoading, isError, refetch } = useProposals(workspaceId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">Failed to load proposals.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const proposals = data?.items ?? [];

  if (proposals.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No proposals yet. Generate one from an eligible CRM lead.
        </p>
        <Button size="sm" onClick={onGenerate}>
          Generate proposal
        </Button>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-3 font-medium">Title</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Contact</th>
            <th className="px-4 py-3 font-medium">Sent at</th>
            <th className="px-4 py-3 font-medium">Created</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {proposals.map((p) => (
            <tr key={p.id} className="hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 font-medium max-w-[260px] truncate">
                {p.title}
              </td>
              <td className="px-4 py-3">
                <ProposalStatusBadge status={p.status} />
              </td>
              <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                {p.contact_id.slice(0, 8)}…
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {p.sent_at ? new Date(p.sent_at).toLocaleDateString() : "—"}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {new Date(p.created_at).toLocaleDateString()}
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/proposals/${p.id}`}
                  className="text-xs text-primary underline-offset-2 hover:underline"
                >
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
