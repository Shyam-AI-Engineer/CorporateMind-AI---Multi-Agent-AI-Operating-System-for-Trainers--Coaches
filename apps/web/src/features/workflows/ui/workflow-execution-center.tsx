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
} from "@/features/workflows/api/use-workflows";
import type {
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
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {totalRequired > 0
            ? `${doneSteps}/${totalRequired} required steps done`
            : "No required steps"}{" "}
          · Started {new Date(run.started_at).toLocaleDateString()}
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
