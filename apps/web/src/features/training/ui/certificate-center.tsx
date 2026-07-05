"use client";

import { useState } from "react";
import {
  useCertificateList,
  useCreateCertificate,
  useIssueCertificate,
  useRevokeCertificate,
  useUpdateCertificate,
} from "@/features/training/api/use-training";
import type {
  CertificateStatus,
  IssueCertificate,
  RevokeCertificate,
  TrainingCertificate,
  TrainingCertificateCreate,
  TrainingCertificateFilters,
  TrainingCertificateUpdate,
} from "@/features/training/types";
import { CERTIFICATE_STATUSES } from "@/features/training/types";

// ── Status badge ──────────────────────────────────────────────────────────────

function certStatusColor(status: CertificateStatus): string {
  switch (status) {
    case "draft":
      return "bg-gray-100 text-gray-700";
    case "issued":
      return "bg-green-100 text-green-700";
    case "revoked":
      return "bg-red-100 text-red-700";
  }
}

function CertStatusBadge({
  status,
  testId,
}: {
  status: CertificateStatus;
  testId?: string;
}) {
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${certStatusColor(status)}`}
    >
      {status}
    </span>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

function CreateCertificateDialog({
  sessionId,
  workspaceId,
  onClose,
}: {
  sessionId: string;
  workspaceId: string;
  onClose: () => void;
}) {
  const createMut = useCreateCertificate(workspaceId);
  const [attendanceId, setAttendanceId] = useState("");
  const [certTitle, setCertTitle] = useState("");
  const [notes, setNotes] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: TrainingCertificateCreate = {
      workspace_id: workspaceId,
      attendance_id: attendanceId,
      session_id: sessionId,
      certificate_title: certTitle || undefined,
      notes: notes || undefined,
    };
    try {
      await createMut.mutateAsync(body);
      onClose();
    } catch {
      // error displayed via createMut.error
    }
  };

  return (
    <div
      data-testid="create-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Issue Certificate</h2>
        <form data-testid="create-form" onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Attendance ID
            </label>
            <input
              data-testid="input-attendance-id"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Attendance record ID"
              value={attendanceId}
              onChange={(e) => setAttendanceId(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Certificate Title
            </label>
            <input
              data-testid="input-cert-title"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="e.g. Certificate of Completion"
              value={certTitle}
              onChange={(e) => setCertTitle(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea
              data-testid="input-create-notes"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Optional notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>
          {createMut.error && (
            <p data-testid="create-error" className="text-sm text-red-600">
              {createMut.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              data-testid="btn-cancel-create"
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              data-testid="btn-submit-create"
              type="submit"
              disabled={createMut.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {createMut.isPending ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Issue dialog ──────────────────────────────────────────────────────────────

function IssueCertificateDialog({
  cert,
  workspaceId,
  onClose,
}: {
  cert: TrainingCertificate;
  workspaceId: string;
  onClose: () => void;
}) {
  const issueMut = useIssueCertificate(workspaceId);
  const [issueDate, setIssueDate] = useState("");
  const [issuedBy, setIssuedBy] = useState("");
  const [certNumber, setCertNumber] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: IssueCertificate = {
      issue_date: issueDate || undefined,
      issued_by: issuedBy || undefined,
      certificate_number: certNumber || undefined,
    };
    try {
      await issueMut.mutateAsync({ id: cert.id, sessionId: cert.session_id, body });
      onClose();
    } catch {
      // error displayed via issueMut.error
    }
  };

  return (
    <div
      data-testid="issue-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold">Issue Certificate</h2>
        <p className="mb-4 text-sm text-gray-500">{cert.participant_name}</p>
        <form data-testid="issue-form" onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Issue Date</label>
            <input
              data-testid="input-issue-date"
              type="date"
              className="w-full rounded border px-3 py-2 text-sm"
              value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Issued By</label>
            <input
              data-testid="input-issued-by"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Name or title"
              value={issuedBy}
              onChange={(e) => setIssuedBy(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Certificate Number
            </label>
            <input
              data-testid="input-cert-number"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="e.g. CERT-2026-001"
              value={certNumber}
              onChange={(e) => setCertNumber(e.target.value)}
            />
          </div>
          {issueMut.error && (
            <p data-testid="issue-error" className="text-sm text-red-600">
              {issueMut.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              data-testid="btn-cancel-issue"
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              data-testid="btn-confirm-issue"
              type="submit"
              disabled={issueMut.isPending}
              className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50"
            >
              {issueMut.isPending ? "Issuing…" : "Issue Certificate"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Revoke dialog ─────────────────────────────────────────────────────────────

function RevokeCertificateDialog({
  cert,
  workspaceId,
  onClose,
}: {
  cert: TrainingCertificate;
  workspaceId: string;
  onClose: () => void;
}) {
  const revokeMut = useRevokeCertificate(workspaceId);
  const [notes, setNotes] = useState("");

  const handleRevoke = async () => {
    const body: RevokeCertificate = { notes: notes || undefined };
    try {
      await revokeMut.mutateAsync({ id: cert.id, sessionId: cert.session_id, body });
      onClose();
    } catch {
      // error displayed via revokeMut.error
    }
  };

  return (
    <div
      data-testid="revoke-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-1 text-lg font-semibold">Revoke Certificate</h2>
        <p className="mb-4 text-sm text-gray-500">{cert.participant_name}</p>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Reason (optional)
            </label>
            <textarea
              data-testid="input-revoke-notes"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Reason for revocation"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />
          </div>
          {revokeMut.error && (
            <p data-testid="revoke-error" className="text-sm text-red-600">
              {revokeMut.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              data-testid="btn-cancel-revoke"
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              data-testid="btn-confirm-revoke"
              onClick={handleRevoke}
              disabled={revokeMut.isPending}
              className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
            >
              {revokeMut.isPending ? "Revoking…" : "Revoke"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Certificate drawer ────────────────────────────────────────────────────────

function CertificateDrawer({
  cert,
  workspaceId,
  onClose,
}: {
  cert: TrainingCertificate;
  workspaceId: string;
  onClose: () => void;
}) {
  const updateMut = useUpdateCertificate(workspaceId);
  const [editMode, setEditMode] = useState(false);
  const [editTitle, setEditTitle] = useState(cert.certificate_title ?? "");
  const [editCertNumber, setEditCertNumber] = useState(
    cert.certificate_number ?? "",
  );
  const [editIssuedBy, setEditIssuedBy] = useState(cert.issued_by ?? "");
  const [editNotes, setEditNotes] = useState(cert.notes ?? "");

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: TrainingCertificateUpdate = {
      certificate_title: editTitle || undefined,
      certificate_number: editCertNumber || undefined,
      issued_by: editIssuedBy || undefined,
      notes: editNotes || undefined,
    };
    try {
      await updateMut.mutateAsync({
        id: cert.id,
        sessionId: cert.session_id,
        body,
      });
      setEditMode(false);
    } catch {
      // error displayed via updateMut.error
    }
  };

  return (
    <div
      data-testid="certificate-drawer"
      className="fixed inset-y-0 right-0 z-40 w-full max-w-md overflow-y-auto bg-white shadow-xl"
    >
      <div className="flex items-center justify-between border-b p-4">
        <div>
          <h2 className="text-lg font-semibold">Certificate</h2>
          <p
            data-testid="drawer-participant-name"
            className="text-sm text-gray-500"
          >
            {cert.participant_name}
          </p>
        </div>
        <button
          data-testid="btn-close-drawer"
          onClick={onClose}
          className="rounded p-1 hover:bg-gray-100"
        >
          ✕
        </button>
      </div>

      <div className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <CertStatusBadge
            status={cert.status}
            testId="drawer-status-badge"
          />
        </div>

        {!editMode ? (
          <div className="grid grid-cols-2 gap-4 text-sm">
            {[
              {
                label: "Certificate Title",
                value: cert.certificate_title ?? "—",
                testId: "drawer-cert-title",
              },
              {
                label: "Certificate Number",
                value: cert.certificate_number ?? "—",
                testId: "drawer-cert-number",
              },
              {
                label: "Issue Date",
                value: cert.issue_date ?? "—",
                testId: "drawer-issue-date",
              },
              {
                label: "Issued By",
                value: cert.issued_by ?? "—",
                testId: "drawer-issued-by",
              },
              {
                label: "Email",
                value: cert.participant_email ?? "—",
                testId: "drawer-email",
              },
              {
                label: "Download Count",
                value: String(cert.download_count),
                testId: "drawer-download-count",
              },
            ].map(({ label, value, testId }) => (
              <div key={label}>
                <p className="text-gray-500">{label}</p>
                <p data-testid={testId} className="font-medium">
                  {value}
                </p>
              </div>
            ))}
          </div>
        ) : null}

        {cert.verification_code && !editMode && (
          <div className="rounded bg-gray-50 p-3">
            <p className="mb-1 text-xs text-gray-500">Verification Code</p>
            <p
              data-testid="drawer-verification-code"
              className="font-mono text-sm"
            >
              {cert.verification_code}
            </p>
          </div>
        )}

        {cert.notes && !editMode && (
          <div>
            <p className="mb-1 text-xs text-gray-500">Notes</p>
            <p data-testid="drawer-notes" className="text-sm">
              {cert.notes}
            </p>
          </div>
        )}

        {editMode && (
          <form
            data-testid="drawer-edit-form"
            onSubmit={handleSave}
            className="space-y-3"
          >
            <div>
              <label className="mb-1 block text-sm font-medium">
                Certificate Title
              </label>
              <input
                data-testid="edit-cert-title"
                className="w-full rounded border px-3 py-2 text-sm"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Certificate Number
              </label>
              <input
                data-testid="edit-cert-number"
                className="w-full rounded border px-3 py-2 text-sm"
                value={editCertNumber}
                onChange={(e) => setEditCertNumber(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Issued By
              </label>
              <input
                data-testid="edit-issued-by"
                className="w-full rounded border px-3 py-2 text-sm"
                value={editIssuedBy}
                onChange={(e) => setEditIssuedBy(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Notes</label>
              <textarea
                data-testid="edit-notes"
                className="w-full rounded border px-3 py-2 text-sm"
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                rows={3}
              />
            </div>
            {updateMut.error && (
              <p data-testid="drawer-error" className="text-sm text-red-600">
                {updateMut.error.message}
              </p>
            )}
            <div className="flex gap-2">
              <button
                data-testid="btn-save-edit"
                type="submit"
                disabled={updateMut.isPending}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {updateMut.isPending ? "Saving…" : "Save"}
              </button>
              <button
                data-testid="btn-cancel-edit"
                type="button"
                onClick={() => setEditMode(false)}
                className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {!editMode && cert.status === "draft" && (
          <button
            data-testid="btn-edit-certificate"
            onClick={() => setEditMode(true)}
            className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
          >
            Edit
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  sessionId: string;
  workspaceId: string;
}

export function CertificateCenter({ sessionId, workspaceId }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<CertificateStatus | "">("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);

  const [createOpen, setCreateOpen] = useState(false);
  const [issueTarget, setIssueTarget] = useState<TrainingCertificate | null>(
    null,
  );
  const [revokeTarget, setRevokeTarget] =
    useState<TrainingCertificate | null>(null);
  const [drawerTarget, setDrawerTarget] =
    useState<TrainingCertificate | null>(null);

  const filters: TrainingCertificateFilters = {
    workspace_id: workspaceId,
    session_id: sessionId,
    status: statusFilter || undefined,
    search: search || undefined,
    cursor,
  };

  const { data, isLoading, isError } = useCertificateList(filters);

  const items = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? null;

  const kpiIssued = items.filter((c) => c.status === "issued").length;
  const kpiDraft = items.filter((c) => c.status === "draft").length;
  const kpiRevoked = items.filter((c) => c.status === "revoked").length;

  if (isLoading) {
    return (
      <div data-testid="certificate-loading" className="p-8 text-center text-gray-500">
        Loading certificates…
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="certificate-error" className="p-8 text-center text-red-500">
        Failed to load certificates.
      </div>
    );
  }

  return (
    <div data-testid="certificate-center" className="space-y-4">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div data-testid="kpi-total" className="rounded-lg border bg-white p-4">
          <p className="text-sm text-gray-500">Total</p>
          <p className="mt-1 text-2xl font-semibold">{total}</p>
        </div>
        <div data-testid="kpi-issued" className="rounded-lg border bg-white p-4">
          <p className="text-sm text-gray-500">Issued</p>
          <p className="mt-1 text-2xl font-semibold">{kpiIssued}</p>
        </div>
        <div data-testid="kpi-draft" className="rounded-lg border bg-white p-4">
          <p className="text-sm text-gray-500">Draft</p>
          <p className="mt-1 text-2xl font-semibold">{kpiDraft}</p>
        </div>
        <div data-testid="kpi-revoked" className="rounded-lg border bg-white p-4">
          <p className="text-sm text-gray-500">Revoked</p>
          <p className="mt-1 text-2xl font-semibold">{kpiRevoked}</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          data-testid="input-search"
          className="rounded border px-3 py-2 text-sm"
          placeholder="Search participant, cert number…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setCursor(undefined);
          }}
        />
        <select
          data-testid="select-status-filter"
          className="rounded border px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as CertificateStatus | "");
            setCursor(undefined);
          }}
        >
          <option value="">All statuses</option>
          {CERTIFICATE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button
          data-testid="btn-create-certificate"
          onClick={() => setCreateOpen(true)}
          className="ml-auto rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          + Certificate
        </button>
      </div>

      {/* Empty state */}
      {items.length === 0 ? (
        <div data-testid="certificate-empty" className="rounded-lg border p-12 text-center">
          <p className="text-gray-500">No certificates yet.</p>
          <button
            data-testid="btn-create-empty"
            onClick={() => setCreateOpen(true)}
            className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Create first certificate
          </button>
        </div>
      ) : (
        <>
          {/* Table */}
          <div
            data-testid="certificate-table"
            className="overflow-x-auto rounded-lg border"
          >
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3">Participant</th>
                  <th className="px-4 py-3">Cert Number</th>
                  <th className="px-4 py-3">Issue Date</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Verification</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((cert) => (
                  <tr
                    key={cert.id}
                    data-testid={`certificate-row-${cert.id}`}
                    className="hover:bg-gray-50"
                  >
                    <td className="px-4 py-3">
                      <button
                        className="text-left hover:underline"
                        onClick={() => setDrawerTarget(cert)}
                      >
                        {cert.participant_name}
                      </button>
                      {cert.participant_email && (
                        <p className="text-xs text-gray-400">
                          {cert.participant_email}
                        </p>
                      )}
                    </td>
                    <td
                      data-testid={`cert-number-${cert.id}`}
                      className="px-4 py-3 font-mono text-xs"
                    >
                      {cert.certificate_number ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {cert.issue_date ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <CertStatusBadge
                        status={cert.status}
                        testId={`status-badge-${cert.id}`}
                      />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {cert.verification_code ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        data-testid={`btn-action-${cert.id}`}
                        onClick={() => {
                          if (cert.status === "draft") setIssueTarget(cert);
                          else if (cert.status === "issued") setRevokeTarget(cert);
                          else setDrawerTarget(cert);
                        }}
                        className="rounded border px-2 py-1 text-xs hover:bg-gray-50"
                      >
                        {cert.status === "draft"
                          ? "Issue"
                          : cert.status === "issued"
                            ? "Revoke"
                            : "View"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Count + load more */}
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span data-testid="certificate-count">
              {total} certificate{total !== 1 ? "s" : ""}
            </span>
            {hasMore && (
              <button
                data-testid="btn-load-more"
                onClick={() => setCursor(nextCursor ?? undefined)}
                className="rounded border px-3 py-1 text-sm hover:bg-gray-50"
              >
                Load more
              </button>
            )}
          </div>
        </>
      )}

      {/* Dialogs */}
      {createOpen && (
        <CreateCertificateDialog
          sessionId={sessionId}
          workspaceId={workspaceId}
          onClose={() => setCreateOpen(false)}
        />
      )}
      {issueTarget && (
        <IssueCertificateDialog
          cert={issueTarget}
          workspaceId={workspaceId}
          onClose={() => setIssueTarget(null)}
        />
      )}
      {revokeTarget && (
        <RevokeCertificateDialog
          cert={revokeTarget}
          workspaceId={workspaceId}
          onClose={() => setRevokeTarget(null)}
        />
      )}

      {/* Drawer */}
      {drawerTarget && (
        <CertificateDrawer
          cert={drawerTarget}
          workspaceId={workspaceId}
          onClose={() => setDrawerTarget(null)}
        />
      )}
    </div>
  );
}
