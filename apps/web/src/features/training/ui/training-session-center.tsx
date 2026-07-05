"use client";

import { useState } from "react";
import {
  useCreateTrainingSession,
  useStartSession,
  useCompleteSession,
  useCancelSession,
  useAssignSessionTrainer,
  useEngagementSessions,
  useUpdateTrainingSession,
} from "@/features/training/api/use-training";
import type {
  TrainingSession,
  SessionStatus,
  TrainingSessionCreate,
  TrainingSessionUpdate,
  CompleteSession,
  CancelSession,
  SessionTrainerAssign,
} from "@/features/training/types";
import { SESSION_STATUSES } from "@/features/training/types";
import { CertificateCenter } from "@/features/training/ui/certificate-center";

// ── Status badge ──────────────────────────────────────────────────────────────

function sessionStatusColor(status: SessionStatus): string {
  switch (status) {
    case "planned":
      return "bg-gray-100 text-gray-700";
    case "scheduled":
      return "bg-blue-100 text-blue-700";
    case "in_progress":
      return "bg-yellow-100 text-yellow-700";
    case "completed":
      return "bg-green-100 text-green-700";
    case "cancelled":
      return "bg-red-100 text-red-700";
  }
}

function SessionStatusBadge({ status }: { status: SessionStatus }) {
  return (
    <span
      data-testid={`session-status-${status}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sessionStatusColor(status)}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// ── KPI cards ─────────────────────────────────────────────────────────────────

function SessionKPIs({ sessions }: { sessions: TrainingSession[] }) {
  const planned = sessions.filter((s) => s.status === "planned").length;
  const scheduled = sessions.filter((s) => s.status === "scheduled").length;
  const inProgress = sessions.filter((s) => s.status === "in_progress").length;
  const completed = sessions.filter((s) => s.status === "completed").length;

  return (
    <div
      data-testid="session-kpis"
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      {[
        { label: "Planned", value: planned, testId: "kpi-planned" },
        { label: "Scheduled", value: scheduled, testId: "kpi-scheduled" },
        { label: "In Progress", value: inProgress, testId: "kpi-in-progress" },
        { label: "Completed", value: completed, testId: "kpi-completed" },
      ].map(({ label, value, testId }) => (
        <div
          key={label}
          data-testid={testId}
          className="rounded-lg border bg-white p-4"
        >
          <p className="text-sm text-gray-500">{label}</p>
          <p className="mt-1 text-2xl font-semibold">{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Session table ─────────────────────────────────────────────────────────────

function SessionTable({
  sessions,
  onSelect,
  selectedId,
}: {
  sessions: TrainingSession[];
  onSelect: (s: TrainingSession) => void;
  selectedId: string | null;
}) {
  if (sessions.length === 0) {
    return (
      <p data-testid="session-empty" className="py-8 text-center text-gray-400">
        No sessions yet. Create the first session.
      </p>
    );
  }

  return (
    <div data-testid="session-table" className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-gray-500">#</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Name
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Status
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Scheduled Start
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Scheduled End
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">
              Attendees
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {sessions.map((s) => (
            <tr
              key={s.id}
              data-testid={`session-row-${s.id}`}
              onClick={() => onSelect(s)}
              className={`cursor-pointer hover:bg-gray-50 ${
                selectedId === s.id ? "bg-blue-50" : ""
              }`}
            >
              <td className="px-4 py-3 text-gray-500">
                {s.session_number ?? "—"}
              </td>
              <td className="px-4 py-3 font-medium">{s.session_name}</td>
              <td className="px-4 py-3">
                <SessionStatusBadge status={s.status} />
              </td>
              <td className="px-4 py-3 text-gray-500">
                {s.scheduled_start
                  ? new Date(s.scheduled_start).toLocaleString()
                  : "—"}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {s.scheduled_end
                  ? new Date(s.scheduled_end).toLocaleString()
                  : "—"}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {s.actual_attendees ?? s.expected_attendees ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Session timeline ──────────────────────────────────────────────────────────

function SessionTimeline({ sessions }: { sessions: TrainingSession[] }) {
  const sorted = [...sessions].sort((a, b) => {
    const aNum = a.session_number ?? 999;
    const bNum = b.session_number ?? 999;
    return aNum - bNum;
  });

  return (
    <div data-testid="session-timeline" className="space-y-2">
      {sorted.map((s, i) => (
        <div key={s.id} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            <div
              data-testid={`timeline-dot-${s.id}`}
              className={`h-3 w-3 rounded-full border-2 ${
                s.status === "completed"
                  ? "border-green-500 bg-green-500"
                  : s.status === "in_progress"
                    ? "border-yellow-500 bg-yellow-500"
                    : s.status === "cancelled"
                      ? "border-red-300 bg-red-300"
                      : "border-gray-300 bg-white"
              }`}
            />
            {i < sorted.length - 1 && (
              <div className="h-6 w-0.5 bg-gray-200" />
            )}
          </div>
          <div className="pb-2">
            <p className="text-sm font-medium">
              {s.session_number ? `#${s.session_number} · ` : ""}
              {s.session_name}
            </p>
            <p className="text-xs text-gray-400">
              {s.scheduled_start
                ? new Date(s.scheduled_start).toLocaleString()
                : "No date set"}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

function CreateSessionDialog({
  workspaceId,
  engagementId,
  onClose,
}: {
  workspaceId: string;
  engagementId: string;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [number, setNumber] = useState("");
  const [status, setStatus] = useState<SessionStatus>("planned");
  const [scheduledStart, setScheduledStart] = useState("");
  const [scheduledEnd, setScheduledEnd] = useState("");
  const [location, setLocation] = useState("");
  const [meetingLink, setMeetingLink] = useState("");
  const [capacity, setCapacity] = useState("");
  const [expectedAttendees, setExpectedAttendees] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useCreateTrainingSession(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Session name is required");
      return;
    }
    const body: TrainingSessionCreate = {
      workspace_id: workspaceId,
      engagement_id: engagementId,
      session_name: name.trim(),
      status,
    };
    if (number) body.session_number = Number(number);
    if (scheduledStart) body.scheduled_start = scheduledStart;
    if (scheduledEnd) body.scheduled_end = scheduledEnd;
    if (location) body.location = location;
    if (meetingLink) body.meeting_link = meetingLink;
    if (capacity) body.capacity = Number(capacity);
    if (expectedAttendees) body.expected_attendees = Number(expectedAttendees);
    if (notes) body.notes = notes;

    try {
      await create.mutateAsync(body);
      onClose();
    } catch {
      setError("Failed to create session");
    }
  }

  return (
    <div
      data-testid="create-session-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Create Training Session</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Session Name *
            </label>
            <input
              data-testid="input-session-name"
              className="w-full rounded border px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Day 1 Morning Session"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Session #
              </label>
              <input
                data-testid="input-session-number"
                type="number"
                min={1}
                className="w-full rounded border px-3 py-2 text-sm"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Status</label>
              <select
                data-testid="select-status"
                className="w-full rounded border px-3 py-2 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value as SessionStatus)}
              >
                {SESSION_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Scheduled Start
              </label>
              <input
                data-testid="input-scheduled-start"
                type="datetime-local"
                className="w-full rounded border px-3 py-2 text-sm"
                value={scheduledStart}
                onChange={(e) => setScheduledStart(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Scheduled End
              </label>
              <input
                data-testid="input-scheduled-end"
                type="datetime-local"
                className="w-full rounded border px-3 py-2 text-sm"
                value={scheduledEnd}
                onChange={(e) => setScheduledEnd(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Location</label>
            <input
              data-testid="input-location"
              className="w-full rounded border px-3 py-2 text-sm"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Meeting Link
            </label>
            <input
              data-testid="input-meeting-link"
              className="w-full rounded border px-3 py-2 text-sm"
              value={meetingLink}
              onChange={(e) => setMeetingLink(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Capacity</label>
              <input
                data-testid="input-capacity"
                type="number"
                min={0}
                className="w-full rounded border px-3 py-2 text-sm"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Expected Attendees
              </label>
              <input
                data-testid="input-expected-attendees"
                type="number"
                min={0}
                className="w-full rounded border px-3 py-2 text-sm"
                value={expectedAttendees}
                onChange={(e) => setExpectedAttendees(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea
              data-testid="input-notes"
              className="w-full rounded border px-3 py-2 text-sm"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          {error && (
            <p data-testid="create-error" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              data-testid="btn-cancel-create"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="btn-submit-create"
              disabled={create.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {create.isPending ? "Creating…" : "Create Session"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Complete dialog ───────────────────────────────────────────────────────────

function CompleteSessionDialog({
  session,
  workspaceId,
  onClose,
}: {
  session: TrainingSession;
  workspaceId: string;
  onClose: () => void;
}) {
  const [actualAttendees, setActualAttendees] = useState("");
  const [notes, setNotes] = useState(session.notes ?? "");
  const complete = useCompleteSession(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: CompleteSession = {};
    if (actualAttendees) body.actual_attendees = Number(actualAttendees);
    if (notes) body.notes = notes;
    await complete.mutateAsync({
      id: session.id,
      engagementId: session.engagement_id,
      body,
    });
    onClose();
  }

  return (
    <div
      data-testid="complete-session-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Complete Session</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Actual Attendees
            </label>
            <input
              data-testid="input-actual-attendees"
              type="number"
              min={0}
              className="w-full rounded border px-3 py-2 text-sm"
              value={actualAttendees}
              onChange={(e) => setActualAttendees(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea
              data-testid="input-complete-notes"
              className="w-full rounded border px-3 py-2 text-sm"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              data-testid="btn-cancel-complete"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="btn-submit-complete"
              disabled={complete.isPending}
              className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50"
            >
              {complete.isPending ? "Completing…" : "Mark Complete"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Cancel dialog ─────────────────────────────────────────────────────────────

function CancelSessionDialog({
  session,
  workspaceId,
  onClose,
}: {
  session: TrainingSession;
  workspaceId: string;
  onClose: () => void;
}) {
  const [notes, setNotes] = useState("");
  const cancel = useCancelSession(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: CancelSession = {};
    if (notes) body.notes = notes;
    await cancel.mutateAsync({
      id: session.id,
      engagementId: session.engagement_id,
      body,
    });
    onClose();
  }

  return (
    <div
      data-testid="cancel-session-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Cancel Session</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Reason (optional)
            </label>
            <textarea
              data-testid="input-cancel-notes"
              className="w-full rounded border px-3 py-2 text-sm"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              data-testid="btn-cancel-cancel"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Back
            </button>
            <button
              type="submit"
              data-testid="btn-submit-cancel"
              disabled={cancel.isPending}
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
            >
              {cancel.isPending ? "Cancelling…" : "Cancel Session"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Assign trainer dialog ─────────────────────────────────────────────────────

function AssignTrainerDialog({
  session,
  workspaceId,
  onClose,
}: {
  session: TrainingSession;
  workspaceId: string;
  onClose: () => void;
}) {
  const [trainerId, setTrainerId] = useState(session.trainer_id ?? "");
  const assign = useAssignSessionTrainer(workspaceId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!trainerId.trim()) return;
    const body: SessionTrainerAssign = { trainer_id: trainerId.trim() };
    await assign.mutateAsync({
      id: session.id,
      engagementId: session.engagement_id,
      body,
    });
    onClose();
  }

  return (
    <div
      data-testid="assign-trainer-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Assign Trainer</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Trainer ID</label>
            <input
              data-testid="input-trainer-id"
              className="w-full rounded border px-3 py-2 text-sm"
              value={trainerId}
              onChange={(e) => setTrainerId(e.target.value)}
              placeholder="UUID of trainer"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              data-testid="btn-cancel-assign"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="btn-submit-assign"
              disabled={assign.isPending || !trainerId.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {assign.isPending ? "Assigning…" : "Assign"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Session drawer ─────────────────────────────────────────────────────────────

type ModalState =
  | null
  | { type: "complete" }
  | { type: "cancel" }
  | { type: "assign_trainer" };

function SessionDrawer({
  session,
  workspaceId,
  onClose,
}: {
  session: TrainingSession;
  workspaceId: string;
  onClose: () => void;
}) {
  const [modal, setModal] = useState<ModalState>(null);
  const [drawerTab, setDrawerTab] = useState<"overview" | "certificates">(
    "overview",
  );
  const start = useStartSession(workspaceId);

  const canStart =
    session.status === "planned" || session.status === "scheduled";
  const canComplete = session.status === "in_progress";
  const canCancel =
    session.status !== "completed" && session.status !== "cancelled";

  return (
    <>
      <div
        data-testid="session-drawer"
        className="fixed inset-y-0 right-0 z-40 w-full max-w-md overflow-y-auto bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b p-4">
          <div>
            <h2 className="text-lg font-semibold">{session.session_name}</h2>
            {session.session_number && (
              <p className="text-sm text-gray-500">
                Session #{session.session_number}
              </p>
            )}
          </div>
          <button
            data-testid="btn-close-drawer"
            onClick={onClose}
            className="rounded p-1 hover:bg-gray-100"
          >
            ✕
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b">
          <button
            data-testid="drawer-tab-overview"
            onClick={() => setDrawerTab("overview")}
            className={`px-4 py-2 text-sm font-medium ${
              drawerTab === "overview"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Overview
          </button>
          <button
            data-testid="drawer-tab-certificates"
            onClick={() => setDrawerTab("certificates")}
            className={`px-4 py-2 text-sm font-medium ${
              drawerTab === "certificates"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Certificates
          </button>
        </div>

        {drawerTab === "overview" && (
          <>
            <div className="space-y-4 p-4">
              <div className="flex items-center gap-2">
                <SessionStatusBadge status={session.status} />
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                {[
                  {
                    label: "Scheduled Start",
                    value: session.scheduled_start
                      ? new Date(session.scheduled_start).toLocaleString()
                      : "—",
                    testId: "drawer-scheduled-start",
                  },
                  {
                    label: "Scheduled End",
                    value: session.scheduled_end
                      ? new Date(session.scheduled_end).toLocaleString()
                      : "—",
                    testId: "drawer-scheduled-end",
                  },
                  {
                    label: "Actual Start",
                    value: session.actual_start
                      ? new Date(session.actual_start).toLocaleString()
                      : "—",
                    testId: "drawer-actual-start",
                  },
                  {
                    label: "Actual End",
                    value: session.actual_end
                      ? new Date(session.actual_end).toLocaleString()
                      : "—",
                    testId: "drawer-actual-end",
                  },
                  {
                    label: "Location",
                    value: session.location ?? "—",
                    testId: "drawer-location",
                  },
                  {
                    label: "Capacity",
                    value: session.capacity?.toString() ?? "—",
                    testId: "drawer-capacity",
                  },
                  {
                    label: "Expected",
                    value: session.expected_attendees?.toString() ?? "—",
                    testId: "drawer-expected-attendees",
                  },
                  {
                    label: "Actual",
                    value: session.actual_attendees?.toString() ?? "—",
                    testId: "drawer-actual-attendees",
                  },
                ].map(({ label, value, testId }) => (
                  <div key={label}>
                    <p className="text-gray-400">{label}</p>
                    <p data-testid={testId} className="font-medium">
                      {value}
                    </p>
                  </div>
                ))}
              </div>

              {session.meeting_link && (
                <div>
                  <p className="text-sm text-gray-400">Meeting Link</p>
                  <a
                    data-testid="drawer-meeting-link"
                    href={session.meeting_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline"
                  >
                    {session.meeting_link}
                  </a>
                </div>
              )}

              {session.notes && (
                <div>
                  <p className="text-sm text-gray-400">Notes</p>
                  <p data-testid="drawer-notes" className="text-sm">
                    {session.notes}
                  </p>
                </div>
              )}
            </div>

            <div className="border-t p-4">
              <p className="mb-3 text-xs font-medium uppercase text-gray-400">
                Actions
              </p>
              <div className="flex flex-wrap gap-2">
                {canStart && (
                  <button
                    data-testid="btn-start-session"
                    disabled={start.isPending}
                    onClick={() =>
                      start.mutate({
                        id: session.id,
                        engagementId: session.engagement_id,
                      })
                    }
                    className="rounded bg-yellow-500 px-3 py-1.5 text-sm text-white hover:bg-yellow-600 disabled:opacity-50"
                  >
                    Start
                  </button>
                )}
                {canComplete && (
                  <button
                    data-testid="btn-complete-session"
                    onClick={() => setModal({ type: "complete" })}
                    className="rounded bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700"
                  >
                    Complete
                  </button>
                )}
                {canCancel && (
                  <button
                    data-testid="btn-cancel-session"
                    onClick={() => setModal({ type: "cancel" })}
                    className="rounded bg-red-500 px-3 py-1.5 text-sm text-white hover:bg-red-600"
                  >
                    Cancel
                  </button>
                )}
                <button
                  data-testid="btn-assign-trainer"
                  onClick={() => setModal({ type: "assign_trainer" })}
                  className="rounded border px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Assign Trainer
                </button>
              </div>
            </div>
          </>
        )}

        {drawerTab === "certificates" && (
          <div className="p-4">
            <CertificateCenter
              sessionId={session.id}
              workspaceId={workspaceId}
            />
          </div>
        )}
      </div>

      {modal?.type === "complete" && (
        <CompleteSessionDialog
          session={session}
          workspaceId={workspaceId}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === "cancel" && (
        <CancelSessionDialog
          session={session}
          workspaceId={workspaceId}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === "assign_trainer" && (
        <AssignTrainerDialog
          session={session}
          workspaceId={workspaceId}
          onClose={() => setModal(null)}
        />
      )}
    </>
  );
}

// ── Filters bar ───────────────────────────────────────────────────────────────

function SessionFilters({
  statusFilter,
  onStatusChange,
  search,
  onSearchChange,
}: {
  statusFilter: SessionStatus | "";
  onStatusChange: (v: SessionStatus | "") => void;
  search: string;
  onSearchChange: (v: string) => void;
}) {
  return (
    <div data-testid="session-filters" className="flex flex-wrap gap-3">
      <input
        data-testid="input-search"
        className="rounded border px-3 py-2 text-sm"
        placeholder="Search sessions…"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
      />
      <select
        data-testid="select-status-filter"
        className="rounded border px-3 py-2 text-sm"
        value={statusFilter}
        onChange={(e) => onStatusChange(e.target.value as SessionStatus | "")}
      >
        <option value="">All statuses</option>
        {SESSION_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface TrainingSessionCenterProps {
  workspaceId: string;
  engagementId: string;
}

export function TrainingSessionCenter({
  workspaceId,
  engagementId,
}: TrainingSessionCenterProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [selectedSession, setSelectedSession] =
    useState<TrainingSession | null>(null);
  const [statusFilter, setStatusFilter] = useState<SessionStatus | "">("");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"table" | "timeline">("table");

  const { data, isLoading, isError } = useEngagementSessions(engagementId);
  const sessions = data?.data ?? [];

  const filtered = sessions.filter((s) => {
    const matchesStatus = !statusFilter || s.status === statusFilter;
    const matchesSearch =
      !search ||
      s.session_name.toLowerCase().includes(search.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  return (
    <div data-testid="training-session-center" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Sessions</h2>
        <button
          data-testid="btn-create-session"
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          + New Session
        </button>
      </div>

      {/* Loading / error states */}
      {isLoading && (
        <p data-testid="session-loading" className="text-gray-400">
          Loading sessions…
        </p>
      )}
      {isError && (
        <p data-testid="session-error" className="text-red-500">
          Failed to load sessions.
        </p>
      )}

      {!isLoading && !isError && (
        <>
          {/* KPIs */}
          <SessionKPIs sessions={sessions} />

          {/* Filters + view toggle */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SessionFilters
              statusFilter={statusFilter}
              onStatusChange={(v) => setStatusFilter(v)}
              search={search}
              onSearchChange={(v) => setSearch(v)}
            />
            <div className="flex rounded border">
              <button
                data-testid="btn-view-table"
                onClick={() => setView("table")}
                className={`px-3 py-1.5 text-sm ${view === "table" ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}
              >
                Table
              </button>
              <button
                data-testid="btn-view-timeline"
                onClick={() => setView("timeline")}
                className={`px-3 py-1.5 text-sm ${view === "timeline" ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}
              >
                Timeline
              </button>
            </div>
          </div>

          {/* Content */}
          {view === "table" ? (
            <SessionTable
              sessions={filtered}
              onSelect={setSelectedSession}
              selectedId={selectedSession?.id ?? null}
            />
          ) : (
            <SessionTimeline sessions={filtered} />
          )}
        </>
      )}

      {/* Drawer */}
      {selectedSession && (
        <SessionDrawer
          session={selectedSession}
          workspaceId={workspaceId}
          onClose={() => setSelectedSession(null)}
        />
      )}

      {/* Create dialog */}
      {showCreate && (
        <CreateSessionDialog
          workspaceId={workspaceId}
          engagementId={engagementId}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}
