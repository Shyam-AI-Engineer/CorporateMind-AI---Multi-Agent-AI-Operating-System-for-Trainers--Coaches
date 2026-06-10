"use client";

/**
 * FollowUpList — follow-up task queue with Pending / Done / Cancelled tabs.
 *
 * Each row: task type, notes, scheduled date, status badge.
 * Empty state is shown per tab, not globally.
 *
 * States: skeleton rows (loading), per-tab empty, error + retry.
 */

import { useState } from "react";
import { format, formatDistanceToNow, isPast, parseISO } from "date-fns";
import { AlertCircle, CalendarClock, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useFollowUps } from "@/features/crm/api/use-activities";
import {
  FOLLOW_UP_STATUS_CONFIG,
  type FollowUpTask,
} from "@/features/crm/types";
import { useWorkspace } from "@/hooks/use-workspace";

const STATUS_TABS = ["pending", "done", "cancelled"] as const;
type StatusTab = (typeof STATUS_TABS)[number];

export function FollowUpList() {
  const { workspaceId } = useWorkspace();
  const [activeTab, setActiveTab] = useState<StatusTab>("pending");

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
    <Tabs
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as StatusTab)}
    >
      <TabsList>
        {STATUS_TABS.map((s) => (
          <TabsTrigger key={s} value={s}>
            {FOLLOW_UP_STATUS_CONFIG[s]?.label ?? s}
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
                <TaskRow key={task.id} task={task} />
              ))}
            </div>
          )}
        </TabsContent>
      ))}
    </Tabs>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: FollowUpTask }) {
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

  // Humanise the type string ("followup_required" → "Followup required")
  const typeLabel = task.type.replaceAll("_", " ");

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
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

function EmptyState({ status }: { status: StatusTab }) {
  const messages: Record<StatusTab, string> = {
    pending: "No pending follow-ups.",
    done: "No completed follow-ups yet.",
    cancelled: "No cancelled follow-ups.",
  };

  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-card">
      <CalendarClock className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">{messages[status]}</p>
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
