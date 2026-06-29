"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Clock, XCircle, PlayCircle, Ban } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { WorkQueueGroupItem } from "@/features/analytics/types";
import {
  useRecommendationWorkQueue,
  useStartRecommendation,
  useBlockRecommendation,
  useCompleteRecommendation,
  useCancelRecommendation,
} from "@/features/analytics/api/use-analytics";

// ── helpers ───────────────────────────────────────────────────────────────────

function elapsedDays(startedAt: string | null): number {
  if (!startedAt) return 0;
  const ms = Date.now() - new Date(startedAt).getTime();
  return Math.floor(ms / 86_400_000);
}

// ── card components ───────────────────────────────────────────────────────────

function ReadyCard({
  item,
  onStart,
}: {
  item: WorkQueueGroupItem;
  onStart: (id: string) => void;
}) {
  return (
    <Card data-testid={`ready-card-${item.recommendation_id}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm">{item.title || item.recommendation_id}</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Accepted · not started</span>
        <Button
          size="sm"
          data-testid={`start-btn-${item.recommendation_id}`}
          onClick={() => onStart(item.recommendation_id)}
        >
          <PlayCircle className="mr-1 h-3 w-3" />
          Start
        </Button>
      </CardContent>
    </Card>
  );
}

function InProgressCard({
  item,
  onComplete,
  onBlock,
}: {
  item: WorkQueueGroupItem;
  onComplete: (id: string) => void;
  onBlock: (id: string) => void;
}) {
  const days = elapsedDays(item.started_at);
  return (
    <Card data-testid={`in-progress-card-${item.recommendation_id}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm">{item.title || item.recommendation_id}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">
          Started · {days} day{days !== 1 ? "s" : ""} elapsed
        </p>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="default"
            data-testid={`complete-btn-${item.recommendation_id}`}
            onClick={() => onComplete(item.recommendation_id)}
          >
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Complete
          </Button>
          <Button
            size="sm"
            variant="outline"
            data-testid={`block-btn-${item.recommendation_id}`}
            onClick={() => onBlock(item.recommendation_id)}
          >
            <Ban className="mr-1 h-3 w-3" />
            Block
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function BlockedCard({
  item,
  onResume,
  onCancel,
}: {
  item: WorkQueueGroupItem;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  return (
    <Card data-testid={`blocked-card-${item.recommendation_id}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm">{item.title || item.recommendation_id}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {item.blocked_reason && (
          <p className="text-xs text-destructive">{item.blocked_reason}</p>
        )}
        <div className="flex gap-2">
          <Button
            size="sm"
            data-testid={`resume-btn-${item.recommendation_id}`}
            onClick={() => onResume(item.recommendation_id)}
          >
            <PlayCircle className="mr-1 h-3 w-3" />
            Resume
          </Button>
          <Button
            size="sm"
            variant="outline"
            data-testid={`cancel-from-blocked-btn-${item.recommendation_id}`}
            onClick={() => onCancel(item.recommendation_id)}
          >
            <XCircle className="mr-1 h-3 w-3" />
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CompletedCard({ item }: { item: WorkQueueGroupItem }) {
  return (
    <Card data-testid={`completed-card-${item.recommendation_id}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm">{item.title || item.recommendation_id}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">
          Completed{" "}
          {item.completed_at
            ? new Date(item.completed_at).toLocaleDateString()
            : ""}
        </p>
        {item.completion_notes && (
          <p className="mt-1 text-xs">{item.completion_notes}</p>
        )}
      </CardContent>
    </Card>
  );
}

function CancelledCard({ item }: { item: WorkQueueGroupItem }) {
  return (
    <Card data-testid={`cancelled-card-${item.recommendation_id}`}>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm">{item.title || item.recommendation_id}</CardTitle>
      </CardHeader>
      <CardContent>
        {item.blocked_reason && (
          <p className="text-xs text-muted-foreground">{item.blocked_reason}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ── dialogs ───────────────────────────────────────────────────────────────────

function BlockDialog({
  open,
  onConfirm,
  onClose,
}: {
  open: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="block-dialog">
        <DialogHeader>
          <DialogTitle>Block Recommendation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="block-reason-input">Reason (required)</Label>
          <Textarea
            id="block-reason-input"
            data-testid="block-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe what's blocking this recommendation…"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            data-testid="block-confirm-btn"
            disabled={!reason.trim()}
            onClick={() => { onConfirm(reason.trim()); setReason(""); }}
          >
            Block
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompleteDialog({
  open,
  onConfirm,
  onClose,
}: {
  open: boolean;
  onConfirm: (notes: string) => void;
  onClose: () => void;
}) {
  const [notes, setNotes] = useState("");
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="complete-dialog">
        <DialogHeader>
          <DialogTitle>Complete Recommendation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="complete-notes-input">Notes (optional)</Label>
          <Textarea
            id="complete-notes-input"
            data-testid="complete-notes-input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add any completion notes…"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            data-testid="complete-confirm-btn"
            onClick={() => { onConfirm(notes.trim()); setNotes(""); }}
          >
            Complete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelDialog({
  open,
  onConfirm,
  onClose,
}: {
  open: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="cancel-dialog">
        <DialogHeader>
          <DialogTitle>Cancel Recommendation</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="cancel-reason-input">Reason (optional)</Label>
          <Input
            id="cancel-reason-input"
            data-testid="cancel-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you cancelling this?"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Back</Button>
          <Button
            variant="destructive"
            data-testid="cancel-confirm-btn"
            onClick={() => { onConfirm(reason.trim()); setReason(""); }}
          >
            Cancel Recommendation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── timeline ──────────────────────────────────────────────────────────────────

function TimelineSection({ items }: { items: WorkQueueGroupItem[] }) {
  if (items.length === 0) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="timeline-empty"
      >
        No completed recommendations.
      </p>
    );
  }
  return (
    <ul data-testid="timeline-list" className="space-y-2">
      {items.map((item) => (
        <li
          key={item.recommendation_id}
          data-testid={`timeline-item-${item.recommendation_id}`}
          className="flex items-center gap-3 text-sm"
        >
          <Clock className="h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="font-medium">{item.title || item.recommendation_id}</span>
          <span className="text-muted-foreground">·</span>
          <span className="capitalize text-muted-foreground">
            {item.execution_status ?? "accepted"}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function RecommendationWorkQueue({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const { data, isLoading, isError } = useRecommendationWorkQueue(workspaceId);
  const startMutation = useStartRecommendation(workspaceId);
  const blockMutation = useBlockRecommendation(workspaceId);
  const completeMutation = useCompleteRecommendation(workspaceId);
  const cancelMutation = useCancelRecommendation(workspaceId);

  const [blockTarget, setBlockTarget] = useState<string | null>(null);
  const [completeTarget, setCompleteTarget] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div data-testid="work-queue-skeleton" className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div
        data-testid="work-queue-error"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load work queue. Try refreshing.
      </div>
    );
  }

  return (
    <div data-testid="recommendation-work-queue" className="space-y-8">

      {/* Section 1 — Ready */}
      <section data-testid="ready-section">
        <h3 className="mb-3 text-sm font-semibold">Ready to Start</h3>
        {data.ready.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="ready-empty">
            No work queued.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.ready.map((item) => (
              <ReadyCard
                key={item.recommendation_id}
                item={item}
                onStart={(id) => startMutation.mutate({ recommendationId: id })}
              />
            ))}
          </div>
        )}
      </section>

      {/* Section 2 — In Progress */}
      <section data-testid="in-progress-section">
        <h3 className="mb-3 text-sm font-semibold">In Progress</h3>
        {data.in_progress.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="in-progress-empty">
            Nothing in progress.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.in_progress.map((item) => (
              <InProgressCard
                key={item.recommendation_id}
                item={item}
                onComplete={(id) => setCompleteTarget(id)}
                onBlock={(id) => setBlockTarget(id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Section 3 — Blocked */}
      <section data-testid="blocked-section">
        <h3 className="mb-3 text-sm font-semibold">Blocked</h3>
        {data.blocked.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="blocked-empty">
            Nothing blocked.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.blocked.map((item) => (
              <BlockedCard
                key={item.recommendation_id}
                item={item}
                onResume={(id) => startMutation.mutate({ recommendationId: id })}
                onCancel={(id) => setCancelTarget(id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Section 4 — Completed */}
      <section data-testid="completed-section">
        <h3 className="mb-3 text-sm font-semibold">Completed</h3>
        {data.completed.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="completed-empty">
            No completed recommendations.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.completed.map((item) => (
              <CompletedCard key={item.recommendation_id} item={item} />
            ))}
          </div>
        )}
      </section>

      {/* Section 5 — Cancelled */}
      <section data-testid="cancelled-section">
        <h3 className="mb-3 text-sm font-semibold">Cancelled</h3>
        {data.cancelled.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="cancelled-empty">
            Nothing cancelled.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.cancelled.map((item) => (
              <CancelledCard key={item.recommendation_id} item={item} />
            ))}
          </div>
        )}
      </section>

      {/* Section 6 — Timeline */}
      <section data-testid="timeline-section">
        <h3 className="mb-3 text-sm font-semibold">Timeline</h3>
        <TimelineSection items={data.timeline} />
      </section>

      {/* Dialogs */}
      <BlockDialog
        open={blockTarget !== null}
        onConfirm={(reason) => {
          if (blockTarget) {
            blockMutation.mutate({ recommendationId: blockTarget, reason });
            setBlockTarget(null);
          }
        }}
        onClose={() => setBlockTarget(null)}
      />
      <CompleteDialog
        open={completeTarget !== null}
        onConfirm={(notes) => {
          if (completeTarget) {
            completeMutation.mutate({ recommendationId: completeTarget, notes });
            setCompleteTarget(null);
          }
        }}
        onClose={() => setCompleteTarget(null)}
      />
      <CancelDialog
        open={cancelTarget !== null}
        onConfirm={(reason) => {
          if (cancelTarget) {
            cancelMutation.mutate({ recommendationId: cancelTarget, reason });
            setCancelTarget(null);
          }
        }}
        onClose={() => setCancelTarget(null)}
      />
    </div>
  );
}
