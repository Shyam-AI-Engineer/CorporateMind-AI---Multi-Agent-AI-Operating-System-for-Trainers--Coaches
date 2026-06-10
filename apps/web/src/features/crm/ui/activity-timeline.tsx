"use client";

/**
 * ActivityTimeline — chronological CRM activity feed.
 *
 * Each row shows: activity-type icon, summary text, relative timestamp.
 * Optional leadId / contactId props scope the feed to one lead or contact;
 * workspace_id alone shows the full workspace activity stream.
 *
 * States: skeleton rows (loading), empty, error + retry.
 */

import { formatDistanceToNow, parseISO } from "date-fns";
import {
  AlertCircle,
  AlertTriangle,
  Clock,
  HelpCircle,
  Mail,
  MailX,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Activity,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivities } from "@/features/crm/api/use-activities";
import {
  ACTIVITY_CONFIG,
  type Activity as CRMActivity,
} from "@/features/crm/types";
import { useWorkspace } from "@/hooks/use-workspace";

// Map the string icon keys defined in ACTIVITY_CONFIG to Lucide components.
const ICON_MAP: Record<string, LucideIcon> = {
  "trending-up":    TrendingUp,
  "trending-down":  TrendingDown,
  "help-circle":    HelpCircle,
  "clock":          Clock,
  "mail-x":         MailX,
  "mail":           Mail,
  "alert-triangle": AlertTriangle,
};

interface ActivityTimelineProps {
  leadId?: string;
  contactId?: string;
}

export function ActivityTimeline({ leadId, contactId }: ActivityTimelineProps) {
  const { workspaceId } = useWorkspace();

  const { data, isLoading, isError, refetch } = useActivities({
    workspace_id: workspaceId ?? undefined,
    lead_id: leadId,
    contact_id: contactId,
    limit: 50,
  });

  if (!workspaceId) {
    return (
      <p className="text-sm text-muted-foreground">
        No workspace — please sign in again.
      </p>
    );
  }

  if (isLoading) return <LoadingRows />;
  if (isError) return <ErrorState onRetry={() => void refetch()} />;

  const activities = data?.items ?? [];
  if (activities.length === 0) return <EmptyState />;

  return (
    <div className="flex flex-col divide-y rounded-lg border">
      {activities.map((activity) => (
        <ActivityRow key={activity.id} activity={activity} />
      ))}
    </div>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function ActivityRow({ activity }: { activity: CRMActivity }) {
  const config = ACTIVITY_CONFIG[activity.type];
  const IconComponent = config
    ? (ICON_MAP[config.icon] ?? Activity)
    : Activity;

  const label = config?.label ?? activity.type;
  const timeAgo = formatDistanceToNow(parseISO(activity.created_at), {
    addSuffix: true,
  });

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
        <IconComponent className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {activity.summary && (
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
            {activity.summary}
          </p>
        )}
      </div>
      <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
        {timeAgo}
      </span>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="flex flex-col divide-y rounded-lg border">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-4 py-3">
          <Skeleton className="mt-0.5 h-7 w-7 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-60" />
          </div>
          <Skeleton className="h-3 w-16" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-card">
      <Activity className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">No activity yet.</p>
      <p className="text-xs text-muted-foreground/70">
        Leads and inbox replies will appear here as they happen.
      </p>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-lg border bg-card">
      <AlertCircle className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">Failed to load activity.</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Retry
      </Button>
    </div>
  );
}
