"use client";

import { useState } from "react";
import {
  useCustomerSuccessList,
  useCreateCustomerSuccess,
  useUpdateCustomerSuccess,
  useAssignSuccessOwner,
  useUpdateSuccessHealth,
  useScheduleFollowup,
  useArchiveCustomerSuccess,
  useCustomerSuccessByCustomer,
} from "@/features/customers/api/use-customer-success";
import { NextRenewalCard } from "@/features/customers/ui/renewal-center";
import type {
  CustomerSuccess,
  CustomerSuccessCreate,
  CustomerSuccessFilters,
  CustomerSuccessUpdate,
  HealthStatus,
  RiskLevel,
} from "@/features/customers/types-success";
import { HEALTH_STATUSES, RISK_LEVELS } from "@/features/customers/types-success";

// ── HealthBadge ───────────────────────────────────────────────────────────────

function healthColor(h: HealthStatus): string {
  switch (h) {
    case "healthy": return "bg-green-100 text-green-800";
    case "watch": return "bg-yellow-100 text-yellow-800";
    case "at_risk": return "bg-red-100 text-red-700";
  }
}

export function HealthBadge({ status }: { status: HealthStatus }) {
  return (
    <span
      data-testid={`health-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${healthColor(status)}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// ── RiskBadge ─────────────────────────────────────────────────────────────────

function riskColor(r: RiskLevel): string {
  switch (r) {
    case "low": return "bg-blue-100 text-blue-800";
    case "medium": return "bg-orange-100 text-orange-800";
    case "high": return "bg-red-100 text-red-700";
  }
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span
      data-testid={`risk-badge-${level}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${riskColor(level)}`}
    >
      {level} risk
    </span>
  );
}

// ── KPI bar ───────────────────────────────────────────────────────────────────

export function KpiBar({ items }: { items: CustomerSuccess[] }) {
  const healthy = items.filter((i) => i.health_status === "healthy").length;
  const watch = items.filter((i) => i.health_status === "watch").length;
  const at_risk = items.filter((i) => i.health_status === "at_risk").length;
  const renewalDue = items.filter((i) => i.renewal_date != null).length;
  const followupDue = items.filter((i) => i.next_followup_date != null).length;
  const expansion = items.filter((i) => i.expansion_opportunity).length;

  return (
    <div className="grid grid-cols-3 gap-4 md:grid-cols-6" data-testid="kpi-bar">
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-green-700" data-testid="kpi-healthy">{healthy}</p>
        <p className="text-xs text-muted-foreground">Healthy</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-yellow-700" data-testid="kpi-watch">{watch}</p>
        <p className="text-xs text-muted-foreground">Watch</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-red-700" data-testid="kpi-at-risk">{at_risk}</p>
        <p className="text-xs text-muted-foreground">At risk</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold" data-testid="kpi-renewal">{renewalDue}</p>
        <p className="text-xs text-muted-foreground">Renewals</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold" data-testid="kpi-followup">{followupDue}</p>
        <p className="text-xs text-muted-foreground">Follow-ups</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-blue-700" data-testid="kpi-expansion">{expansion}</p>
        <p className="text-xs text-muted-foreground">Expansion</p>
      </div>
    </div>
  );
}

// ── FilterBar ─────────────────────────────────────────────────────────────────

interface FilterBarProps {
  search: string;
  health: string;
  risk: string;
  onSearch: (v: string) => void;
  onHealth: (v: string) => void;
  onRisk: (v: string) => void;
}

export function FilterBar({ search, health, risk, onSearch, onHealth, onRisk }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3" data-testid="filter-bar">
      <input
        type="text"
        placeholder="Search notes…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        data-testid="search-input"
        className="rounded border px-3 py-2 text-sm"
      />
      <select
        value={health}
        onChange={(e) => onHealth(e.target.value)}
        data-testid="health-filter"
        className="rounded border px-3 py-2 text-sm"
      >
        <option value="">All health</option>
        {HEALTH_STATUSES.map((h) => (
          <option key={h} value={h}>{h.replace("_", " ")}</option>
        ))}
      </select>
      <select
        value={risk}
        onChange={(e) => onRisk(e.target.value)}
        data-testid="risk-filter"
        className="rounded border px-3 py-2 text-sm"
      >
        <option value="">All risk</option>
        {RISK_LEVELS.map((r) => (
          <option key={r} value={r}>{r} risk</option>
        ))}
      </select>
    </div>
  );
}

// ── Success table ─────────────────────────────────────────────────────────────

interface SuccessTableProps {
  records: CustomerSuccess[];
  onSelect: (r: CustomerSuccess) => void;
}

export function SuccessTable({ records, onSelect }: SuccessTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border" data-testid="success-table">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Customer</th>
            <th className="px-4 py-3 text-left font-medium">Health</th>
            <th className="px-4 py-3 text-left font-medium">Risk</th>
            <th className="px-4 py-3 text-left font-medium">Score</th>
            <th className="px-4 py-3 text-left font-medium">Renewal</th>
            <th className="px-4 py-3 text-left font-medium">Follow-up</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 && (
            <tr>
              <td colSpan={6} className="py-8 text-center text-muted-foreground" data-testid="empty-state">
                No customer success records found.
              </td>
            </tr>
          )}
          {records.map((r) => (
            <tr
              key={r.id}
              data-testid="success-row"
              className="cursor-pointer border-t hover:bg-muted/30"
              onClick={() => onSelect(r)}
            >
              <td className="px-4 py-3 font-medium" data-testid="row-customer-id">
                {r.customer_id.slice(0, 8)}…
              </td>
              <td className="px-4 py-3">
                <HealthBadge status={r.health_status} />
              </td>
              <td className="px-4 py-3">
                <RiskBadge level={r.risk_level} />
              </td>
              <td className="px-4 py-3" data-testid="row-score">
                {r.health_score ?? "—"}
              </td>
              <td className="px-4 py-3" data-testid="row-renewal">
                {r.renewal_date ?? "—"}
              </td>
              <td className="px-4 py-3" data-testid="row-followup">
                {r.next_followup_date ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── FollowupDialog ────────────────────────────────────────────────────────────

interface FollowupDialogProps {
  onClose: () => void;
  onSchedule: (date: string) => void;
  isPending: boolean;
}

export function FollowupDialog({ onClose, onSchedule, isPending }: FollowupDialogProps) {
  const [date, setDate] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!date) return;
    onSchedule(date);
  }

  return (
    <div
      data-testid="followup-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Schedule follow-up</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            data-testid="followup-date-input"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="followup-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="followup-submit"
              disabled={!date || isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isPending ? "Saving…" : "Schedule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── OwnerAssignmentDialog ─────────────────────────────────────────────────────

interface OwnerAssignmentDialogProps {
  onClose: () => void;
  onAssign: (ownerId: string) => void;
  isPending: boolean;
}

export function OwnerAssignmentDialog({
  onClose,
  onAssign,
  isPending,
}: OwnerAssignmentDialogProps) {
  const [ownerId, setOwnerId] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ownerId.trim()) return;
    onAssign(ownerId.trim());
  }

  return (
    <div
      data-testid="owner-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Assign owner</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Owner user ID *"
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value)}
            data-testid="owner-id-input"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="owner-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="owner-submit"
              disabled={!ownerId.trim() || isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isPending ? "Saving…" : "Assign"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── CustomerSuccessDrawer ─────────────────────────────────────────────────────

interface DrawerProps {
  record: CustomerSuccess;
  workspaceId: string;
  onClose: () => void;
}

export function CustomerSuccessDrawer({ record, workspaceId, onClose }: DrawerProps) {
  const [showFollowup, setShowFollowup] = useState(false);
  const [showOwner, setShowOwner] = useState(false);

  const healthMut = useUpdateSuccessHealth(workspaceId);
  const followupMut = useScheduleFollowup(workspaceId);
  const ownerMut = useAssignSuccessOwner(workspaceId);
  const archiveMut = useArchiveCustomerSuccess(workspaceId);

  return (
    <div
      data-testid="success-drawer"
      className="fixed right-0 top-0 h-full w-96 overflow-y-auto border-l bg-white p-6 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold" data-testid="drawer-customer-id">
          {record.customer_id.slice(0, 8)}…
        </h2>
        <button
          onClick={onClose}
          data-testid="drawer-close"
          className="text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </div>

      <div className="space-y-3 text-sm">
        <div>
          <span className="text-muted-foreground">Health: </span>
          <HealthBadge status={record.health_status} />
        </div>
        <div>
          <span className="text-muted-foreground">Risk: </span>
          <RiskBadge level={record.risk_level} />
        </div>
        {record.health_score != null && (
          <div>
            <span className="text-muted-foreground">Score: </span>
            <span data-testid="drawer-score">{record.health_score}</span>
          </div>
        )}
        {record.renewal_date && (
          <div>
            <span className="text-muted-foreground">Renewal: </span>
            <span data-testid="drawer-renewal">{record.renewal_date}</span>
          </div>
        )}
        {record.next_followup_date && (
          <div>
            <span className="text-muted-foreground">Follow-up: </span>
            <span data-testid="drawer-followup">{record.next_followup_date}</span>
          </div>
        )}
        {record.renewal_probability != null && (
          <div>
            <span className="text-muted-foreground">Renewal prob.: </span>
            <span data-testid="drawer-renewal-prob">{record.renewal_probability}%</span>
          </div>
        )}
        {record.expansion_opportunity && (
          <div data-testid="drawer-expansion" className="text-blue-700 font-medium">
            Expansion opportunity
          </div>
        )}
        {record.notes && (
          <div>
            <span className="text-muted-foreground">Notes: </span>
            <span data-testid="drawer-notes">{record.notes}</span>
          </div>
        )}
      </div>

      {/* Next renewal summary */}
      <NextRenewalCard customerId={record.customer_id} workspaceId={workspaceId} />

      {/* Health change */}
      <div className="mt-6 space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Change health</p>
        <div className="flex flex-wrap gap-2">
          {HEALTH_STATUSES.map((h) => (
            <button
              key={h}
              data-testid={`health-change-btn-${h}`}
              onClick={() =>
                healthMut.mutate({
                  id: record.id,
                  body: { health_status: h },
                  customerId: record.customer_id,
                })
              }
              className="rounded border px-2 py-1 text-xs hover:bg-muted"
            >
              {h.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="mt-4 flex gap-2">
        <button
          data-testid="schedule-followup-btn"
          onClick={() => setShowFollowup(true)}
          className="rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Schedule follow-up
        </button>
        <button
          data-testid="assign-owner-btn"
          onClick={() => setShowOwner(true)}
          className="rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Assign owner
        </button>
      </div>

      {!record.is_archived && (
        <div className="mt-6">
          <button
            data-testid="archive-btn"
            onClick={() => archiveMut.mutate(record.id)}
            className="w-full rounded border border-red-300 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
          >
            Archive
          </button>
        </div>
      )}

      {showFollowup && (
        <FollowupDialog
          onClose={() => setShowFollowup(false)}
          onSchedule={(date) =>
            followupMut.mutate(
              {
                id: record.id,
                body: { next_followup_date: date },
                customerId: record.customer_id,
              },
              { onSuccess: () => setShowFollowup(false) }
            )
          }
          isPending={followupMut.isPending}
        />
      )}

      {showOwner && (
        <OwnerAssignmentDialog
          onClose={() => setShowOwner(false)}
          onAssign={(ownerId) =>
            ownerMut.mutate(
              {
                id: record.id,
                body: { owner_user_id: ownerId },
                customerId: record.customer_id,
              },
              { onSuccess: () => setShowOwner(false) }
            )
          }
          isPending={ownerMut.isPending}
        />
      )}
    </div>
  );
}

// ── CreateDialog ──────────────────────────────────────────────────────────────

interface CreateDialogProps {
  workspaceId: string;
  onClose: () => void;
  onCreate: (req: CustomerSuccessCreate) => void;
  isPending: boolean;
}

export function CreateSuccessDialog({
  workspaceId,
  onClose,
  onCreate,
  isPending,
}: CreateDialogProps) {
  const [customerId, setCustomerId] = useState("");
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("watch");
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("medium");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!customerId.trim()) return;
    onCreate({
      workspace_id: workspaceId,
      customer_id: customerId.trim(),
      health_status: healthStatus,
      risk_level: riskLevel,
      notes: notes || undefined,
    });
  }

  return (
    <div
      data-testid="create-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Add customer success record</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Customer ID *"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            data-testid="create-customer-id"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <select
            value={healthStatus}
            onChange={(e) => setHealthStatus(e.target.value as HealthStatus)}
            data-testid="create-health-status"
            className="w-full rounded border px-3 py-2 text-sm"
          >
            {HEALTH_STATUSES.map((h) => (
              <option key={h} value={h}>{h.replace("_", " ")}</option>
            ))}
          </select>
          <select
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value as RiskLevel)}
            data-testid="create-risk-level"
            className="w-full rounded border px-3 py-2 text-sm"
          >
            {RISK_LEVELS.map((r) => (
              <option key={r} value={r}>{r} risk</option>
            ))}
          </select>
          <textarea
            placeholder="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="create-notes"
            rows={3}
            className="w-full rounded border px-3 py-2 text-sm"
          />
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
              disabled={!customerId.trim() || isPending}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isPending ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface CustomerSuccessCenterProps {
  workspaceId: string;
}

export function CustomerSuccessCenter({ workspaceId }: CustomerSuccessCenterProps) {
  const [search, setSearch] = useState("");
  const [healthFilter, setHealthFilter] = useState<string>("");
  const [riskFilter, setRiskFilter] = useState<string>("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<CustomerSuccess | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const filters: CustomerSuccessFilters = {
    workspace_id: workspaceId,
    ...(healthFilter ? { health_status: healthFilter as HealthStatus } : {}),
    ...(riskFilter ? { risk_level: riskFilter as RiskLevel } : {}),
    ...(search ? { search } : {}),
    ...(cursor ? { cursor } : {}),
  };

  const { data, isLoading, isError } = useCustomerSuccessList(filters);
  const createMut = useCreateCustomerSuccess(workspaceId);

  const records = data?.data?.items ?? [];
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? undefined;
  const total = data?.data?.total ?? 0;

  return (
    <div className="space-y-6" data-testid="customer-success-center">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Customer Success</h1>
          <p className="text-sm text-muted-foreground" data-testid="success-total">
            {total} record{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="add-record-btn"
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          Add record
        </button>
      </div>

      {/* KPIs */}
      <KpiBar items={records} />

      {/* Filters */}
      <FilterBar
        search={search}
        health={healthFilter}
        risk={riskFilter}
        onSearch={(v) => { setSearch(v); setCursor(undefined); }}
        onHealth={(v) => { setHealthFilter(v); setCursor(undefined); }}
        onRisk={(v) => { setRiskFilter(v); setCursor(undefined); }}
      />

      {/* Table */}
      {isLoading && (
        <p data-testid="loading-state" className="py-8 text-center text-muted-foreground">
          Loading…
        </p>
      )}
      {isError && (
        <p data-testid="error-state" className="py-4 text-center text-red-600">
          Failed to load customer success records.
        </p>
      )}
      {!isLoading && !isError && (
        <SuccessTable records={records} onSelect={setSelected} />
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

      {/* Drawer */}
      {selected && (
        <CustomerSuccessDrawer
          record={selected}
          workspaceId={workspaceId}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Create dialog */}
      {showCreate && (
        <CreateSuccessDialog
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreate={(req) => createMut.mutate(req, { onSuccess: () => setShowCreate(false) })}
          isPending={createMut.isPending}
        />
      )}
    </div>
  );
}

// ── CustomerSuccessSummary — read-only health card for customer detail view ───

export function CustomerSuccessSummary({ customerId }: { customerId: string }) {
  const { data, isLoading } = useCustomerSuccessByCustomer(customerId);
  const record = data?.data;

  return (
    <div data-testid="customer-success-summary" className="mt-6">
      <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Customer Success
      </p>
      {isLoading && (
        <p data-testid="success-summary-loading" className="text-xs text-muted-foreground">
          Loading…
        </p>
      )}
      {!isLoading && !record && (
        <p data-testid="success-summary-empty" className="text-xs text-muted-foreground">
          No success record yet.
        </p>
      )}
      {!isLoading && record && (
        <div data-testid="success-summary-card" className="rounded border px-3 py-2 text-xs space-y-1">
          <div className="flex items-center gap-2">
            <HealthBadge status={record.health_status} />
            <RiskBadge level={record.risk_level} />
          </div>
          {record.health_score != null && (
            <p>Score: <span data-testid="success-summary-score">{record.health_score}</span></p>
          )}
          {record.renewal_date && (
            <p>Renewal: <span data-testid="success-summary-renewal">{record.renewal_date}</span></p>
          )}
          {record.next_followup_date && (
            <p>Follow-up: <span data-testid="success-summary-followup">{record.next_followup_date}</span></p>
          )}
        </div>
      )}
    </div>
  );
}
