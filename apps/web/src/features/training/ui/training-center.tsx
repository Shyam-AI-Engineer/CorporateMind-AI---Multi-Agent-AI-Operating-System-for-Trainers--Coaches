"use client";

import { useState } from "react";
import {
  useTrainingEngagements,
  useCreateTrainingEngagement,
  useUpdateTrainingEngagement,
  useStartEngagement,
  useCompleteEngagement,
  useCancelEngagement,
  useAssignTrainer,
  useAssignCoordinator,
} from "@/features/training/api/use-training";
import type {
  CancelEngagement,
  CompleteEngagement,
  DeliveryMode,
  TrainingEngagement,
  TrainingEngagementCreate,
  TrainingEngagementFilters,
  TrainingPriority,
  TrainingStatus,
} from "@/features/training/types";
import {
  DELIVERY_MODES,
  TRAINING_PRIORITIES,
  TRAINING_STATUSES,
} from "@/features/training/types";

// ── Status helpers ────────────────────────────────────────────────────────────

function statusColor(status: TrainingStatus): string {
  switch (status) {
    case "planned":     return "bg-blue-100 text-blue-800";
    case "scheduled":   return "bg-purple-100 text-purple-800";
    case "in_progress": return "bg-yellow-100 text-yellow-800";
    case "completed":   return "bg-green-100 text-green-800";
    case "cancelled":   return "bg-gray-100 text-gray-600";
  }
}

function priorityColor(priority: TrainingPriority): string {
  switch (priority) {
    case "low":    return "bg-gray-100 text-gray-600";
    case "medium": return "bg-blue-100 text-blue-700";
    case "high":   return "bg-orange-100 text-orange-700";
    case "urgent": return "bg-red-100 text-red-700";
  }
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

export function TrainingStatusBadge({ status }: { status: TrainingStatus }) {
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusColor(status)}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// ── PriorityBadge ─────────────────────────────────────────────────────────────

export function TrainingPriorityBadge({ priority }: { priority: TrainingPriority }) {
  return (
    <span
      data-testid={`priority-badge-${priority}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${priorityColor(priority)}`}
    >
      {priority}
    </span>
  );
}

// ── KPI section ───────────────────────────────────────────────────────────────

function KpiCard({ label, value, testId }: { label: string; value: number; testId?: string }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold" data-testid={testId}>
        {value}
      </p>
    </div>
  );
}

function KpiSection({ engagements }: { engagements: TrainingEngagement[] }) {
  const inProgress = engagements.filter((e) => e.status === "in_progress").length;
  const planned    = engagements.filter((e) => e.status === "planned").length;
  const completed  = engagements.filter((e) => e.status === "completed").length;
  const cancelled  = engagements.filter((e) => e.status === "cancelled").length;
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4" data-testid="kpi-section">
      <KpiCard label="In Progress" value={inProgress} testId="kpi-in-progress" />
      <KpiCard label="Planned"     value={planned}    testId="kpi-planned" />
      <KpiCard label="Completed"   value={completed}  testId="kpi-completed" />
      <KpiCard label="Cancelled"   value={cancelled}  testId="kpi-cancelled" />
    </div>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  search: string;
  status: string;
  deliveryMode: string;
  onSearch: (v: string) => void;
  onStatus: (v: string) => void;
  onDeliveryMode: (v: string) => void;
}

function FilterBar({
  search, status, deliveryMode, onSearch, onStatus, onDeliveryMode,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="filter-bar">
      <input
        type="text"
        placeholder="Search engagements…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        data-testid="search-input"
        className="rounded border px-3 py-1.5 text-sm"
      />
      <select
        value={status}
        onChange={(e) => onStatus(e.target.value)}
        data-testid="status-select"
        className="rounded border px-3 py-1.5 text-sm"
      >
        <option value="">All statuses</option>
        {TRAINING_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
      <select
        value={deliveryMode}
        onChange={(e) => onDeliveryMode(e.target.value)}
        data-testid="delivery-mode-select"
        className="rounded border px-3 py-1.5 text-sm"
      >
        <option value="">All modes</option>
        {DELIVERY_MODES.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Engagement table ──────────────────────────────────────────────────────────

function EngagementTable({
  engagements,
  onSelect,
}: {
  engagements: TrainingEngagement[];
  onSelect: (e: TrainingEngagement) => void;
}) {
  if (engagements.length === 0) {
    return (
      <p data-testid="empty-state" className="py-8 text-center text-muted-foreground">
        No engagements found.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border" data-testid="engagement-table">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-2 text-left">Program</th>
            <th className="px-4 py-2 text-left">Type</th>
            <th className="px-4 py-2 text-left">Mode</th>
            <th className="px-4 py-2 text-left">Status</th>
            <th className="px-4 py-2 text-left">Priority</th>
            <th className="px-4 py-2 text-left">Start date</th>
          </tr>
        </thead>
        <tbody>
          {engagements.map((e) => (
            <tr
              key={e.id}
              onClick={() => onSelect(e)}
              data-testid={`engagement-row-${e.id}`}
              className="cursor-pointer border-t hover:bg-muted/30"
            >
              <td className="px-4 py-2 font-medium">{e.program_name}</td>
              <td className="px-4 py-2 text-muted-foreground">{e.training_type}</td>
              <td className="px-4 py-2 text-muted-foreground">{e.delivery_mode}</td>
              <td className="px-4 py-2">
                <TrainingStatusBadge status={e.status} />
              </td>
              <td className="px-4 py-2">
                <TrainingPriorityBadge priority={e.priority} />
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {e.planned_start_date ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Complete dialog ───────────────────────────────────────────────────────────

interface CompleteDialogProps {
  engagementId: string;
  workspaceId: string;
  onClose: () => void;
  onComplete: (id: string, body: CompleteEngagement) => void;
}

function CompleteDialog({ engagementId, onClose, onComplete }: CompleteDialogProps) {
  const [actualEndDate, setActualEndDate] = useState("");
  const [actualParticipants, setActualParticipants] = useState("");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onComplete(engagementId, {
      actual_end_date: actualEndDate || undefined,
      actual_participants: actualParticipants ? Number(actualParticipants) : undefined,
      notes: notes || undefined,
    });
    onClose();
  }

  return (
    <div
      data-testid="complete-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Complete engagement</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="date"
            value={actualEndDate}
            onChange={(e) => setActualEndDate(e.target.value)}
            data-testid="complete-end-date"
            className="w-full rounded border px-3 py-2 text-sm"
            placeholder="Actual end date"
          />
          <input
            type="number"
            min={0}
            value={actualParticipants}
            onChange={(e) => setActualParticipants(e.target.value)}
            data-testid="complete-participants"
            className="w-full rounded border px-3 py-2 text-sm"
            placeholder="Actual participants"
          />
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="complete-notes"
            placeholder="Completion notes"
            rows={3}
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="complete-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="complete-submit"
              className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700"
            >
              Mark complete
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Cancel dialog ─────────────────────────────────────────────────────────────

interface CancelDialogProps {
  engagementId: string;
  onClose: () => void;
  onCancel: (id: string, body: CancelEngagement) => void;
}

function CancelDialog({ engagementId, onClose, onCancel }: CancelDialogProps) {
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onCancel(engagementId, { notes: notes || undefined });
    onClose();
  }

  return (
    <div
      data-testid="cancel-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Cancel engagement</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="cancel-notes"
            placeholder="Reason for cancellation (optional)"
            rows={3}
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="cancel-dialog-close"
              className="rounded border px-4 py-2 text-sm"
            >
              Back
            </button>
            <button
              type="submit"
              data-testid="cancel-submit"
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            >
              Cancel engagement
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Assign trainer dialog ─────────────────────────────────────────────────────

interface AssignTrainerDialogProps {
  engagementId: string;
  onClose: () => void;
  onAssign: (id: string, trainerId: string) => void;
}

function AssignTrainerDialog({ engagementId, onClose, onAssign }: AssignTrainerDialogProps) {
  const [trainerId, setTrainerId] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!trainerId.trim()) return;
    onAssign(engagementId, trainerId.trim());
    onClose();
  }

  return (
    <div
      data-testid="assign-trainer-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Assign trainer</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            value={trainerId}
            onChange={(e) => setTrainerId(e.target.value)}
            data-testid="trainer-id-input"
            placeholder="Trainer ID (UUID)"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="assign-trainer-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="assign-trainer-submit"
              disabled={!trainerId.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Assign
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Assign coordinator dialog ─────────────────────────────────────────────────

interface AssignCoordinatorDialogProps {
  engagementId: string;
  onClose: () => void;
  onAssign: (id: string, coordinatorId: string) => void;
}

function AssignCoordinatorDialog({
  engagementId,
  onClose,
  onAssign,
}: AssignCoordinatorDialogProps) {
  const [coordinatorId, setCoordinatorId] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!coordinatorId.trim()) return;
    onAssign(engagementId, coordinatorId.trim());
    onClose();
  }

  return (
    <div
      data-testid="assign-coordinator-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Assign coordinator</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            value={coordinatorId}
            onChange={(e) => setCoordinatorId(e.target.value)}
            data-testid="coordinator-id-input"
            placeholder="Coordinator ID (UUID)"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="assign-coordinator-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="assign-coordinator-submit"
              disabled={!coordinatorId.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Assign
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Detail drawer ─────────────────────────────────────────────────────────────

interface DetailDrawerProps {
  engagement: TrainingEngagement;
  workspaceId: string;
  onClose: () => void;
  onStart: (id: string) => void;
  onOpenComplete: (id: string) => void;
  onOpenCancel: (id: string) => void;
  onOpenAssignTrainer: (id: string) => void;
  onOpenAssignCoordinator: (id: string) => void;
}

const TERMINAL = new Set<TrainingStatus>(["completed", "cancelled"]);

function DetailDrawer({
  engagement,
  onClose,
  onStart,
  onOpenComplete,
  onOpenCancel,
  onOpenAssignTrainer,
  onOpenAssignCoordinator,
}: DetailDrawerProps) {
  const isTerminal = TERMINAL.has(engagement.status);
  const canStart = engagement.status === "planned" || engagement.status === "scheduled";

  return (
    <div
      data-testid="detail-drawer"
      className="fixed right-0 top-0 h-full w-[420px] overflow-y-auto border-l bg-white p-6 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold" data-testid="drawer-program-name">
          {engagement.program_name}
        </h2>
        <button onClick={onClose} data-testid="drawer-close" className="text-muted-foreground hover:text-foreground">
          ✕
        </button>
      </div>

      {/* Status + priority */}
      <div className="mb-4 flex gap-2">
        <TrainingStatusBadge status={engagement.status} />
        <TrainingPriorityBadge priority={engagement.priority} />
      </div>

      {/* Details */}
      <div className="space-y-2 text-sm">
        <div>
          <span className="text-muted-foreground">Type: </span>
          <span data-testid="drawer-training-type">{engagement.training_type}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Mode: </span>
          <span data-testid="drawer-delivery-mode">{engagement.delivery_mode}</span>
        </div>
        {engagement.planned_start_date && (
          <div>
            <span className="text-muted-foreground">Planned start: </span>
            <span data-testid="drawer-planned-start">{engagement.planned_start_date}</span>
          </div>
        )}
        {engagement.planned_end_date && (
          <div>
            <span className="text-muted-foreground">Planned end: </span>
            <span data-testid="drawer-planned-end">{engagement.planned_end_date}</span>
          </div>
        )}
        {engagement.actual_start_date && (
          <div>
            <span className="text-muted-foreground">Actual start: </span>
            <span data-testid="drawer-actual-start">{engagement.actual_start_date}</span>
          </div>
        )}
        {engagement.actual_end_date && (
          <div>
            <span className="text-muted-foreground">Actual end: </span>
            <span data-testid="drawer-actual-end">{engagement.actual_end_date}</span>
          </div>
        )}
        {engagement.estimated_participants != null && (
          <div>
            <span className="text-muted-foreground">Estimated participants: </span>
            <span data-testid="drawer-estimated-participants">{engagement.estimated_participants}</span>
          </div>
        )}
        {engagement.actual_participants != null && (
          <div>
            <span className="text-muted-foreground">Actual participants: </span>
            <span data-testid="drawer-actual-participants">{engagement.actual_participants}</span>
          </div>
        )}
        {engagement.location && (
          <div>
            <span className="text-muted-foreground">Location: </span>
            <span data-testid="drawer-location">{engagement.location}</span>
          </div>
        )}
        {engagement.meeting_link && (
          <div>
            <span className="text-muted-foreground">Meeting link: </span>
            <span data-testid="drawer-meeting-link">{engagement.meeting_link}</span>
          </div>
        )}
        {engagement.assigned_trainer_id && (
          <div>
            <span className="text-muted-foreground">Trainer: </span>
            <span data-testid="drawer-trainer-id">{engagement.assigned_trainer_id}</span>
          </div>
        )}
        {engagement.coordinator_id && (
          <div>
            <span className="text-muted-foreground">Coordinator: </span>
            <span data-testid="drawer-coordinator-id">{engagement.coordinator_id}</span>
          </div>
        )}
        {engagement.notes && (
          <div>
            <span className="text-muted-foreground">Notes: </span>
            <span data-testid="drawer-notes">{engagement.notes}</span>
          </div>
        )}
      </div>

      {/* Status transitions */}
      {!isTerminal && (
        <div className="mt-6 space-y-2" data-testid="status-actions">
          {canStart && (
            <button
              onClick={() => onStart(engagement.id)}
              data-testid="start-btn"
              className="w-full rounded bg-yellow-500 px-3 py-2 text-sm text-white hover:bg-yellow-600"
            >
              Start engagement
            </button>
          )}
          {engagement.status === "in_progress" && (
            <button
              onClick={() => onOpenComplete(engagement.id)}
              data-testid="complete-btn"
              className="w-full rounded bg-green-600 px-3 py-2 text-sm text-white hover:bg-green-700"
            >
              Complete engagement
            </button>
          )}
          <button
            onClick={() => onOpenCancel(engagement.id)}
            data-testid="cancel-btn"
            className="w-full rounded border border-red-300 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
          >
            Cancel engagement
          </button>
        </div>
      )}

      {/* Assignments */}
      <div className="mt-6 space-y-2" data-testid="assignment-actions">
        <button
          onClick={() => onOpenAssignTrainer(engagement.id)}
          data-testid="assign-trainer-btn"
          className="w-full rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Assign trainer
        </button>
        <button
          onClick={() => onOpenAssignCoordinator(engagement.id)}
          data-testid="assign-coordinator-btn"
          className="w-full rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Assign coordinator
        </button>
      </div>
    </div>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

interface CreateDialogProps {
  workspaceId: string;
  onClose: () => void;
  onCreate: (req: TrainingEngagementCreate) => void;
}

function CreateDialog({ workspaceId, onClose, onCreate }: CreateDialogProps) {
  const [programName, setProgramName]     = useState("");
  const [trainingType, setTrainingType]   = useState("");
  const [customerId, setCustomerId]       = useState("");
  const [deliveryMode, setDeliveryMode]   = useState<DeliveryMode>("onsite");
  const [priority, setPriority]           = useState<TrainingPriority>("medium");
  const [plannedStart, setPlannedStart]   = useState("");
  const [plannedEnd, setPlannedEnd]       = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!programName || !trainingType || !customerId) return;
    onCreate({
      workspace_id: workspaceId,
      customer_id: customerId,
      program_name: programName,
      training_type: trainingType,
      delivery_mode: deliveryMode,
      priority,
      planned_start_date: plannedStart || undefined,
      planned_end_date: plannedEnd || undefined,
    });
    onClose();
  }

  return (
    <div
      data-testid="create-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">New training engagement</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Program name *"
            value={programName}
            onChange={(e) => setProgramName(e.target.value)}
            data-testid="create-program-name"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Customer ID (UUID) *"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            data-testid="create-customer-id"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Training type *"
            value={trainingType}
            onChange={(e) => setTrainingType(e.target.value)}
            data-testid="create-training-type"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <select
              value={deliveryMode}
              onChange={(e) => setDeliveryMode(e.target.value as DeliveryMode)}
              data-testid="create-delivery-mode"
              className="flex-1 rounded border px-3 py-2 text-sm"
            >
              {DELIVERY_MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value as TrainingPriority)}
              data-testid="create-priority"
              className="flex-1 rounded border px-3 py-2 text-sm"
            >
              {TRAINING_PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <input
              type="date"
              value={plannedStart}
              onChange={(e) => setPlannedStart(e.target.value)}
              data-testid="create-planned-start"
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
            <input
              type="date"
              value={plannedEnd}
              onChange={(e) => setPlannedEnd(e.target.value)}
              data-testid="create-planned-end"
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="create-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="create-submit"
              disabled={!programName || !trainingType || !customerId}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type Modal =
  | { kind: "complete"; id: string }
  | { kind: "cancel"; id: string }
  | { kind: "assign-trainer"; id: string }
  | { kind: "assign-coordinator"; id: string }
  | null;

interface TrainingCenterProps {
  workspaceId: string;
}

export function TrainingCenter({ workspaceId }: TrainingCenterProps) {
  const [search, setSearch]               = useState("");
  const [statusFilter, setStatusFilter]   = useState<string>("");
  const [modeFilter, setModeFilter]       = useState<string>("");
  const [cursor, setCursor]               = useState<string | undefined>();
  const [selected, setSelected]           = useState<TrainingEngagement | null>(null);
  const [showCreate, setShowCreate]       = useState(false);
  const [modal, setModal]                 = useState<Modal>(null);

  const filters: TrainingEngagementFilters = {
    workspace_id: workspaceId,
    ...(statusFilter   ? { status:        statusFilter   as TrainingStatus } : {}),
    ...(modeFilter     ? { delivery_mode: modeFilter     as DeliveryMode }   : {}),
    ...(search         ? { search }                                           : {}),
    ...(cursor         ? { cursor }                                           : {}),
  };

  const { data, isLoading, isError } = useTrainingEngagements(filters);
  const createMut       = useCreateTrainingEngagement(workspaceId);
  const updateMut       = useUpdateTrainingEngagement(workspaceId);
  const startMut        = useStartEngagement(workspaceId);
  const completeMut     = useCompleteEngagement(workspaceId);
  const cancelMut       = useCancelEngagement(workspaceId);
  const assignTrainer   = useAssignTrainer(workspaceId);
  const assignCoord     = useAssignCoordinator(workspaceId);

  const engagements = data?.data?.items   ?? [];
  const hasMore     = data?.data?.has_more ?? false;
  const nextCursor  = data?.data?.next_cursor ?? undefined;
  const total       = data?.data?.total   ?? 0;

  function handleStart(id: string) {
    startMut.mutate(id, {
      onSuccess: (res) => {
        if (selected?.id === id) setSelected(res.data);
      },
    });
  }

  function handleComplete(id: string, body: CompleteEngagement) {
    completeMut.mutate({ id, body }, {
      onSuccess: (res) => {
        if (selected?.id === id) setSelected(res.data);
      },
    });
  }

  function handleCancel(id: string, body: { notes?: string }) {
    cancelMut.mutate({ id, body }, {
      onSuccess: (res) => {
        if (selected?.id === id) setSelected(res.data);
      },
    });
  }

  function handleAssignTrainer(id: string, trainerId: string) {
    assignTrainer.mutate({ id, body: { assigned_trainer_id: trainerId } }, {
      onSuccess: (res) => {
        if (selected?.id === id) setSelected(res.data);
      },
    });
  }

  function handleAssignCoordinator(id: string, coordinatorId: string) {
    assignCoord.mutate({ id, body: { coordinator_id: coordinatorId } }, {
      onSuccess: (res) => {
        if (selected?.id === id) setSelected(res.data);
      },
    });
  }

  return (
    <div className="space-y-6" data-testid="training-center">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Training Engagements</h1>
          <p className="text-sm text-muted-foreground" data-testid="engagement-total">
            {total} engagement{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="add-engagement-btn"
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          New engagement
        </button>
      </div>

      {/* KPIs */}
      <KpiSection engagements={engagements} />

      {/* Filters */}
      <FilterBar
        search={search}
        status={statusFilter}
        deliveryMode={modeFilter}
        onSearch={(v) => { setSearch(v); setCursor(undefined); }}
        onStatus={(v) => { setStatusFilter(v); setCursor(undefined); }}
        onDeliveryMode={(v) => { setModeFilter(v); setCursor(undefined); }}
      />

      {/* Table */}
      {isLoading && (
        <p data-testid="loading-state" className="py-8 text-center text-muted-foreground">
          Loading engagements…
        </p>
      )}
      {isError && (
        <p data-testid="error-state" className="py-4 text-center text-red-600">
          Failed to load engagements.
        </p>
      )}
      {!isLoading && !isError && (
        <EngagementTable engagements={engagements} onSelect={setSelected} />
      )}

      {/* Pagination */}
      {hasMore && (
        <div className="flex justify-center">
          <button
            onClick={() => setCursor(nextCursor)}
            data-testid="load-more-btn"
            className="rounded border px-4 py-2 text-sm hover:bg-muted"
          >
            Load more
          </button>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <DetailDrawer
          engagement={selected}
          workspaceId={workspaceId}
          onClose={() => setSelected(null)}
          onStart={handleStart}
          onOpenComplete={(id) => setModal({ kind: "complete", id })}
          onOpenCancel={(id) => setModal({ kind: "cancel", id })}
          onOpenAssignTrainer={(id) => setModal({ kind: "assign-trainer", id })}
          onOpenAssignCoordinator={(id) => setModal({ kind: "assign-coordinator", id })}
        />
      )}

      {/* Create dialog */}
      {showCreate && (
        <CreateDialog
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreate={(req) => createMut.mutate(req)}
        />
      )}

      {/* Complete dialog */}
      {modal?.kind === "complete" && (
        <CompleteDialog
          engagementId={modal.id}
          workspaceId={workspaceId}
          onClose={() => setModal(null)}
          onComplete={handleComplete}
        />
      )}

      {/* Cancel dialog */}
      {modal?.kind === "cancel" && (
        <CancelDialog
          engagementId={modal.id}
          onClose={() => setModal(null)}
          onCancel={handleCancel}
        />
      )}

      {/* Assign trainer dialog */}
      {modal?.kind === "assign-trainer" && (
        <AssignTrainerDialog
          engagementId={modal.id}
          onClose={() => setModal(null)}
          onAssign={handleAssignTrainer}
        />
      )}

      {/* Assign coordinator dialog */}
      {modal?.kind === "assign-coordinator" && (
        <AssignCoordinatorDialog
          engagementId={modal.id}
          onClose={() => setModal(null)}
          onAssign={handleAssignCoordinator}
        />
      )}
    </div>
  );
}
