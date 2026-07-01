"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useWorkflowRuns,
  useWorkflowRun,
  useCancelRun,
  useCompleteStep,
  useReopenStep,
  useSkipStep,
  useBlockStep,
  useResumeStep,
  useAttachEntity,
  useDetachEntity,
  useEntityRuns,
} from "@/features/workflows/api/use-workflows";
import type {
  EntityType,
  RunStatus,
  StepRunStatus,
  WorkflowRunOut,
  WorkflowRunStepOut,
} from "@/features/workflows/types";
import {
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  SkipForward,
  RotateCcw,
  Play,
  Ban,
  ChevronRight,
  Link2,
  Link2Off,
  ExternalLink,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Status badge helpers ──────────────────────────────────────────────────────

function RunStatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
    active: { label: "Active", variant: "default" },
    completed: { label: "Completed", variant: "secondary" },
    cancelled: { label: "Cancelled", variant: "destructive" },
    pending: { label: "Pending", variant: "outline" },
  };
  const { label, variant } = map[status] ?? { label: status, variant: "outline" };
  return <Badge variant={variant}>{label}</Badge>;
}

function StepStatusIcon({ status }: { status: StepRunStatus }) {
  const icons: Record<StepRunStatus, React.ReactNode> = {
    completed: <CheckCircle2 className="h-4 w-4 text-green-600" />,
    skipped: <SkipForward className="h-4 w-4 text-muted-foreground" />,
    blocked: <AlertCircle className="h-4 w-4 text-destructive" />,
    in_progress: <Play className="h-4 w-4 text-blue-600" />,
    pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  };
  return <>{icons[status] ?? <Clock className="h-4 w-4" />}</>;
}

// ── Step action dialog ────────────────────────────────────────────────────────

interface StepActionDialogProps {
  step: WorkflowRunStepOut;
  workspaceId: string;
  runId: string;
  open: boolean;
  onClose: () => void;
}

function StepActionDialog({
  step,
  workspaceId,
  runId,
  open,
  onClose,
}: StepActionDialogProps) {
  const [notes, setNotes] = useState("");
  const complete = useCompleteStep(workspaceId, runId);
  const reopen = useReopenStep(workspaceId, runId);
  const skip = useSkipStep(workspaceId, runId);
  const block = useBlockStep(workspaceId, runId);
  const resume = useResumeStep(workspaceId, runId);

  const isPending = complete.isPending || reopen.isPending || skip.isPending || block.isPending || resume.isPending;

  function handleAction(action: "complete" | "reopen" | "skip" | "block" | "resume") {
    const onSuccess = () => { onClose(); setNotes(""); };
    switch (action) {
      case "complete":
        complete.mutate({ stepId: step.id, data: { notes: notes || null } }, { onSuccess });
        break;
      case "reopen":
        reopen.mutate(step.id, { onSuccess });
        break;
      case "skip":
        skip.mutate({ stepId: step.id, data: { notes: notes || null } }, { onSuccess });
        break;
      case "block":
        block.mutate({ stepId: step.id, data: { notes: notes || null } }, { onSuccess });
        break;
      case "resume":
        resume.mutate(step.id, { onSuccess });
        break;
    }
  }

  const canComplete = step.status === "pending" || step.status === "in_progress";
  const canReopen = step.status === "completed";
  const canSkip = !step.required && (step.status === "pending" || step.status === "in_progress");
  const canBlock = step.status === "pending" || step.status === "in_progress";
  const canResume = step.status === "blocked";

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="step-action-dialog">
        <DialogHeader>
          <DialogTitle>{step.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <StepStatusIcon status={step.status} />
            <span className="capitalize">{step.status.replace("_", " ")}</span>
            {step.required && <Badge variant="outline" className="text-xs">Required</Badge>}
          </div>
          {step.notes && (
            <p className="rounded-md bg-muted p-2 text-sm">{step.notes}</p>
          )}
          <Textarea
            placeholder="Add notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            disabled={isPending}
            data-testid="step-notes-input"
          />
        </div>
        <DialogFooter className="flex flex-wrap gap-2">
          {canComplete && (
            <Button
              onClick={() => handleAction("complete")}
              disabled={isPending}
              data-testid="btn-complete"
            >
              <CheckCircle2 className="mr-1 h-4 w-4" />
              Complete
            </Button>
          )}
          {canReopen && (
            <Button
              variant="outline"
              onClick={() => handleAction("reopen")}
              disabled={isPending}
              data-testid="btn-reopen"
            >
              <RotateCcw className="mr-1 h-4 w-4" />
              Reopen
            </Button>
          )}
          {canSkip && (
            <Button
              variant="outline"
              onClick={() => handleAction("skip")}
              disabled={isPending}
              data-testid="btn-skip"
            >
              <SkipForward className="mr-1 h-4 w-4" />
              Skip
            </Button>
          )}
          {canBlock && (
            <Button
              variant="outline"
              onClick={() => handleAction("block")}
              disabled={isPending}
              data-testid="btn-block"
            >
              <AlertCircle className="mr-1 h-4 w-4" />
              Block
            </Button>
          )}
          {canResume && (
            <Button
              onClick={() => handleAction("resume")}
              disabled={isPending}
              data-testid="btn-resume"
            >
              <Play className="mr-1 h-4 w-4" />
              Resume
            </Button>
          )}
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Attach entity dialog — Sprint 35 ─────────────────────────────────────────

const ENTITY_TYPE_OPTIONS: { value: EntityType; label: string }[] = [
  { value: "lead", label: "Lead" },
  { value: "proposal", label: "Proposal" },
  { value: "campaign", label: "Campaign" },
  { value: "customer", label: "Customer" },
  { value: "training", label: "Training" },
  { value: "other", label: "Other" },
];

interface AttachEntityDialogProps {
  workspaceId: string;
  runId: string;
  open: boolean;
  onClose: () => void;
}

function AttachEntityDialog({ workspaceId, runId, open, onClose }: AttachEntityDialogProps) {
  const [entityType, setEntityType] = useState<EntityType>("lead");
  const [entityId, setEntityId] = useState("");
  const [entityTitle, setEntityTitle] = useState("");
  const attach = useAttachEntity(workspaceId, runId);

  const canSubmit = entityId.trim().length > 0 && entityTitle.trim().length > 0;

  function handleConfirm() {
    if (!canSubmit) return;
    attach.mutate(
      { entity_type: entityType, entity_id: entityId.trim(), entity_title: entityTitle.trim() },
      {
        onSuccess: () => {
          onClose();
          setEntityId("");
          setEntityTitle("");
          setEntityType("lead");
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="attach-entity-dialog">
        <DialogHeader>
          <DialogTitle>Link to Business Entity</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium">Entity Type</label>
            <select
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={entityType}
              onChange={(e) => setEntityType(e.target.value as EntityType)}
              disabled={attach.isPending}
              data-testid="entity-type-select"
            >
              {ENTITY_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Entity ID</label>
            <input
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="UUID of the entity"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              disabled={attach.isPending}
              data-testid="entity-id-input"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Entity Title</label>
            <input
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Display name for this entity"
              value={entityTitle}
              onChange={(e) => setEntityTitle(e.target.value)}
              disabled={attach.isPending}
              data-testid="entity-title-input"
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={handleConfirm}
            disabled={!canSubmit || attach.isPending}
            data-testid="btn-attach-confirm"
          >
            <Link2 className="mr-1 h-4 w-4" />
            Link Entity
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={attach.isPending}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Detach entity dialog — Sprint 35 ─────────────────────────────────────────

interface DetachEntityDialogProps {
  workspaceId: string;
  runId: string;
  entityTitle: string;
  open: boolean;
  onClose: () => void;
}

function DetachEntityDialog({
  workspaceId,
  runId,
  entityTitle,
  open,
  onClose,
}: DetachEntityDialogProps) {
  const detach = useDetachEntity(workspaceId, runId);

  function handleConfirm() {
    detach.mutate(undefined, { onSuccess: onClose });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="detach-entity-dialog">
        <DialogHeader>
          <DialogTitle>Unlink from Entity</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Remove the link between this workflow run and{" "}
          <span className="font-medium text-foreground">"{entityTitle}"</span>?
          The run will continue but will no longer be associated with this entity.
        </p>
        <DialogFooter>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={detach.isPending}
            data-testid="btn-detach-confirm"
          >
            <Link2Off className="mr-1 h-4 w-4" />
            Unlink
          </Button>
          <Button variant="ghost" onClick={onClose} disabled={detach.isPending}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Entity workflow history panel — Sprint 35 ─────────────────────────────────

interface EntityWorkflowHistoryPanelProps {
  workspaceId: string;
  entityType: EntityType;
  entityId: string;
  currentRunId: string;
  onSelectRun: (runId: string) => void;
}

function EntityWorkflowHistoryPanel({
  workspaceId,
  entityType,
  entityId,
  currentRunId,
  onSelectRun,
}: EntityWorkflowHistoryPanelProps) {
  const { data, isLoading } = useEntityRuns(workspaceId, entityType, entityId);

  return (
    <div
      className="rounded-lg border p-4 space-y-3"
      data-testid="entity-history-panel"
    >
      <div className="flex items-center gap-2">
        <History className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Run History for this Entity</span>
      </div>

      {isLoading && (
        <p className="text-xs text-muted-foreground" data-testid="entity-history-loading">
          Loading history…
        </p>
      )}

      {!isLoading && data?.items.length === 0 && (
        <p className="text-xs text-muted-foreground" data-testid="entity-history-empty">
          No other runs for this entity.
        </p>
      )}

      {data?.items
        .filter((r) => r.id !== currentRunId)
        .map((run) => {
          const duration =
            run.completed_at || run.cancelled_at
              ? Math.round(
                  (new Date(run.completed_at ?? run.cancelled_at!).getTime() -
                    new Date(run.started_at).getTime()) /
                    60000,
                )
              : null;

          return (
            <button
              key={run.id}
              className="flex w-full items-center gap-3 rounded-md border p-3 text-left hover:bg-accent text-sm"
              onClick={() => onSelectRun(run.id)}
              data-testid={`entity-history-run-${run.id}`}
            >
              <RunStatusBadge status={run.status} />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{run.title}</p>
                <p className="text-xs text-muted-foreground">
                  Started {new Date(run.started_at).toLocaleDateString()}
                  {duration !== null && ` · ${duration}m`}
                </p>
              </div>
              <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
            </button>
          );
        })}
    </div>
  );
}

// ── Business context section — Sprint 35 ─────────────────────────────────────

interface BusinessContextSectionProps {
  run: WorkflowRunOut;
  workspaceId: string;
}

function BusinessContextSection({ run, workspaceId }: BusinessContextSectionProps) {
  const [showAttach, setShowAttach] = useState(false);
  const [showDetach, setShowDetach] = useState(false);
  const canModify = run.status === "active" || run.status === "pending";

  return (
    <div
      className="rounded-lg border p-4 space-y-3"
      data-testid="business-context-section"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Business Context</span>
        {canModify && !run.entity_type && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowAttach(true)}
            data-testid="btn-attach-entity"
          >
            <Link2 className="mr-1 h-3.5 w-3.5" />
            Link Entity
          </Button>
        )}
      </div>

      {run.entity_type ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="capitalize" data-testid="entity-type-badge">
              {run.entity_type}
            </Badge>
            <span className="text-sm font-medium" data-testid="entity-title-text">
              {run.entity_title}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              asChild
              data-testid="btn-open-entity"
            >
              <a href={`/${run.entity_type}s/${run.entity_id}`}>
                <ExternalLink className="mr-1 h-3.5 w-3.5" />
                Open {run.entity_type}
              </a>
            </Button>
            {canModify && (
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => setShowDetach(true)}
                data-testid="btn-detach-entity"
              >
                <Link2Off className="mr-1 h-3.5 w-3.5" />
                Unlink
              </Button>
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No entity linked to this run.</p>
      )}

      {showAttach && (
        <AttachEntityDialog
          workspaceId={workspaceId}
          runId={run.id}
          open={showAttach}
          onClose={() => setShowAttach(false)}
        />
      )}
      {showDetach && run.entity_title && (
        <DetachEntityDialog
          workspaceId={workspaceId}
          runId={run.id}
          entityTitle={run.entity_title}
          open={showDetach}
          onClose={() => setShowDetach(false)}
        />
      )}
    </div>
  );
}

// ── Run detail view ───────────────────────────────────────────────────────────

interface RunDetailProps {
  runId: string;
  workspaceId: string;
  onBack: () => void;
}

function RunDetail({ runId, workspaceId, onBack }: RunDetailProps) {
  const { data: run, isLoading, error } = useWorkflowRun(runId);
  const cancel = useCancelRun(workspaceId);
  const [selectedStep, setSelectedStep] = useState<WorkflowRunStepOut | null>(null);
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(null);

  if (selectedHistoryRunId) {
    return (
      <RunDetail
        runId={selectedHistoryRunId}
        workspaceId={workspaceId}
        onBack={() => setSelectedHistoryRunId(null)}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground" data-testid="run-detail-loading">
        Loading run…
      </div>
    );
  }
  if (error || !run) {
    return (
      <div className="p-6 text-sm text-destructive" data-testid="run-detail-error">
        Failed to load run.
      </div>
    );
  }

  const canCancel = run.status === "active" || run.status === "pending";
  const isImmutable = run.status === "completed" || run.status === "cancelled";

  return (
    <div className="space-y-4 p-6" data-testid="run-detail">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={onBack}
            className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            data-testid="btn-back"
          >
            ← Back
          </button>
          <h2 className="text-xl font-semibold">{run.title}</h2>
          <div className="mt-1 flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-xs text-muted-foreground">
              Started {new Date(run.started_at).toLocaleDateString()}
            </span>
          </div>
        </div>
        {canCancel && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancel.mutate(runId)}
            disabled={cancel.isPending}
            data-testid="btn-cancel-run"
          >
            <Ban className="mr-1 h-4 w-4" />
            Cancel Run
          </Button>
        )}
      </div>

      {/* Business context — Sprint 35 */}
      <BusinessContextSection run={run} workspaceId={workspaceId} />

      {/* Step checklist */}
      <div className="space-y-2" data-testid="step-checklist">
        {run.run_steps.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="no-steps-message">
            No steps defined for this run.
          </p>
        )}
        {run.run_steps.map((step) => (
          <button
            key={step.id}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent",
              step.status === "completed" && "opacity-70",
              isImmutable && "cursor-default",
            )}
            onClick={() => !isImmutable && setSelectedStep(step)}
            data-testid={`step-row-${step.id}`}
          >
            <StepStatusIcon status={step.status} />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{step.title}</span>
                {step.required && (
                  <Badge variant="outline" className="text-xs">Required</Badge>
                )}
              </div>
              {step.notes && (
                <p className="mt-0.5 text-xs text-muted-foreground">{step.notes}</p>
              )}
            </div>
            <span className="text-xs text-muted-foreground capitalize">
              {step.status.replace("_", " ")}
            </span>
            {!isImmutable && <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          </button>
        ))}
      </div>

      {/* Entity workflow history — Sprint 35 */}
      {run.entity_type && run.entity_id && (
        <EntityWorkflowHistoryPanel
          workspaceId={workspaceId}
          entityType={run.entity_type}
          entityId={run.entity_id}
          currentRunId={runId}
          onSelectRun={setSelectedHistoryRunId}
        />
      )}

      {selectedStep && (
        <StepActionDialog
          step={selectedStep}
          workspaceId={workspaceId}
          runId={runId}
          open={!!selectedStep}
          onClose={() => setSelectedStep(null)}
        />
      )}
    </div>
  );
}

// ── Run list row ──────────────────────────────────────────────────────────────

function RunRow({
  run,
  onClick,
}: {
  run: WorkflowRunOut;
  onClick: () => void;
}) {
  const doneSteps = run.run_steps.filter((s) => s.status === "completed").length;
  const totalRequired = run.run_steps.filter((s) => s.required).length;

  return (
    <button
      className="flex w-full items-center gap-4 rounded-lg border p-4 text-left hover:bg-accent transition-colors"
      onClick={onClick}
      data-testid={`run-row-${run.id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{run.title}</span>
          <RunStatusBadge status={run.status} />
          {run.entity_type && (
            <Badge variant="outline" className="text-xs capitalize">
              {run.entity_type}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {totalRequired > 0
            ? `${doneSteps}/${totalRequired} required steps done`
            : "No required steps"}{" "}
          · Started {new Date(run.started_at).toLocaleDateString()}
          {run.entity_title && ` · ${run.entity_title}`}
        </p>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  );
}

// ── Main WorkflowExecutionCenter ──────────────────────────────────────────────

interface WorkflowExecutionCenterProps {
  workspaceId: string;
}

export function WorkflowExecutionCenter({ workspaceId }: WorkflowExecutionCenterProps) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const activeRuns = useWorkflowRuns(workspaceId, { status_filter: "active" });
  const completedRuns = useWorkflowRuns(workspaceId, { status_filter: "completed" });
  const cancelledRuns = useWorkflowRuns(workspaceId, { status_filter: "cancelled" });

  if (selectedRunId) {
    return (
      <RunDetail
        runId={selectedRunId}
        workspaceId={workspaceId}
        onBack={() => setSelectedRunId(null)}
      />
    );
  }

  return (
    <div className="space-y-4" data-testid="workflow-execution-center">
      <div className="flex items-center justify-between px-6 pt-6">
        <div>
          <h1 className="text-2xl font-semibold">Workflow Runs</h1>
          <p className="text-sm text-muted-foreground">
            Track active and completed workflow executions.
          </p>
        </div>
      </div>

      <Tabs defaultValue="active" className="px-6">
        <TabsList>
          <TabsTrigger value="active" data-testid="tab-active">Active</TabsTrigger>
          <TabsTrigger value="completed" data-testid="tab-completed">Completed</TabsTrigger>
          <TabsTrigger value="cancelled" data-testid="tab-cancelled">Cancelled</TabsTrigger>
        </TabsList>

        <TabsContent value="active" className="mt-4 space-y-2" data-testid="tab-panel-active">
          {activeRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="active-loading">Loading…</p>
          )}
          {activeRuns.error && (
            <p className="text-sm text-destructive" data-testid="active-error">Failed to load active runs.</p>
          )}
          {activeRuns.data?.items.length === 0 && !activeRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="active-empty">
              No active workflow runs.
            </p>
          )}
          {activeRuns.data?.items.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              onClick={() => setSelectedRunId(run.id)}
            />
          ))}
        </TabsContent>

        <TabsContent value="completed" className="mt-4 space-y-2" data-testid="tab-panel-completed">
          {completedRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="completed-loading">Loading…</p>
          )}
          {completedRuns.data?.items.length === 0 && !completedRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="completed-empty">
              No completed workflow runs.
            </p>
          )}
          {completedRuns.data?.items.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              onClick={() => setSelectedRunId(run.id)}
            />
          ))}
        </TabsContent>

        <TabsContent value="cancelled" className="mt-4 space-y-2" data-testid="tab-panel-cancelled">
          {cancelledRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="cancelled-loading">Loading…</p>
          )}
          {cancelledRuns.data?.items.length === 0 && !cancelledRuns.isLoading && (
            <p className="text-sm text-muted-foreground" data-testid="cancelled-empty">
              No cancelled workflow runs.
            </p>
          )}
          {cancelledRuns.data?.items.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              onClick={() => setSelectedRunId(run.id)}
            />
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
