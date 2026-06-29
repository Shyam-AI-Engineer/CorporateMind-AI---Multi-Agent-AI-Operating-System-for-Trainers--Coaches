"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AlertCircle, CheckCircle2, Send, XCircle } from "lucide-react";
import {
  useApproveProposal,
  useDeliverProposal,
  useProposal,
} from "@/features/proposals/api/use-proposals";
import {
  ApprovalStatusBadge,
  ClientStatusBadge,
  DeliveryStatusBadge,
  ProposalStatusBadge,
} from "@/features/proposals/ui/proposal-status-badge";
import { ProposalContentView } from "@/features/proposals/ui/proposal-content-view";
import { ProposalRejectDialog } from "@/features/proposals/ui/proposal-reject-dialog";
import { AcceptProposalDialog } from "@/features/proposals/ui/accept-proposal-dialog";
import { DeclineProposalDialog } from "@/features/proposals/ui/decline-proposal-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import { ApiError } from "@/lib/api";

function formatInr(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

export default function ProposalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { workspaceId } = useWorkspace();
  const { data: proposal, isLoading, isError } = useProposal(id);
  const approve = useApproveProposal(workspaceId);
  const deliver = useDeliverProposal(workspaceId);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [deliverError, setDeliverError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="max-w-3xl space-y-4 p-6">
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

  const isPendingApproval = proposal.approval_status === "pending_approval";
  const isApprovedDraft =
    proposal.approval_status === "approved" && proposal.status === "draft";
  const isRejected = proposal.approval_status === "rejected";
  const isDeliveryBlocked = proposal.delivery_status === "blocked";
  const isSentAwaitingResponse =
    proposal.status === "sent" && proposal.client_status === null;
  const isAccepted = proposal.client_status === "accepted";
  const isDeclined = proposal.client_status === "declined";

  async function handleApprove() {
    setApproveError(null);
    try {
      await approve.mutateAsync(proposal!.id);
    } catch (err) {
      setApproveError(
        err instanceof ApiError ? err.message : "Approval failed — please try again.",
      );
    }
  }

  async function handleDeliver() {
    setDeliverError(null);
    try {
      await deliver.mutateAsync(proposal!.id);
    } catch (err) {
      setDeliverError(
        err instanceof ApiError
          ? err.message
          : "Delivery failed — please try again.",
      );
    }
  }

  return (
    <div className="max-w-3xl space-y-6 p-6">
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
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold leading-snug">{proposal.title}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Contact {proposal.contact_id.slice(0, 8)}…
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ProposalStatusBadge status={proposal.status} />
          <ApprovalStatusBadge status={proposal.approval_status} />
          <ClientStatusBadge status={proposal.client_status} />
        </div>
      </div>

      {/* Metadata grid */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border p-4 text-sm sm:grid-cols-3">
        <MetaCell label="Approval">
          <ApprovalStatusBadge status={proposal.approval_status} />
        </MetaCell>
        <MetaCell label="Delivery">
          <DeliveryStatusBadge status={proposal.delivery_status} />
        </MetaCell>
        <MetaCell label="Client response">
          <ClientStatusBadge status={proposal.client_status} />
          {!proposal.client_status && (
            <span className="text-muted-foreground">—</span>
          )}
        </MetaCell>
        <MetaCell label="Created">
          {new Date(proposal.created_at).toLocaleString()}
        </MetaCell>
        <MetaCell label="Sent at">
          {proposal.sent_at ? new Date(proposal.sent_at).toLocaleString() : "—"}
        </MetaCell>
        {proposal.approved_at && (
          <MetaCell label="Approved at">
            {new Date(proposal.approved_at).toLocaleString()}
          </MetaCell>
        )}
        {proposal.approved_by && (
          <MetaCell label="Approved by">
            {proposal.approved_by.slice(0, 8)}…
          </MetaCell>
        )}
        {isRejected && proposal.rejected_reason && (
          <MetaCell label="Rejection reason" className="col-span-2 sm:col-span-3">
            <span className="text-destructive">{proposal.rejected_reason}</span>
          </MetaCell>
        )}
        {proposal.expected_value_inr !== null && proposal.expected_value_inr !== undefined && (
          <MetaCell label="Expected value">
            {formatInr(proposal.expected_value_inr)}
          </MetaCell>
        )}
        {proposal.actual_value_inr !== null && proposal.actual_value_inr !== undefined && (
          <MetaCell label="Deal value">
            <span className="text-green-700 dark:text-green-400">
              {formatInr(proposal.actual_value_inr)}
            </span>
          </MetaCell>
        )}
        {proposal.client_accepted_at && (
          <MetaCell label="Accepted at">
            {new Date(proposal.client_accepted_at).toLocaleString()}
          </MetaCell>
        )}
        {proposal.client_declined_at && (
          <MetaCell label="Declined at">
            {new Date(proposal.client_declined_at).toLocaleString()}
          </MetaCell>
        )}
      </dl>

      {/* Compliance block callout */}
      {isDeliveryBlocked && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Delivery blocked by compliance</p>
            <p className="mt-0.5 text-xs">
              This proposal was flagged before sending. Contact your compliance
              administrator for details.
            </p>
          </div>
        </div>
      )}

      {/* Accepted callout */}
      {isAccepted && (
        <div className="flex items-start gap-2 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Client accepted this proposal</p>
            {proposal.actual_value_inr !== null && proposal.actual_value_inr !== undefined && (
              <p className="mt-0.5 text-xs">
                Deal value: {formatInr(proposal.actual_value_inr)}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Declined callout */}
      {isDeclined && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Client declined this proposal</p>
            <p className="mt-0.5 text-xs">No further actions are available.</p>
          </div>
        </div>
      )}

      {/* Action bar — internal approval */}
      {isPendingApproval && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            disabled={approve.isPending}
            onClick={() => void handleApprove()}
          >
            {approve.isPending ? "Approving…" : "Approve"}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={approve.isPending}
            onClick={() => setRejectOpen(true)}
          >
            Reject
          </Button>
          {approveError && (
            <p className="text-xs text-destructive">{approveError}</p>
          )}
        </div>
      )}

      {/* Action bar — send */}
      {isApprovedDraft && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            disabled={deliver.isPending}
            onClick={() => void handleDeliver()}
          >
            <Send className="mr-1.5 h-3.5 w-3.5" />
            {deliver.isPending ? "Sending…" : "Send proposal"}
          </Button>
          {deliverError && (
            <p className="text-xs text-destructive">{deliverError}</p>
          )}
        </div>
      )}

      {/* Action bar — client response (sent, awaiting) */}
      {isSentAwaitingResponse && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            onClick={() => setAcceptOpen(true)}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            Record Acceptance
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setDeclineOpen(true)}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5" />
            Record Decline
          </Button>
        </div>
      )}

      {/* Proposal content */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold">Proposal content</h2>
        <ProposalContentView proposal={proposal} />
      </div>

      {/* Dialogs */}
      <ProposalRejectDialog
        proposalId={proposal.id}
        workspaceId={workspaceId}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
      />
      <AcceptProposalDialog
        proposalId={proposal.id}
        workspaceId={workspaceId}
        open={acceptOpen}
        onOpenChange={setAcceptOpen}
      />
      <DeclineProposalDialog
        proposalId={proposal.id}
        workspaceId={workspaceId}
        open={declineOpen}
        onOpenChange={setDeclineOpen}
      />
    </div>
  );
}

function MetaCell({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-medium">{children}</dd>
    </div>
  );
}
