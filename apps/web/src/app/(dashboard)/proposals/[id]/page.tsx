"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useProposal, useMarkProposalSent } from "@/features/proposals/api/use-proposals";
import { ProposalStatusBadge } from "@/features/proposals/ui/proposal-status-badge";
import { ProposalContentView } from "@/features/proposals/ui/proposal-content-view";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";

export default function ProposalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { workspaceId } = useWorkspace();
  const { data: proposal, isLoading, isError } = useProposal(id);
  const markSent = useMarkProposalSent(workspaceId);

  if (isLoading) {
    return (
      <div className="p-6 space-y-4 max-w-3xl">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-64" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  if (isError || !proposal) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">Proposal not found.</p>
        <Link
          href="/proposals"
          className="mt-2 inline-block text-sm text-primary underline-offset-2 hover:underline"
        >
          Back to proposals
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Breadcrumb */}
      <div className="text-xs text-muted-foreground">
        <Link href="/proposals" className="hover:underline">
          Proposals
        </Link>
        {" / "}
        <span className="truncate">{proposal.title}</span>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold leading-snug">{proposal.title}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Contact {proposal.contact_id.slice(0, 8)}…
          </p>
        </div>
        <ProposalStatusBadge status={proposal.status} />
      </div>

      {/* Metadata row */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border p-4 text-sm sm:grid-cols-3">
        {[
          { label: "Status",  value: <ProposalStatusBadge status={proposal.status} /> },
          { label: "Created", value: new Date(proposal.created_at).toLocaleString() },
          { label: "Sent at", value: proposal.sent_at ? new Date(proposal.sent_at).toLocaleString() : "—" },
        ].map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      {/* Mark as sent action */}
      {proposal.status === "draft" && (
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            disabled={markSent.isPending}
            onClick={() => markSent.mutate(proposal.id)}
          >
            {markSent.isPending ? "Marking…" : "Mark as sent"}
          </Button>
          {markSent.isError && (
            <p className="text-xs text-destructive">Failed — please try again.</p>
          )}
        </div>
      )}

      {/* Proposal content */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold">Proposal content</h2>
        <ProposalContentView proposal={proposal} />
      </div>
    </div>
  );
}
