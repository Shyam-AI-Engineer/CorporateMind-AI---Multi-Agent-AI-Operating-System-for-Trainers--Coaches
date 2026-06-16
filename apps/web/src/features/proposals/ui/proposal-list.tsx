"use client";

import Link from "next/link";
import { useProposals } from "@/features/proposals/api/use-proposals";
import {
  ApprovalStatusBadge,
  DeliveryStatusBadge,
  ProposalStatusBadge,
} from "@/features/proposals/ui/proposal-status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FILTER_TABS = [
  { value: undefined,            label: "All"            },
  { value: "pending_approval",   label: "Pending Review" },
  { value: "approved",           label: "Approved"       },
  { value: "rejected",           label: "Rejected"       },
] as const;

interface ProposalListProps {
  workspaceId: string;
  approvalStatus: string | undefined;
  onFilterChange: (status: string | undefined) => void;
  onGenerate: () => void;
}

export function ProposalList({
  workspaceId,
  approvalStatus,
  onFilterChange,
  onGenerate,
}: ProposalListProps) {
  const { data, isLoading, isError, refetch } = useProposals(
    workspaceId,
    approvalStatus,
  );

  const proposals = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Filter chip bar */}
      <div className="flex flex-wrap gap-2">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => onFilterChange(tab.value)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              approvalStatus === tab.value
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-transparent text-muted-foreground hover:border-foreground/30 hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="text-sm text-muted-foreground">Failed to load proposals.</p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      )}

      {!isLoading && !isError && proposals.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <p className="text-sm text-muted-foreground">
            {approvalStatus === "pending_approval"
              ? "No proposals awaiting review."
              : approvalStatus === "approved"
                ? "No approved proposals."
                : approvalStatus === "rejected"
                  ? "No rejected proposals."
                  : "No proposals yet. Generate one from an eligible CRM lead."}
          </p>
          {!approvalStatus && (
            <Button size="sm" onClick={onGenerate}>
              Generate proposal
            </Button>
          )}
        </div>
      )}

      {!isLoading && !isError && proposals.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Approval</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Delivery</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Sent</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {proposals.map((p) => (
                <tr
                  key={p.id}
                  className="transition-colors hover:bg-muted/30"
                >
                  <td className="max-w-[220px] truncate px-4 py-3 font-medium">
                    {p.title}
                  </td>
                  <td className="px-4 py-3">
                    <ApprovalStatusBadge status={p.approval_status} />
                  </td>
                  <td className="px-4 py-3">
                    <ProposalStatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-3">
                    <DeliveryStatusBadge status={p.delivery_status} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(p.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {p.sent_at ? new Date(p.sent_at).toLocaleDateString() : "—"}
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
      )}
    </div>
  );
}
