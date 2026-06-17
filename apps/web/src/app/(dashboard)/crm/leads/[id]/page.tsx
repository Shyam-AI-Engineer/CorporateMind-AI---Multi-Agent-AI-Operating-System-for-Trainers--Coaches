"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { format } from "date-fns";
import { AlertCircle, Calendar, FileText } from "lucide-react";

import {
  useAdvanceStage,
  useGetLead,
  useMarkLost,
} from "@/features/crm/api/use-leads";
import { useProposalsForContact } from "@/features/proposals/api/use-proposals";
import { ActivityTimeline } from "@/features/crm/ui/activity-timeline";
import { LeadStageTimeline } from "@/features/crm/ui/lead-stage-timeline";
import { MeetingSchedulerDialog } from "@/features/crm/ui/meeting-scheduler-dialog";
import { GenerateProposalDialog } from "@/features/proposals/ui/generate-proposal-dialog";
import {
  ApprovalStatusBadge,
  DeliveryStatusBadge,
} from "@/features/proposals/ui/proposal-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { STAGE_CONFIG, TERMINAL_STAGES } from "@/features/crm/types";
import { ApiError } from "@/lib/api";

// Human-readable advance-button labels per stage
const ADVANCE_LABELS: Record<string, string> = {
  discovered: "Mark Engaged",
  engaged: "Mark Meeting Scheduled",
  meeting_scheduled: "Mark Meeting Completed",
  meeting_completed: "Mark Booked",
};

export default function LeadDetailPage() {
  const { id: leadId } = useParams<{ id: string }>();
  const { workspaceId } = useWorkspace();
  const router = useRouter();

  const { data: lead, isLoading, isError } = useGetLead(leadId);
  const advance = useAdvanceStage(workspaceId);
  const markLost = useMarkLost(workspaceId);
  const { data: proposalList } = useProposalsForContact(
    workspaceId,
    lead?.contact_id,
  );

  const [meetingOpen, setMeetingOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="max-w-3xl space-y-4 p-6">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-32 w-full rounded-lg" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">Lead not found.</p>
        <Link
          href="/crm"
          className="mt-2 inline-block text-sm text-primary underline-offset-2 hover:underline"
        >
          Back to pipeline
        </Link>
      </div>
    );
  }

  const stageConfig = STAGE_CONFIG[lead.stage];
  const isTerminal = TERMINAL_STAGES.has(lead.stage);
  const isMeetingScheduled = lead.stage === "meeting_scheduled";
  const isMeetingCompleted = lead.stage === "meeting_completed";
  const advanceLabel = ADVANCE_LABELS[lead.stage];
  const proposals = proposalList?.items ?? [];

  async function handleAdvance() {
    setActionError(null);
    try {
      await advance.mutateAsync({ leadId: lead!.id });
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Action failed — please try again.",
      );
    }
  }

  async function handleMarkLost() {
    setActionError(null);
    try {
      await markLost.mutateAsync({ leadId: lead!.id });
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Action failed — please try again.",
      );
    }
  }

  return (
    <div className="max-w-3xl space-y-6 p-6">
      {/* Breadcrumb */}
      <div className="text-xs text-muted-foreground">
        <Link href="/crm" className="hover:underline">
          CRM Pipeline
        </Link>
        {" / "}
        <span>Lead {lead.id.slice(0, 8)}…</span>
      </div>

      {/* Stage progress */}
      <LeadStageTimeline currentStage={lead.stage} />

      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-mono text-muted-foreground">
            Contact {lead.contact_id.slice(0, 8)}…
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${stageConfig.bgClass} ${stageConfig.colorClass}`}
            >
              {stageConfig.label}
            </span>
            <Badge
              variant={
                lead.score >= 70
                  ? "success"
                  : lead.score >= 40
                    ? "warning"
                    : "destructive"
              }
              className="text-xs"
            >
              Score {lead.score}
            </Badge>
          </div>
        </div>
      </div>

      {/* Metadata grid */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border p-4 text-sm sm:grid-cols-3">
        <MetaCell label="Created">
          {format(new Date(lead.created_at), "MMM d, yyyy")}
        </MetaCell>
        <MetaCell label="Last updated">
          {format(new Date(lead.updated_at), "MMM d, yyyy")}
        </MetaCell>
        <MetaCell label="Meeting time">
          {lead.meeting_scheduled_at ? (
            <span className="flex items-center gap-1 text-violet-700">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              {format(new Date(lead.meeting_scheduled_at), "MMM d, h:mm a")}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </MetaCell>
        {lead.booked_at && (
          <MetaCell label="Booked at">
            {format(new Date(lead.booked_at), "MMM d, yyyy")}
          </MetaCell>
        )}
        {lead.notes && (
          <MetaCell label="Notes" className="col-span-2 sm:col-span-3">
            <span className="whitespace-pre-wrap text-xs text-muted-foreground">
              {lead.notes}
            </span>
          </MetaCell>
        )}
      </dl>

      {/* Action bar */}
      {!isTerminal && (
        <div className="flex flex-wrap items-center gap-3">
          {isMeetingScheduled && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setMeetingOpen(true)}
            >
              <Calendar className="mr-1.5 h-3.5 w-3.5" />
              Set meeting time
            </Button>
          )}
          {isMeetingCompleted && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setGenerateOpen(true)}
            >
              <FileText className="mr-1.5 h-3.5 w-3.5" />
              Generate proposal
            </Button>
          )}
          {advanceLabel && (
            <Button
              size="sm"
              disabled={advance.isPending}
              onClick={() => void handleAdvance()}
            >
              {advance.isPending ? "Updating…" : advanceLabel}
            </Button>
          )}
          <Button
            size="sm"
            variant="destructive"
            disabled={markLost.isPending}
            onClick={() => void handleMarkLost()}
          >
            {markLost.isPending ? "Updating…" : "Mark Lost"}
          </Button>
          {actionError && (
            <div className="flex items-center gap-1.5 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {actionError}
            </div>
          )}
        </div>
      )}

      {/* Proposal history */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Proposal history</h2>
        {proposals.length === 0 ? (
          <div className="flex h-24 flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed bg-card">
            <FileText className="h-5 w-5 text-muted-foreground/40" />
            <p className="text-xs text-muted-foreground">
              No proposals yet for this contact.
            </p>
          </div>
        ) : (
          <div className="divide-y rounded-lg border">
            {proposals.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{p.title}</p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2">
                    <ApprovalStatusBadge status={p.approval_status} />
                    <DeliveryStatusBadge status={p.delivery_status} />
                    {p.sent_at && (
                      <span className="text-xs text-muted-foreground">
                        Sent {format(new Date(p.sent_at), "MMM d")}
                      </span>
                    )}
                  </div>
                </div>
                <Link
                  href={`/proposals/${p.id}` as Route}
                  className="shrink-0 text-xs text-primary underline-offset-2 hover:underline"
                >
                  View
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Activity feed */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Activity</h2>
        <ActivityTimeline leadId={lead.id} />
      </section>

      {/* Dialogs — mounted here so they can access lead context */}
      <MeetingSchedulerDialog
        leadId={lead.id}
        workspaceId={workspaceId ?? ""}
        open={meetingOpen}
        onOpenChange={setMeetingOpen}
      />
      <GenerateProposalDialog
        workspaceId={workspaceId ?? ""}
        initialLeadId={lead.id}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onSuccess={(id) => router.push(`/proposals/${id}` as Route)}
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
