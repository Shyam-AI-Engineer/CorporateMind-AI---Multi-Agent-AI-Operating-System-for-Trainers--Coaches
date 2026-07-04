"use client";

import React, { useState } from "react";
import {
  useAttendanceList,
  useRegisterParticipant,
  useUpdateAttendance,
  useMarkPresent,
  useMarkLate,
  useMarkAbsent,
  useMarkLeftEarly,
  useCheckOut,
} from "@/features/training/api/use-training";
import type {
  TrainingAttendance,
  AttendanceStatus,
  TrainingAttendanceCreate,
  TrainingAttendanceUpdate,
  CheckOutAttendance,
  TrainingAttendanceFilters,
} from "@/features/training/types";
import { ATTENDANCE_STATUSES } from "@/features/training/types";

// ── Utility ───────────────────────────────────────────────────────────────────

function statusLabel(s: AttendanceStatus): string {
  const map: Record<AttendanceStatus, string> = {
    registered: "Registered",
    present: "Present",
    late: "Late",
    absent: "Absent",
    left_early: "Left Early",
  };
  return map[s] ?? s;
}

function statusColor(s: AttendanceStatus): string {
  const map: Record<AttendanceStatus, string> = {
    registered: "bg-gray-100 text-gray-700",
    present: "bg-green-100 text-green-700",
    late: "bg-yellow-100 text-yellow-700",
    absent: "bg-red-100 text-red-700",
    left_early: "bg-orange-100 text-orange-700",
  };
  return map[s] ?? "bg-gray-100 text-gray-700";
}

function fmt(dt: string | null): string {
  if (!dt) return "—";
  return new Date(dt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── KPI computation ───────────────────────────────────────────────────────────

interface KPIs {
  total: number;
  present: number;
  late: number;
  absent: number;
  left_early: number;
  registered: number;
  certificate_eligible: number;
  avg_completion: number | null;
}

function computeKPIs(items: TrainingAttendance[]): KPIs {
  const total = items.length;
  const present = items.filter((i) => i.attendance_status === "present").length;
  const late = items.filter((i) => i.attendance_status === "late").length;
  const absent = items.filter((i) => i.attendance_status === "absent").length;
  const left_early = items.filter((i) => i.attendance_status === "left_early").length;
  const registered = items.filter((i) => i.attendance_status === "registered").length;
  const certificate_eligible = items.filter((i) => i.certificate_eligible).length;
  const completions = items
    .map((i) => i.completion_percent)
    .filter((p): p is number => p !== null);
  const avg_completion =
    completions.length > 0
      ? completions.reduce((a, b) => a + b, 0) / completions.length
      : null;
  return {
    total,
    present,
    late,
    absent,
    left_early,
    registered,
    certificate_eligible,
    avg_completion,
  };
}

// ── RegisterParticipantDialog ─────────────────────────────────────────────────

interface RegisterParticipantDialogProps {
  sessionId: string;
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

function RegisterParticipantDialog({
  sessionId,
  workspaceId,
  open,
  onClose,
}: RegisterParticipantDialogProps) {
  const register = useRegisterParticipant(workspaceId);
  const [form, setForm] = useState<TrainingAttendanceCreate>({
    workspace_id: workspaceId,
    session_id: sessionId,
    participant_name: "",
    participant_email: "",
    participant_phone: "",
    company: "",
    designation: "",
    attendance_status: "registered",
    certificate_eligible: false,
    remarks: "",
  });
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.participant_name.trim()) {
      setError("Participant name is required");
      return;
    }
    try {
      await register.mutateAsync({
        ...form,
        participant_email: form.participant_email || undefined,
        participant_phone: form.participant_phone || undefined,
        company: form.company || undefined,
        designation: form.designation || undefined,
        remarks: form.remarks || undefined,
      });
      onClose();
    } catch {
      setError("Failed to register participant");
    }
  }

  return (
    <div
      data-testid="register-dialog"
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Register Participant</h2>
        <form onSubmit={handleSubmit} data-testid="register-form">
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                data-testid="input-participant-name"
                name="participant_name"
                value={form.participant_name}
                onChange={handleChange}
                className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
                placeholder="Full name"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">Email</label>
                <input
                  data-testid="input-participant-email"
                  name="participant_email"
                  type="email"
                  value={form.participant_email}
                  onChange={handleChange}
                  className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Phone</label>
                <input
                  data-testid="input-participant-phone"
                  name="participant_phone"
                  value={form.participant_phone}
                  onChange={handleChange}
                  className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">Company</label>
                <input
                  data-testid="input-company"
                  name="company"
                  value={form.company}
                  onChange={handleChange}
                  className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Designation
                </label>
                <input
                  data-testid="input-designation"
                  name="designation"
                  value={form.designation}
                  onChange={handleChange}
                  className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Status</label>
              <select
                data-testid="select-attendance-status"
                name="attendance_status"
                value={form.attendance_status}
                onChange={handleChange}
                className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
              >
                {ATTENDANCE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Remarks</label>
              <textarea
                data-testid="input-remarks"
                name="remarks"
                value={form.remarks}
                onChange={handleChange}
                rows={2}
                className="mt-1 block w-full border rounded-md px-3 py-2 text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                data-testid="checkbox-certificate"
                type="checkbox"
                name="certificate_eligible"
                checked={form.certificate_eligible}
                onChange={handleChange}
                id="cert-eligible"
              />
              <label htmlFor="cert-eligible" className="text-sm text-gray-700">
                Certificate eligible
              </label>
            </div>
          </div>
          {error && (
            <p data-testid="register-error" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              data-testid="btn-cancel-register"
              onClick={onClose}
              className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="btn-submit-register"
              disabled={register.isPending}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {register.isPending ? "Registering…" : "Register"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── AttendanceStatusDialog ────────────────────────────────────────────────────

interface AttendanceStatusDialogProps {
  attendance: TrainingAttendance;
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

function AttendanceStatusDialog({
  attendance,
  workspaceId,
  open,
  onClose,
}: AttendanceStatusDialogProps) {
  const markPresent = useMarkPresent(workspaceId);
  const markLate = useMarkLate(workspaceId);
  const markAbsent = useMarkAbsent(workspaceId);
  const markLeftEarly = useMarkLeftEarly(workspaceId);
  const checkOut = useCheckOut(workspaceId);
  const [error, setError] = useState<string | null>(null);
  const [checkOutTime, setCheckOutTime] = useState("");
  const [completionPct, setCompletionPct] = useState("");
  const [certEligible, setCertEligible] = useState(attendance.certificate_eligible);

  if (!open) return null;

  const args = { id: attendance.id, sessionId: attendance.session_id };

  async function handle(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      onClose();
    } catch {
      setError("Action failed. Please try again.");
    }
  }

  return (
    <div
      data-testid="status-dialog"
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-6">
        <h2 className="text-lg font-semibold mb-1">Update Status</h2>
        <p className="text-sm text-gray-500 mb-4">{attendance.participant_name}</p>
        <div className="flex flex-col gap-2">
          <button
            data-testid="btn-status-present"
            onClick={() => handle(() => markPresent.mutateAsync(args))}
            disabled={markPresent.isPending}
            className="w-full px-4 py-2 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            Mark Present
          </button>
          <button
            data-testid="btn-status-late"
            onClick={() => handle(() => markLate.mutateAsync(args))}
            disabled={markLate.isPending}
            className="w-full px-4 py-2 text-sm bg-yellow-500 text-white rounded-md hover:bg-yellow-600 disabled:opacity-50"
          >
            Mark Late
          </button>
          <button
            data-testid="btn-status-absent"
            onClick={() => handle(() => markAbsent.mutateAsync(args))}
            disabled={markAbsent.isPending}
            className="w-full px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
          >
            Mark Absent
          </button>
          <button
            data-testid="btn-status-left-early"
            onClick={() => handle(() => markLeftEarly.mutateAsync(args))}
            disabled={markLeftEarly.isPending}
            className="w-full px-4 py-2 text-sm bg-orange-500 text-white rounded-md hover:bg-orange-600 disabled:opacity-50"
          >
            Mark Left Early
          </button>
          <hr className="my-2" />
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase">Check Out</p>
            <input
              data-testid="input-checkout-time"
              type="datetime-local"
              value={checkOutTime}
              onChange={(e) => setCheckOutTime(e.target.value)}
              className="w-full border rounded-md px-3 py-1.5 text-sm"
            />
            <input
              data-testid="input-completion-pct"
              type="number"
              min={0}
              max={100}
              step={1}
              placeholder="Completion % (0–100)"
              value={completionPct}
              onChange={(e) => setCompletionPct(e.target.value)}
              className="w-full border rounded-md px-3 py-1.5 text-sm"
            />
            <div className="flex items-center gap-2">
              <input
                data-testid="checkbox-cert-checkout"
                type="checkbox"
                id="cert-checkout"
                checked={certEligible}
                onChange={(e) => setCertEligible(e.target.checked)}
              />
              <label htmlFor="cert-checkout" className="text-sm text-gray-700">
                Certificate eligible
              </label>
            </div>
            <button
              data-testid="btn-checkout"
              onClick={() => {
                const body: CheckOutAttendance = {};
                if (checkOutTime) body.check_out_time = new Date(checkOutTime).toISOString();
                if (completionPct !== "") body.completion_percent = Number(completionPct);
                body.certificate_eligible = certEligible;
                handle(() => checkOut.mutateAsync({ ...args, body }));
              }}
              disabled={checkOut.isPending}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              Check Out
            </button>
          </div>
        </div>
        {error && (
          <p data-testid="status-error" className="mt-2 text-sm text-red-600">
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end">
          <button
            data-testid="btn-close-status"
            onClick={onClose}
            className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── AttendanceDrawer ──────────────────────────────────────────────────────────

interface AttendanceDrawerProps {
  attendance: TrainingAttendance | null;
  workspaceId: string;
  open: boolean;
  onClose: () => void;
  onStatusAction: (attendance: TrainingAttendance) => void;
}

function AttendanceDrawer({
  attendance,
  workspaceId,
  open,
  onClose,
  onStatusAction,
}: AttendanceDrawerProps) {
  const updateAttendance = useUpdateAttendance(workspaceId);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<TrainingAttendanceUpdate>({});
  const [error, setError] = useState<string | null>(null);

  if (!open || !attendance) return null;

  function startEdit() {
    setEditForm({
      participant_name: attendance!.participant_name,
      participant_email: attendance!.participant_email ?? undefined,
      participant_phone: attendance!.participant_phone ?? undefined,
      company: attendance!.company ?? undefined,
      designation: attendance!.designation ?? undefined,
      remarks: attendance!.remarks ?? undefined,
      certificate_eligible: attendance!.certificate_eligible,
    });
    setEditing(true);
  }

  async function saveEdit() {
    setError(null);
    try {
      await updateAttendance.mutateAsync({
        id: attendance!.id,
        sessionId: attendance!.session_id,
        body: editForm,
      });
      setEditing(false);
    } catch {
      setError("Failed to update participant");
    }
  }

  return (
    <div
      data-testid="attendance-drawer"
      role="complementary"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h2 className="text-lg font-semibold" data-testid="drawer-participant-name">
          {attendance.participant_name}
        </h2>
        <button
          data-testid="btn-close-drawer"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
          aria-label="Close drawer"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
        {/* Status badge */}
        <div className="flex items-center gap-2">
          <span
            data-testid="drawer-status-badge"
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${statusColor(attendance.attendance_status)}`}
          >
            {statusLabel(attendance.attendance_status)}
          </span>
          {attendance.certificate_eligible && (
            <span
              data-testid="drawer-certificate-badge"
              className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700"
            >
              Certificate Eligible
            </span>
          )}
        </div>

        {/* Details */}
        {!editing ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-gray-500">Company</dt>
              <dd data-testid="drawer-company" className="font-medium">
                {attendance.company ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Designation</dt>
              <dd data-testid="drawer-designation" className="font-medium">
                {attendance.designation ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Email</dt>
              <dd data-testid="drawer-email" className="font-medium">
                {attendance.participant_email ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Phone</dt>
              <dd data-testid="drawer-phone" className="font-medium">
                {attendance.participant_phone ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Check In</dt>
              <dd data-testid="drawer-check-in" className="font-medium">
                {fmt(attendance.check_in_time)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Check Out</dt>
              <dd data-testid="drawer-check-out" className="font-medium">
                {fmt(attendance.check_out_time)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Completion</dt>
              <dd data-testid="drawer-completion" className="font-medium">
                {attendance.completion_percent !== null
                  ? `${attendance.completion_percent.toFixed(0)}%`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Remarks</dt>
              <dd data-testid="drawer-remarks" className="font-medium">
                {attendance.remarks ?? "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <div className="space-y-3 text-sm" data-testid="drawer-edit-form">
            <div>
              <label className="block text-gray-500">Name</label>
              <input
                data-testid="edit-participant-name"
                value={editForm.participant_name ?? ""}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, participant_name: e.target.value }))
                }
                className="mt-1 w-full border rounded-md px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-gray-500">Company</label>
              <input
                data-testid="edit-company"
                value={editForm.company ?? ""}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, company: e.target.value }))
                }
                className="mt-1 w-full border rounded-md px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-gray-500">Remarks</label>
              <textarea
                data-testid="edit-remarks"
                value={editForm.remarks ?? ""}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, remarks: e.target.value }))
                }
                rows={2}
                className="mt-1 w-full border rounded-md px-3 py-2"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                data-testid="edit-certificate"
                type="checkbox"
                id="edit-cert"
                checked={editForm.certificate_eligible ?? false}
                onChange={(e) =>
                  setEditForm((p) => ({ ...p, certificate_eligible: e.target.checked }))
                }
              />
              <label htmlFor="edit-cert">Certificate eligible</label>
            </div>
            {error && (
              <p data-testid="drawer-error" className="text-red-600 text-xs">
                {error}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="border-t px-6 py-4 flex flex-col gap-2">
        {!editing ? (
          <>
            <button
              data-testid="btn-update-status"
              onClick={() => onStatusAction(attendance)}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Update Status
            </button>
            <button
              data-testid="btn-edit-participant"
              onClick={startEdit}
              className="w-full px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
            >
              Edit Details
            </button>
          </>
        ) : (
          <>
            <button
              data-testid="btn-save-edit"
              onClick={saveEdit}
              disabled={updateAttendance.isPending}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {updateAttendance.isPending ? "Saving…" : "Save"}
            </button>
            <button
              data-testid="btn-cancel-edit"
              onClick={() => setEditing(false)}
              className="w-full px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── AttendanceTable ───────────────────────────────────────────────────────────

interface AttendanceTableProps {
  items: TrainingAttendance[];
  onRowClick: (a: TrainingAttendance) => void;
  onStatusClick: (a: TrainingAttendance) => void;
}

function AttendanceTable({ items, onRowClick, onStatusClick }: AttendanceTableProps) {
  return (
    <div data-testid="attendance-table" className="overflow-x-auto rounded-lg border">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Name</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Company</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Check In</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Check Out</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Completion</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Cert</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {items.map((a) => (
            <tr
              key={a.id}
              data-testid={`attendance-row-${a.id}`}
              className="hover:bg-gray-50 cursor-pointer"
              onClick={() => onRowClick(a)}
            >
              <td className="px-4 py-3 font-medium text-gray-900">{a.participant_name}</td>
              <td className="px-4 py-3 text-gray-500">{a.company ?? "—"}</td>
              <td className="px-4 py-3">
                <span
                  data-testid={`status-badge-${a.id}`}
                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(a.attendance_status)}`}
                >
                  {statusLabel(a.attendance_status)}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">{fmt(a.check_in_time)}</td>
              <td className="px-4 py-3 text-gray-500">{fmt(a.check_out_time)}</td>
              <td className="px-4 py-3 text-gray-500">
                {a.completion_percent !== null ? `${a.completion_percent.toFixed(0)}%` : "—"}
              </td>
              <td className="px-4 py-3">
                {a.certificate_eligible ? (
                  <span
                    data-testid={`cert-badge-${a.id}`}
                    className="inline-flex rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700"
                  >
                    ✓
                  </span>
                ) : (
                  <span className="text-gray-300">—</span>
                )}
              </td>
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <button
                  data-testid={`btn-action-${a.id}`}
                  onClick={() => onStatusClick(a)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Update
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── AttendanceCenter (main) ───────────────────────────────────────────────────

interface AttendanceCenterProps {
  sessionId: string;
  workspaceId: string;
}

export function AttendanceCenter({ sessionId, workspaceId }: AttendanceCenterProps) {
  const [filters, setFilters] = useState<TrainingAttendanceFilters>({
    workspace_id: workspaceId,
    session_id: sessionId,
  });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<AttendanceStatus | "">("");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [selectedAttendance, setSelectedAttendance] =
    useState<TrainingAttendance | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [statusTarget, setStatusTarget] = useState<TrainingAttendance | null>(null);

  const { data, isLoading, isError } = useAttendanceList(filters);
  const items = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? null;
  const kpis = computeKPIs(items);

  function applySearch(value: string) {
    setSearch(value);
    setFilters((prev) => ({ ...prev, search: value || undefined, cursor: undefined }));
  }

  function applyStatusFilter(value: AttendanceStatus | "") {
    setStatusFilter(value);
    setFilters((prev) => ({
      ...prev,
      attendance_status: value || undefined,
      cursor: undefined,
    }));
  }

  function openDrawer(attendance: TrainingAttendance) {
    setSelectedAttendance(attendance);
    setDrawerOpen(true);
  }

  function openStatusDialog(attendance: TrainingAttendance) {
    setStatusTarget(attendance);
    setStatusDialogOpen(true);
  }

  if (isLoading) {
    return (
      <div data-testid="attendance-loading" className="p-8 text-center text-gray-400">
        Loading attendance…
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="attendance-error" className="p-8 text-center text-red-500">
        Failed to load attendance records.
      </div>
    );
  }

  return (
    <div data-testid="attendance-center" className="flex flex-col gap-5 p-1">
      {/* KPIs */}
      <div data-testid="attendance-kpis" className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div
          data-testid="kpi-total"
          className="rounded-lg border bg-white p-4 text-center shadow-sm"
        >
          <p className="text-2xl font-bold text-gray-900">{kpis.total}</p>
          <p className="text-xs text-gray-500 mt-1">Total Registered</p>
        </div>
        <div
          data-testid="kpi-present"
          className="rounded-lg border bg-white p-4 text-center shadow-sm"
        >
          <p className="text-2xl font-bold text-green-600">{kpis.present + kpis.late}</p>
          <p className="text-xs text-gray-500 mt-1">Attended</p>
        </div>
        <div
          data-testid="kpi-absent"
          className="rounded-lg border bg-white p-4 text-center shadow-sm"
        >
          <p className="text-2xl font-bold text-red-600">{kpis.absent}</p>
          <p className="text-xs text-gray-500 mt-1">Absent</p>
        </div>
        <div
          data-testid="kpi-certificate"
          className="rounded-lg border bg-white p-4 text-center shadow-sm"
        >
          <p className="text-2xl font-bold text-blue-600">{kpis.certificate_eligible}</p>
          <p className="text-xs text-gray-500 mt-1">Certificate Eligible</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <input
            data-testid="input-search"
            type="search"
            placeholder="Search participants…"
            value={search}
            onChange={(e) => applySearch(e.target.value)}
            className="border rounded-md px-3 py-2 text-sm w-56 min-w-0"
          />
          <select
            data-testid="select-status-filter"
            value={statusFilter}
            onChange={(e) => applyStatusFilter(e.target.value as AttendanceStatus | "")}
            className="border rounded-md px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            {ATTENDANCE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </div>
        <button
          data-testid="btn-register"
          onClick={() => setRegisterOpen(true)}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 whitespace-nowrap"
        >
          Register Participant
        </button>
      </div>

      {/* Summary */}
      <p className="text-xs text-gray-400" data-testid="attendance-count">
        {total} participant{total !== 1 ? "s" : ""}
      </p>

      {/* Table */}
      {items.length === 0 ? (
        <div
          data-testid="attendance-empty"
          className="rounded-lg border border-dashed p-12 text-center text-gray-400"
        >
          No participants yet.{" "}
          <button
            data-testid="btn-register-empty"
            onClick={() => setRegisterOpen(true)}
            className="text-blue-600 hover:underline"
          >
            Register the first one
          </button>
          .
        </div>
      ) : (
        <AttendanceTable
          items={items}
          onRowClick={openDrawer}
          onStatusClick={openStatusDialog}
        />
      )}

      {/* Pagination */}
      {hasMore && (
        <div className="flex justify-center mt-2">
          <button
            data-testid="btn-load-more"
            onClick={() =>
              setFilters((prev) => ({ ...prev, cursor: nextCursor ?? undefined }))
            }
            className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
          >
            Load more
          </button>
        </div>
      )}

      {/* Register dialog */}
      <RegisterParticipantDialog
        sessionId={sessionId}
        workspaceId={workspaceId}
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
      />

      {/* Status dialog */}
      {statusTarget && (
        <AttendanceStatusDialog
          attendance={statusTarget}
          workspaceId={workspaceId}
          open={statusDialogOpen}
          onClose={() => {
            setStatusDialogOpen(false);
            setStatusTarget(null);
          }}
        />
      )}

      {/* Detail drawer */}
      <AttendanceDrawer
        attendance={selectedAttendance}
        workspaceId={workspaceId}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setSelectedAttendance(null);
        }}
        onStatusAction={(a) => {
          setDrawerOpen(false);
          openStatusDialog(a);
        }}
      />
    </div>
  );
}
