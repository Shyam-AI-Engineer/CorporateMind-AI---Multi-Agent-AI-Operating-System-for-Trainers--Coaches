"use client";

/**
 * FollowUpList — follow-up task queue with status tabs.
 *
 * Tabs: (Needs review) · Pending · Done · Cancelled. The "Needs review" tab
 * (awaiting_approval) is gated by the FOLLOWUP_APPROVAL_ENABLED flag (Sprint 8C);
 * its rows open the review dialog (approve / edit / reject). The other tabs stay
 * read-only.
 *
 * States: skeleton rows (loading), per-tab empty, error + retry.
 */

import { useState } from "react";
import { format, formatDistanceToNow, isPast, parseISO } from "date-fns";
import { AlertCircle, CalendarClock, ChevronRight, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useFollowUps } from "@/features/crm/api/use-activities";
import { ApprovalCountBadge } from "@/features/crm/ui/approval-count-badge";
import { FollowupReviewDialog } from "@/features/crm/ui/followup-review-dialog";
import {
  FOLLOW_UP_STATUS_CONFIG,
  type FollowUpTask,
} from "@/features/crm/types";
import { useWorkspace } from "@/hooks/use-workspace";
import { FOLLOWUP_APPROVAL_ENABLED } from "@/lib/flags";

const STATUS_TABS: string[] = FOLLOWUP_APPROVAL_ENABLED
  ? ["awaiting_approval", "pending", "done", "cancelled"]
  : ["pending", "done", "cancelled"];

const DEFAULT_TAB = FOLLOWUP_APPROVAL_ENABLED ? "awaiting_approval" : "pending";

export function FollowUpList() {
  const { workspaceId } = useWorkspace();
  const [activeTab, setActiveTab] = useState<string>(DEFAULT_TAB);
  const [reviewTaskId, setReviewTaskId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useFollowUps({
    workspace_id: workspaceId,
    status: activeTab,
    limit: 50,
  });

  if (!workspaceId) {
    return (
      <p className="text-sm text-muted-foreground">
        No workspace — please sign in again.
      </p>
    );
  }

  const tasks = data?.items ?? [];

  return (
    <>
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v)}>
        <TabsList>
          {STATUS_TABS.map((s) => (
            <TabsTrigger key={s} value={s} className="gap-1.5">
              {FOLLOW_UP_STATUS_CONFIG[s]?.label ?? s}
              {s === "awaiting_approval" && <ApprovalCountBadge />}
            </TabsTrigger>
          ))}
        </TabsList>

        {STATUS_TABS.map((s) => (
          <TabsContent key={s} value={s}>
            {isLoading ? (
              <LoadingRows />
            ) : isError ? (
              <ErrorState onRetry={() => void refetch()} />
            ) : tasks.length === 0 ? (
              <EmptyState status={s} />
            ) : (
              <div className="flex flex-col divide-y rounded-lg border">
                {tasks.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    onReview={
                      s === "awaiting_approval"
                        ? () => setReviewTaskId(task.id)
                        : undefined
                    }
                  />
                ))}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>

      {FOLLOWUP_APPROVAL_ENABLED && (
        <FollowupReviewDialog
          taskId={reviewTaskId}
          open={reviewTaskId !== null}
          onOpenChange={(o) => {
            if (!o) setReviewTaskId(null);
          }}
        />
      )}
    </>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function TaskRow({
  task,
  onReview,
}: {
  task: FollowUpTask;
  onReview?: () => void;
}) {
  const statusConfig = FOLLOW_UP_STATUS_CONFIG[task.status] ?? {
    label: task.status,
    variant: "outline" as const,
  };

  let scheduledDisplay: string | null = null;
  if (task.scheduled_for) {
    const date = parseISO(task.scheduled_for);
    const relative = formatDistanceToNow(date, { addSuffix: true });
    const absolute = format(date, "d MMM yyyy, HH:mm");
    const overdue = isPast(date) && task.status === "pending";
    scheduledDisplay = overdue
      ? `Overdue · ${absolute}`
      : `${absolute} (${relative})`;
  }

  const typeLabel = task.type.replaceAll("_", " ");

  const inner = (
    <>
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
        <CalendarClock className="h-3.5 w-3.5 text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium capitalize text-foreground">
            {typeLabel}
          </p>
          <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
        </div>
        {task.notes && (
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
            {task.notes}
          </p>
        )}
        {scheduledDisplay && (
          <p
            className={[
              "mt-1 text-xs",
              task.status === "pending" &&
              task.scheduled_for &&
              isPast(parseISO(task.scheduled_for))
                ? "text-destructive"
                : "text-muted-foreground",
            ].join(" ")}
          >
            {scheduledDisplay}
          </p>
        )}
      </div>
      {onReview && (
        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
      )}
    </>
  );

  if (onReview) {
    return (
      <button
        type="button"
        onClick={onReview}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
      >
        {inner}
      </button>
    );
  }

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
      {inner}
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="flex flex-col divide-y rounded-lg border">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-4 py-3">
          <Skeleton className="mt-0.5 h-7 w-7 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
            <Skeleton className="h-3 w-48" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ status }: { status: string }) {
  const messages: Record<string, string> = {
    awaiting_approval: "Nothing to review — follow-ups needing approval appear here.",
    pending: "No pending follow-ups.",
    done: "No completed follow-ups yet.",
    cancelled: "No cancelled follow-ups.",
  };

  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-card">
      <CalendarClock className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">
        {messages[status] ?? "No follow-ups."}
      </p>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-3 rounded-lg border bg-card">
      <AlertCircle className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">
        Failed to load follow-ups.
      </p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Retry
      </Button>
    </div>
  );
}
