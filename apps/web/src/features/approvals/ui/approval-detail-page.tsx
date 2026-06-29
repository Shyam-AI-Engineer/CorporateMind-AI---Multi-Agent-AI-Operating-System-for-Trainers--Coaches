"use client";

import { useState } from "react";
import { AlertCircle, ArrowLeft, CheckCircle, XCircle, Ban } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useApprovalDetail,
  useApprovalTimeline,
  useApproveRequest,
  useRejectRequest,
  useCancelRequest,
} from "@/features/approvals/api/use-approvals";
import type {
  ApprovalDecisionIn,
  ApprovalPriority,
  ApprovalRequestOut,
  ApprovalStatus,
  ApprovalTimelineEventOut,
} from "@/features/approvals/types";
import Link from "next/link";
import type { Route } from "next";

// ── Priority badge ────────────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: ApprovalPriority }) {
  const colors: Record<ApprovalPriority, string> = {
    low: "bg-slate-100 text-slate-600 border-slate-200",
    medium: "bg-blue-100 text-blue-700 border-blue-200",
    high: "bg-amber-100 text-amber-700 border-amber-200",
    urgent: "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <span
      data-testid={`detail-priority-badge-${priority}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[priority]}`}
    >
      {priority}
    </span>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ApprovalStatus }) {
  const colors: Record<ApprovalStatus, string> = {
    pending: "bg-amber-100 text-amber-700 border-amber-200",
    in_review: "bg-blue-100 text-blue-700 border-blue-200",
    approved: "bg-green-100 text-green-700 border-green-200",
    rejected: "bg-red-100 text-red-700 border-red-200",
    cancelled: "bg-slate-100 text-slate-500 border-slate-200",
  };
  const labels: Record<ApprovalStatus, string> = {
    pending: "Pending",
    in_review: "In Review",
    approved: "Approved",
    rejected: "Rejected",
    cancelled: "Cancelled",
  };
  return (
    <span
      data-testid={`detail-status-badge-${status}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[status]}`}
    >
      {labels[status]}
    </span>
  );
}

// ── Decision dialog ───────────────────────────────────────────────────────────

type DecisionType = "approve" | "reject";

function DecisionDialog({
  approvalId,
  workspaceId,
  type,
  onClose,
}: {
  approvalId: string;
  workspaceId: string;
  type: DecisionType;
  onClose: () => void;
}) {
  const [comments, setComments] = useState("");
  const [error, setError] = useState<string | null>(null);
  const approve = useApproveRequest(workspaceId);
  const reject = useRejectRequest(workspaceId);

  const isPending = approve.isPending || reject.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const data: ApprovalDecisionIn = { comments: comments.trim() || undefined };
    const mutation = type === "approve" ? approve : reject;
    mutation.mutate(
      { approvalId, data },
      {
        onSuccess: onClose,
        onError: (err: unknown) => {
          setError(err instanceof Error ? err.message : "Failed to submit decision");
        },
      },
    );
  };

  const title = type === "approve" ? "Approve Request" : "Reject Request";
  const buttonLabel = type === "approve" ? "Approve" : "Reject";

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`${type}-dialog`}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="decision-comments">Comments (optional)</Label>
            <textarea
              id="decision-comments"
              data-testid="decision-comments-input"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Add any notes about your decision…"
              maxLength={4000}
              rows={4}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          {error && (
            <p data-testid="decision-error" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              data-testid={`${type}-submit-btn`}
              variant={type === "reject" ? "destructive" : "default"}
              disabled={isPending}
            >
              {isPending ? "Submitting…" : buttonLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Cancel dialog ─────────────────────────────────────────────────────────────

function CancelDialog({
  approvalId,
  workspaceId,
  onClose,
}: {
  approvalId: string;
  workspaceId: string;
  onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const cancel = useCancelRequest(workspaceId);

  const handleConfirm = () => {
    cancel.mutate(approvalId, {
      onSuccess: onClose,
      onError: (err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to cancel request");
      },
    });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="cancel-dialog">
        <DialogHeader>
          <DialogTitle>Cancel Request</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Are you sure you want to cancel this approval request? This cannot be
          reversed.
        </p>
        {error && (
          <p data-testid="cancel-error" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Back
          </Button>
          <Button
            data-testid="cancel-confirm-btn"
            variant="destructive"
            onClick={handleConfirm}
            disabled={cancel.isPending}
          >
            {cancel.isPending ? "Cancelling…" : "Cancel Request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────

function eventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    request_created: "Request submitted",
    reviewer_assigned: "Reviewer assigned",
    approved: "Approved",
    rejected: "Rejected",
    cancelled: "Cancelled",
  };
  return labels[eventType] ?? eventType;
}

function ApprovalTimeline({
  events,
}: {
  events: ApprovalTimelineEventOut[];
}) {
  return (
    <div data-testid="approval-timeline" className="space-y-3">
      {events.map((event, i) => (
        <div
          key={event.id}
          data-testid={`timeline-event-${i}`}
          className="flex items-start gap-3 text-sm"
        >
          <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-primary/60 ring-2 ring-primary/20" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span
                data-testid={`timeline-event-type-${i}`}
                className="font-medium"
              >
                {eventLabel(event.event_type)}
              </span>
              <span className="text-xs text-muted-foreground">
                by <span className="font-mono">{event.actor_user_id.slice(0, 8)}</span>
              </span>
            </div>
            {event.notes && (
              <p
                data-testid={`timeline-event-notes-${i}`}
                className="mt-0.5 text-xs text-muted-foreground"
              >
                {event.notes}
              </p>
            )}
            <p className="mt-0.5 text-xs text-muted-foreground">
              {new Date(event.occurred_at).toLocaleString()}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Metadata row helper ───────────────────────────────────────────────────────

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <span className="w-32 shrink-0 text-muted-foreground">{label}</span>
      <span className="font-medium">{children}</span>
    </div>
  );
}

// ── Action buttons ────────────────────────────────────────────────────────────

function ApprovalActions({
  approval,
  workspaceId,
}: {
  approval: ApprovalRequestOut;
  workspaceId: string;
}) {
  const [dialog, setDialog] = useState<"approve" | "reject" | "cancel" | null>(null);
  const isActive = approval.status === "pending" || approval.status === "in_review";

  if (!isActive) {
    return null;
  }

  return (
    <>
      <div data-testid="approval-actions" className="flex items-center gap-2">
        <Button
          size="sm"
          data-testid="approve-btn"
          onClick={() => setDialog("approve")}
          className="gap-1"
        >
          <CheckCircle className="h-4 w-4" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="destructive"
          data-testid="reject-btn"
          onClick={() => setDialog("reject")}
          className="gap-1"
        >
          <XCircle className="h-4 w-4" />
          Reject
        </Button>
        <Button
          size="sm"
          variant="outline"
          data-testid="cancel-btn"
          onClick={() => setDialog("cancel")}
          className="gap-1 text-muted-foreground"
        >
          <Ban className="h-4 w-4" />
          Cancel
        </Button>
      </div>

      {(dialog === "approve" || dialog === "reject") && (
        <DecisionDialog
          approvalId={approval.id}
          workspaceId={workspaceId}
          type={dialog}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "cancel" && (
        <CancelDialog
          approvalId={approval.id}
          workspaceId={workspaceId}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}

// ── Main Approval Detail Page ─────────────────────────────────────────────────

interface ApprovalDetailPageProps {
  approvalId: string;
}

export function ApprovalDetailPage({ approvalId }: ApprovalDetailPageProps) {
  const { workspaceId } = useWorkspace();
  const {
    data: approval,
    isLoading: detailLoading,
    isError: detailError,
  } = useApprovalDetail(approvalId, workspaceId);
  const {
    data: timeline,
    isLoading: timelineLoading,
    isError: timelineError,
  } = useApprovalTimeline(approvalId, workspaceId);

  if (!workspaceId) {
    return (
      <div data-testid="approval-detail-no-workspace" className="text-sm text-muted-foreground">
        Select a workspace to view this approval.
      </div>
    );
  }

  if (detailLoading) {
    return (
      <div data-testid="approval-detail-skeleton" className="space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (detailError || !approval) {
    return (
      <div data-testid="approval-detail-error" className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load approval request.
      </div>
    );
  }

  return (
    <div data-testid="approval-detail-page" className="space-y-6">
      {/* Back nav */}
      <Link
        href={"/approvals" as Route}
        data-testid="back-to-approvals"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Approvals
      </Link>

      {/* Main detail card */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="text-base capitalize">
              {approval.entity_type} Request
            </CardTitle>
            <div className="flex items-center gap-2">
              <PriorityBadge priority={approval.priority} />
              <StatusBadge status={approval.status} />
            </div>
          </div>
          <ApprovalActions approval={approval} workspaceId={workspaceId} />
        </CardHeader>
        <CardContent className="space-y-3">
          <MetaRow label="Requested by">
            <span className="font-mono">{approval.requested_by}</span>
          </MetaRow>
          {approval.assigned_reviewer && (
            <MetaRow label="Reviewer">
              <span data-testid="detail-reviewer" className="font-mono">
                {approval.assigned_reviewer}
              </span>
            </MetaRow>
          )}
          {approval.entity_id && (
            <MetaRow label="Entity ID">
              <span data-testid="detail-entity-id" className="font-mono">
                {approval.entity_id}
              </span>
            </MetaRow>
          )}
          {approval.due_date && (
            <MetaRow label="Due date">
              <span data-testid="detail-due-date">
                {new Date(approval.due_date).toLocaleDateString()}
              </span>
            </MetaRow>
          )}
          {approval.comments && (
            <div className="space-y-1">
              <span className="text-sm text-muted-foreground">Comments</span>
              <p data-testid="detail-comments" className="rounded-md bg-muted/40 px-3 py-2 text-sm">
                {approval.comments}
              </p>
            </div>
          )}
          {approval.reviewed_at && (
            <MetaRow label="Reviewed">
              <span data-testid="detail-reviewed-at">
                {new Date(approval.reviewed_at).toLocaleString()}
              </span>
            </MetaRow>
          )}
        </CardContent>
      </Card>

      {/* Timeline card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Activity Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {timelineLoading ? (
            <div data-testid="timeline-skeleton" className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : timelineError ? (
            <div data-testid="timeline-error" className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              Failed to load timeline.
            </div>
          ) : (timeline ?? []).length === 0 ? (
            <p data-testid="timeline-empty" className="text-sm text-muted-foreground">
              No timeline events yet.
            </p>
          ) : (
            <ApprovalTimeline events={timeline ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
