"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useRecommendationActions,
  useAcceptRecommendation,
  useDismissRecommendation,
  useSnoozeRecommendation,
} from "@/features/analytics/api/use-analytics";
import type { RecommendationAction } from "@/features/analytics/types";

interface Props {
  workspaceId: string;
}

function fmt(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString();
}

function StatusBadge({ status }: { status: string }) {
  const colours: Record<string, string> = {
    accepted: "bg-green-100 text-green-800",
    dismissed: "bg-gray-100 text-gray-700",
    snoozed: "bg-yellow-100 text-yellow-800",
    completed: "bg-blue-100 text-blue-800",
    expired: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${colours[status] ?? "bg-gray-100 text-gray-700"}`}
    >
      {status}
    </span>
  );
}

function DismissDialog({
  open,
  onClose,
  onConfirm,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
  loading: boolean;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="dismiss-dialog">
        <DialogHeader>
          <DialogTitle>Dismiss recommendation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="dismiss-reason">Reason (optional)</Label>
          <Input
            id="dismiss-reason"
            data-testid="dismiss-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you dismissing this?"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            data-testid="dismiss-confirm-btn"
            onClick={() => onConfirm(reason)}
            disabled={loading}
          >
            Dismiss
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SnoozeDialog({
  open,
  onClose,
  onConfirm,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (until: string) => void;
  loading: boolean;
}) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const [until, setUntil] = useState(tomorrow.toISOString().slice(0, 10));
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="snooze-dialog">
        <DialogHeader>
          <DialogTitle>Snooze recommendation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="snooze-until">Resume on</Label>
          <Input
            id="snooze-until"
            data-testid="snooze-until-input"
            type="date"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            data-testid="snooze-confirm-btn"
            onClick={() => onConfirm(until)}
            disabled={loading}
          >
            Snooze
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PendingCard({
  rec,
  onAccept,
  onDismiss,
  onSnooze,
}: {
  rec: RecommendationAction;
  onAccept: () => void;
  onDismiss: () => void;
  onSnooze: () => void;
}) {
  return (
    <div
      className="rounded-lg border bg-card p-4 space-y-3"
      data-testid={`pending-card-${rec.recommendation_id}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">
          Recommendation ID
        </span>
        <span className="font-mono text-xs">{rec.recommendation_id.slice(0, 8)}…</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm">Type</span>
        <StatusBadge status={rec.action_type} />
      </div>
      <div className="flex gap-2 pt-1">
        <Button
          size="sm"
          data-testid={`accept-btn-${rec.recommendation_id}`}
          onClick={onAccept}
        >
          Accept
        </Button>
        <Button
          size="sm"
          variant="outline"
          data-testid={`dismiss-btn-${rec.recommendation_id}`}
          onClick={onDismiss}
        >
          Dismiss
        </Button>
        <Button
          size="sm"
          variant="ghost"
          data-testid={`snooze-btn-${rec.recommendation_id}`}
          onClick={onSnooze}
        >
          Snooze
        </Button>
      </div>
    </div>
  );
}

function ActionRow({ row }: { row: RecommendationAction }) {
  return (
    <tr data-testid={`action-row-${row.recommendation_id}`} className="border-b">
      <td className="py-2 px-3 font-mono text-xs">{row.recommendation_id.slice(0, 8)}…</td>
      <td className="py-2 px-3">
        <StatusBadge status={row.status} />
      </td>
      <td className="py-2 px-3 text-sm text-muted-foreground">{row.reason ?? "—"}</td>
      <td className="py-2 px-3 text-sm">{fmt(row.snooze_until)}</td>
      <td className="py-2 px-3 text-sm">{fmt(row.updated_at)}</td>
    </tr>
  );
}

export function RecommendationActionCenter({ workspaceId }: Props) {
  const { data, isLoading, isError } = useRecommendationActions(workspaceId);
  const acceptMutation = useAcceptRecommendation(workspaceId);
  const dismissMutation = useDismissRecommendation(workspaceId);
  const snoozeMutation = useSnoozeRecommendation(workspaceId);

  const [dismissTarget, setDismissTarget] = useState<string | null>(null);
  const [snoozeTarget, setSnoozeTarget] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div data-testid="action-center-skeleton" className="space-y-3 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-lg bg-muted" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="action-center-error" className="rounded-lg border border-destructive p-4">
        <p className="text-sm text-destructive">Failed to load recommendation actions.</p>
      </div>
    );
  }

  const accepted = data?.accepted ?? [];
  const dismissed = data?.dismissed ?? [];
  const snoozed = data?.snoozed ?? [];
  const completed = data?.completed ?? [];
  const expired = data?.expired ?? [];

  // Items the trainer hasn't acted on yet — show expired (snoozed past due) as pending again
  const pending = [...expired];

  const timeline = [
    ...accepted.map((r) => ({ ...r, _ts: r.updated_at })),
    ...dismissed.map((r) => ({ ...r, _ts: r.updated_at })),
    ...completed.map((r) => ({ ...r, _ts: r.updated_at })),
    ...expired.map((r) => ({ ...r, _ts: r.updated_at })),
  ].sort((a, b) => new Date(b._ts).getTime() - new Date(a._ts).getTime());

  return (
    <div data-testid="recommendation-action-center" className="space-y-8">
      {/* Section 1 — Pending */}
      <section data-testid="pending-section">
        <h3 className="mb-3 text-base font-semibold">Pending Recommendations</h3>
        {pending.length === 0 ? (
          <p data-testid="pending-empty" className="text-sm text-muted-foreground">
            No pending recommendations.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pending.map((rec) => (
              <PendingCard
                key={rec.recommendation_id}
                rec={rec}
                onAccept={() =>
                  acceptMutation.mutate(rec.recommendation_id)
                }
                onDismiss={() => setDismissTarget(rec.recommendation_id)}
                onSnooze={() => setSnoozeTarget(rec.recommendation_id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Section 2 — Accepted */}
      <section data-testid="accepted-section">
        <h3 className="mb-3 text-base font-semibold">Accepted</h3>
        {accepted.length === 0 ? (
          <p data-testid="accepted-empty" className="text-sm text-muted-foreground">
            No accepted recommendations.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="accepted-table">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium">Recommendation</th>
                  <th className="py-2 px-3 text-left font-medium">Status</th>
                  <th className="py-2 px-3 text-left font-medium">Reason</th>
                  <th className="py-2 px-3 text-left font-medium">Resume</th>
                  <th className="py-2 px-3 text-left font-medium">Accepted</th>
                </tr>
              </thead>
              <tbody>
                {accepted.map((r) => (
                  <ActionRow key={r.id} row={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 3 — Dismissed */}
      <section data-testid="dismissed-section">
        <h3 className="mb-3 text-base font-semibold">Dismissed</h3>
        {dismissed.length === 0 ? (
          <p data-testid="dismissed-empty" className="text-sm text-muted-foreground">
            No dismissed recommendations.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="dismissed-table">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium">Recommendation</th>
                  <th className="py-2 px-3 text-left font-medium">Status</th>
                  <th className="py-2 px-3 text-left font-medium">Reason</th>
                  <th className="py-2 px-3 text-left font-medium">Resume</th>
                  <th className="py-2 px-3 text-left font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {dismissed.map((r) => (
                  <ActionRow key={r.id} row={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 4 — Snoozed */}
      <section data-testid="snoozed-section">
        <h3 className="mb-3 text-base font-semibold">Snoozed</h3>
        {snoozed.length === 0 ? (
          <p data-testid="snoozed-empty" className="text-sm text-muted-foreground">
            No snoozed recommendations.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="snoozed-table">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium">Recommendation</th>
                  <th className="py-2 px-3 text-left font-medium">Status</th>
                  <th className="py-2 px-3 text-left font-medium">Reason</th>
                  <th className="py-2 px-3 text-left font-medium">Resume Date</th>
                  <th className="py-2 px-3 text-left font-medium">Snoozed</th>
                </tr>
              </thead>
              <tbody>
                {snoozed.map((r) => (
                  <ActionRow key={r.id} row={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 5 — Activity Timeline */}
      <section data-testid="timeline-section">
        <h3 className="mb-3 text-base font-semibold">Activity Timeline</h3>
        {timeline.length === 0 ? (
          <p data-testid="timeline-empty" className="text-sm text-muted-foreground">
            No activity yet.
          </p>
        ) : (
          <ol data-testid="timeline-list" className="space-y-2">
            {timeline.map((item) => (
              <li
                key={item.id}
                data-testid={`timeline-item-${item.id}`}
                className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm"
              >
                <StatusBadge status={item.status} />
                <span className="font-mono text-xs text-muted-foreground">
                  {item.recommendation_id.slice(0, 8)}…
                </span>
                <span className="ml-auto text-xs text-muted-foreground">{fmt(item._ts)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {/* Dialogs */}
      <DismissDialog
        open={!!dismissTarget}
        onClose={() => setDismissTarget(null)}
        loading={dismissMutation.isPending}
        onConfirm={(reason) => {
          if (!dismissTarget) return;
          dismissMutation.mutate(
            { recommendationId: dismissTarget, reason },
            { onSuccess: () => setDismissTarget(null) },
          );
        }}
      />
      <SnoozeDialog
        open={!!snoozeTarget}
        onClose={() => setSnoozeTarget(null)}
        loading={snoozeMutation.isPending}
        onConfirm={(until) => {
          if (!snoozeTarget) return;
          snoozeMutation.mutate(
            { recommendationId: snoozeTarget, until },
            { onSuccess: () => setSnoozeTarget(null) },
          );
        }}
      />
    </div>
  );
}
