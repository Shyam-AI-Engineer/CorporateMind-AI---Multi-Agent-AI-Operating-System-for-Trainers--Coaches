"use client";

import { useState } from "react";
import {
  useCustomerRenewalList,
  useCreateCustomerRenewal,
  useUpdateCustomerRenewal,
  useAssignRenewalOwner,
  useUpdateRenewalStatus,
  useAttachProposal,
  useArchiveCustomerRenewal,
  useRenewalsByCustomer,
} from "@/features/customers/api/use-renewal";
import type {
  CustomerRenewal,
  CustomerRenewalCreate,
  CustomerRenewalFilters,
  RenewalStatus,
  RenewalType,
} from "@/features/customers/types-renewal";
import { RENEWAL_STATUSES, RENEWAL_TYPES } from "@/features/customers/types-renewal";

// ── StatusBadge ───────────────────────────────────────────────────────────────

function statusColor(s: RenewalStatus): string {
  switch (s) {
    case "planned":     return "bg-gray-100 text-gray-700";
    case "in_progress": return "bg-blue-100 text-blue-800";
    case "negotiation": return "bg-purple-100 text-purple-800";
    case "won":         return "bg-green-100 text-green-800";
    case "lost":        return "bg-red-100 text-red-700";
    case "cancelled":   return "bg-orange-100 text-orange-700";
  }
}

export function StatusBadge({ status }: { status: RenewalStatus }) {
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusColor(status)}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// ── ProbabilityBadge ──────────────────────────────────────────────────────────

export function ProbabilityBadge({ probability }: { probability: number | null }) {
  if (probability == null) return <span data-testid="probability-badge-null">—</span>;
  const color =
    probability >= 75
      ? "text-green-700"
      : probability >= 40
      ? "text-yellow-700"
      : "text-red-700";
  return (
    <span
      data-testid={`probability-badge-${probability}`}
      className={`text-xs font-medium ${color}`}
    >
      {probability}%
    </span>
  );
}

// ── KPI bar ───────────────────────────────────────────────────────────────────

export function RenewalKpiBar({ items }: { items: CustomerRenewal[] }) {
  const dueSoon = items.filter((i) => i.renewal_date != null).length;
  const pipelineValue = items.reduce(
    (sum, i) => sum + (i.contract_value ? parseFloat(i.contract_value) : 0),
    0
  );
  const expectedRevenue = items.reduce(
    (sum, i) => sum + (i.expected_value ? parseFloat(i.expected_value) : 0),
    0
  );
  const won = items.filter((i) => i.renewal_status === "won").length;
  const inProgress = items.filter((i) =>
    ["in_progress", "negotiation"].includes(i.renewal_status)
  ).length;
  const lost = items.filter((i) => i.renewal_status === "lost").length;

  return (
    <div className="grid grid-cols-3 gap-4 md:grid-cols-6" data-testid="renewal-kpi-bar">
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold" data-testid="kpi-due-soon">{dueSoon}</p>
        <p className="text-xs text-muted-foreground">Renewals Due</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold" data-testid="kpi-pipeline-value">
          ₹{pipelineValue.toLocaleString()}
        </p>
        <p className="text-xs text-muted-foreground">Pipeline Value</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-green-700" data-testid="kpi-expected-revenue">
          ₹{expectedRevenue.toLocaleString()}
        </p>
        <p className="text-xs text-muted-foreground">Expected Revenue</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-green-700" data-testid="kpi-won">{won}</p>
        <p className="text-xs text-muted-foreground">Won</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-blue-700" data-testid="kpi-in-progress">{inProgress}</p>
        <p className="text-xs text-muted-foreground">In Progress</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-lg font-bold text-red-700" data-testid="kpi-lost">{lost}</p>
        <p className="text-xs text-muted-foreground">Lost</p>
      </div>
    </div>
  );
}

// ── FilterBar ─────────────────────────────────────────────────────────────────

interface RenewalFilterBarProps {
  search: string;
  status: string;
  type: string;
  onSearch: (v: string) => void;
  onStatus: (v: string) => void;
  onType: (v: string) => void;
}

export function RenewalFilterBar({
  search,
  status,
  type,
  onSearch,
  onStatus,
  onType,
}: RenewalFilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3" data-testid="renewal-filter-bar">
      <input
        type="text"
        placeholder="Search contract name or notes…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        data-testid="renewal-search-input"
        className="rounded border px-3 py-2 text-sm"
      />
      <select
        value={status}
        onChange={(e) => onStatus(e.target.value)}
        data-testid="renewal-status-filter"
        className="rounded border px-3 py-2 text-sm"
      >
        <option value="">All statuses</option>
        {RENEWAL_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
      <select
        value={type}
        onChange={(e) => onType(e.target.value)}
        data-testid="renewal-type-filter"
        className="rounded border px-3 py-2 text-sm"
      >
        <option value="">All types</option>
        {RENEWAL_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Renewal table ─────────────────────────────────────────────────────────────

interface RenewalTableProps {
  records: CustomerRenewal[];
  onSelect: (r: CustomerRenewal) => void;
}

export function RenewalTable({ records, onSelect }: RenewalTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border" data-testid="renewal-table">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Contract</th>
            <th className="px-4 py-3 text-left font-medium">Type</th>
            <th className="px-4 py-3 text-left font-medium">Status</th>
            <th className="px-4 py-3 text-left font-medium">Renewal Date</th>
            <th className="px-4 py-3 text-left font-medium">Probability</th>
            <th className="px-4 py-3 text-left font-medium">Value</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 && (
            <tr>
              <td
                colSpan={6}
                className="py-8 text-center text-muted-foreground"
                data-testid="renewal-empty-state"
              >
                No renewals found.
              </td>
            </tr>
          )}
          {records.map((r) => (
            <tr
              key={r.id}
              data-testid="renewal-row"
              className="cursor-pointer border-t hover:bg-muted/30"
              onClick={() => onSelect(r)}
            >
              <td className="px-4 py-3 font-medium" data-testid="row-contract-name">
                {r.contract_name ?? "—"}
              </td>
              <td className="px-4 py-3" data-testid="row-type">{r.renewal_type}</td>
              <td className="px-4 py-3">
                <StatusBadge status={r.renewal_status} />
              </td>
              <td className="px-4 py-3" data-testid="row-renewal-date">
                {r.renewal_date ?? "—"}
              </td>
              <td className="px-4 py-3">
                <ProbabilityBadge probability={r.probability} />
              </td>
              <td className="px-4 py-3" data-testid="row-value">
                {r.contract_value ? `₹${parseFloat(r.contract_value).toLocaleString()}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── StatusUpdateDialog ────────────────────────────────────────────────────────

interface StatusUpdateDialogProps {
  currentStatus: RenewalStatus;
  onClose: () => void;
  onUpdate: (status: RenewalStatus) => void;
  isPending: boolean;
}

export function StatusUpdateDialog({
  currentStatus,
  onClose,
  onUpdate,
  isPending,
}: StatusUpdateDialogProps) {
  const [selected, setSelected] = useState<RenewalStatus>(currentStatus);

  return (
    <div
      data-testid="status-update-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Update renewal status</h2>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value as RenewalStatus)}
          data-testid="status-select"
          className="w-full rounded border px-3 py-2 text-sm"
        >
          {RENEWAL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            data-testid="status-cancel"
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onUpdate(selected)}
            data-testid="status-submit"
            disabled={isPending}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isPending ? "Saving…" : "Update"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── ProposalAttachDialog ──────────────────────────────────────────────────────

interface ProposalAttachDialogProps {
  onClose: () => void;
  onAttach: (proposalId: string) => void;
  isPending: boolean;
}

export function ProposalAttachDialog({
  onClose,
  onAttach,
  isPending,
}: ProposalAttachDialogProps) {
  const [proposalId, setProposalId] = useState("");

  return (
    <div
      data-testid="proposal-attach-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Attach proposal</h2>
        <input
          type="text"
          placeholder="Proposal ID *"
          value={proposalId}
          onChange={(e) => setProposalId(e.target.value)}
          data-testid="proposal-id-input"
          className="w-full rounded border px-3 py-2 text-sm"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            data-testid="proposal-cancel"
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => proposalId.trim() && onAttach(proposalId.trim())}
            data-testid="proposal-submit"
            disabled={!proposalId.trim() || isPending}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isPending ? "Attaching…" : "Attach"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── RenewalDrawer ─────────────────────────────────────────────────────────────

interface RenewalDrawerProps {
  record: CustomerRenewal;
  workspaceId: string;
  onClose: () => void;
}

export function RenewalDrawer({ record, workspaceId, onClose }: RenewalDrawerProps) {
  const [showStatus, setShowStatus] = useState(false);
  const [showProposal, setShowProposal] = useState(false);

  const statusMut = useUpdateRenewalStatus(workspaceId);
  const proposalMut = useAttachProposal(workspaceId);
  const ownerMut = useAssignRenewalOwner(workspaceId);
  const archiveMut = useArchiveCustomerRenewal(workspaceId);

  const [ownerId, setOwnerId] = useState("");

  return (
    <div
      data-testid="renewal-drawer"
      className="fixed right-0 top-0 h-full w-96 overflow-y-auto border-l bg-white p-6 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold" data-testid="drawer-contract-name">
          {record.contract_name ?? "Renewal"}
        </h2>
        <button
          onClick={onClose}
          data-testid="renewal-drawer-close"
          className="text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </div>

      <div className="space-y-3 text-sm">
        <div>
          <span className="text-muted-foreground">Status: </span>
          <StatusBadge status={record.renewal_status} />
        </div>
        <div>
          <span className="text-muted-foreground">Type: </span>
          <span data-testid="drawer-renewal-type">{record.renewal_type}</span>
        </div>
        {record.renewal_date && (
          <div>
            <span className="text-muted-foreground">Renewal date: </span>
            <span data-testid="drawer-renewal-date">{record.renewal_date}</span>
          </div>
        )}
        {record.contract_value && (
          <div>
            <span className="text-muted-foreground">Contract value: </span>
            <span data-testid="drawer-contract-value">
              ₹{parseFloat(record.contract_value).toLocaleString()}
            </span>
          </div>
        )}
        {record.expected_value && (
          <div>
            <span className="text-muted-foreground">Expected value: </span>
            <span data-testid="drawer-expected-value">
              ₹{parseFloat(record.expected_value).toLocaleString()}
            </span>
          </div>
        )}
        <div>
          <span className="text-muted-foreground">Probability: </span>
          <ProbabilityBadge probability={record.probability} />
        </div>
        {record.proposal_id && (
          <div>
            <span className="text-muted-foreground">Proposal: </span>
            <span data-testid="drawer-proposal-id">{record.proposal_id.slice(0, 8)}…</span>
          </div>
        )}
        {record.notes && (
          <div>
            <span className="text-muted-foreground">Notes: </span>
            <span data-testid="drawer-notes">{record.notes}</span>
          </div>
        )}
      </div>

      {/* Assign owner inline */}
      <div className="mt-6 space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Assign owner</p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Owner user ID"
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value)}
            data-testid="drawer-owner-input"
            className="flex-1 rounded border px-2 py-1 text-xs"
          />
          <button
            data-testid="drawer-assign-owner-btn"
            disabled={!ownerId.trim() || ownerMut.isPending}
            onClick={() =>
              ownerMut.mutate(
                {
                  id: record.id,
                  body: { owner_user_id: ownerId.trim() },
                  customerId: record.customer_id,
                },
                { onSuccess: () => setOwnerId("") }
              )
            }
            className="rounded bg-gray-100 px-2 py-1 text-xs hover:bg-gray-200 disabled:opacity-50"
          >
            Assign
          </button>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-4 flex gap-2">
        <button
          data-testid="update-status-btn"
          onClick={() => setShowStatus(true)}
          className="rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Update status
        </button>
        <button
          data-testid="attach-proposal-btn"
          onClick={() => setShowProposal(true)}
          className="rounded border px-3 py-2 text-sm hover:bg-muted"
        >
          Attach proposal
        </button>
      </div>

      {!record.is_archived && (
        <div className="mt-6">
          <button
            data-testid="renewal-archive-btn"
            onClick={() => archiveMut.mutate(record.id)}
            className="w-full rounded border border-red-300 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
          >
            Archive
          </button>
        </div>
      )}

      {showStatus && (
        <StatusUpdateDialog
          currentStatus={record.renewal_status}
          onClose={() => setShowStatus(false)}
          onUpdate={(s) =>
            statusMut.mutate(
              {
                id: record.id,
                body: { renewal_status: s },
                customerId: record.customer_id,
              },
              { onSuccess: () => setShowStatus(false) }
            )
          }
          isPending={statusMut.isPending}
        />
      )}

      {showProposal && (
        <ProposalAttachDialog
          onClose={() => setShowProposal(false)}
          onAttach={(pid) =>
            proposalMut.mutate(
              {
                id: record.id,
                body: { proposal_id: pid },
                customerId: record.customer_id,
              },
              { onSuccess: () => setShowProposal(false) }
            )
          }
          isPending={proposalMut.isPending}
        />
      )}
    </div>
  );
}

// ── RenewalDialog ─────────────────────────────────────────────────────────────

interface RenewalDialogProps {
  workspaceId: string;
  customerId?: string;
  onClose: () => void;
  onCreate: (req: CustomerRenewalCreate) => void;
  isPending: boolean;
}

export function RenewalDialog({
  workspaceId,
  customerId,
  onClose,
  onCreate,
  isPending,
}: RenewalDialogProps) {
  const [cid, setCid] = useState(customerId ?? "");
  const [contractName, setContractName] = useState("");
  const [renewalType, setRenewalType] = useState<RenewalType>("annual");
  const [renewalDate, setRenewalDate] = useState("");
  const [probability, setProbability] = useState("");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!cid.trim()) return;
    onCreate({
      workspace_id: workspaceId,
      customer_id: cid.trim(),
      contract_name: contractName || undefined,
      renewal_type: renewalType,
      renewal_date: renewalDate || undefined,
      probability: probability ? parseInt(probability, 10) : undefined,
      notes: notes || undefined,
    });
  }

  return (
    <div
      data-testid="renewal-dialog"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">New renewal</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Customer ID *"
            value={cid}
            onChange={(e) => setCid(e.target.value)}
            data-testid="renewal-customer-id"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Contract name"
            value={contractName}
            onChange={(e) => setContractName(e.target.value)}
            data-testid="renewal-contract-name"
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <select
            value={renewalType}
            onChange={(e) => setRenewalType(e.target.value as RenewalType)}
            data-testid="renewal-type-select"
            className="w-full rounded border px-3 py-2 text-sm"
          >
            {RENEWAL_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            type="date"
            value={renewalDate}
            onChange={(e) => setRenewalDate(e.target.value)}
            data-testid="renewal-date-input"
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="number"
            placeholder="Probability 0–100"
            min={0}
            max={100}
            value={probability}
            onChange={(e) => setProbability(e.target.value)}
            data-testid="renewal-probability-input"
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <textarea
            placeholder="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="renewal-notes"
            rows={2}
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid="renewal-cancel"
              className="rounded border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="renewal-submit"
              disabled={!cid.trim() || isPending}
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

interface RenewalCenterProps {
  workspaceId: string;
}

export function RenewalCenter({ workspaceId }: RenewalCenterProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<CustomerRenewal | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const filters: CustomerRenewalFilters = {
    workspace_id: workspaceId,
    ...(statusFilter ? { renewal_status: statusFilter as RenewalStatus } : {}),
    ...(typeFilter ? { renewal_type: typeFilter as RenewalType } : {}),
    ...(search ? { search } : {}),
    ...(cursor ? { cursor } : {}),
  };

  const { data, isLoading, isError } = useCustomerRenewalList(filters);
  const createMut = useCreateCustomerRenewal(workspaceId);

  const records = data?.data?.items ?? [];
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? undefined;
  const total = data?.data?.total ?? 0;

  return (
    <div className="space-y-6" data-testid="renewal-center">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Renewals</h1>
          <p className="text-sm text-muted-foreground" data-testid="renewal-total">
            {total} renewal{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="add-renewal-btn"
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          New renewal
        </button>
      </div>

      {/* KPIs */}
      <RenewalKpiBar items={records} />

      {/* Filters */}
      <RenewalFilterBar
        search={search}
        status={statusFilter}
        type={typeFilter}
        onSearch={(v) => { setSearch(v); setCursor(undefined); }}
        onStatus={(v) => { setStatusFilter(v); setCursor(undefined); }}
        onType={(v) => { setTypeFilter(v); setCursor(undefined); }}
      />

      {/* Table */}
      {isLoading && (
        <p data-testid="renewal-loading" className="py-8 text-center text-muted-foreground">
          Loading…
        </p>
      )}
      {isError && (
        <p data-testid="renewal-error" className="py-4 text-center text-red-600">
          Failed to load renewals.
        </p>
      )}
      {!isLoading && !isError && (
        <RenewalTable records={records} onSelect={setSelected} />
      )}

      {/* Pagination */}
      {hasMore && (
        <div className="flex justify-center">
          <button
            onClick={() => setCursor(nextCursor)}
            data-testid="renewal-load-more"
            className="rounded border px-4 py-2 text-sm hover:bg-muted"
          >
            Load more
          </button>
        </div>
      )}

      {/* Drawer */}
      {selected && (
        <RenewalDrawer
          record={selected}
          workspaceId={workspaceId}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Create dialog */}
      {showCreate && (
        <RenewalDialog
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreate={(req) =>
            createMut.mutate(req, { onSuccess: () => setShowCreate(false) })
          }
          isPending={createMut.isPending}
        />
      )}
    </div>
  );
}

// ── NextRenewalCard — read-only summary for customer success view ──────────────

export function NextRenewalCard({
  customerId,
  workspaceId,
}: {
  customerId: string;
  workspaceId: string;
}) {
  const { data, isLoading } = useRenewalsByCustomer(customerId, workspaceId);
  const items = data?.data?.items ?? [];
  // Pick the first non-won/lost/cancelled renewal sorted by renewal_date
  const next = items.find((i) =>
    ["planned", "in_progress", "negotiation"].includes(i.renewal_status)
  );

  return (
    <div data-testid="next-renewal-card" className="mt-4">
      <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Next Renewal
      </p>
      {isLoading && (
        <p data-testid="next-renewal-loading" className="text-xs text-muted-foreground">
          Loading…
        </p>
      )}
      {!isLoading && !next && (
        <p data-testid="next-renewal-empty" className="text-xs text-muted-foreground">
          No upcoming renewals.
        </p>
      )}
      {!isLoading && next && (
        <div
          data-testid="next-renewal-summary"
          className="rounded border px-3 py-2 text-xs space-y-1"
        >
          <div className="flex items-center gap-2">
            <StatusBadge status={next.renewal_status} />
            <span data-testid="next-renewal-type">{next.renewal_type}</span>
          </div>
          {next.contract_name && (
            <p data-testid="next-renewal-contract">{next.contract_name}</p>
          )}
          {next.renewal_date && (
            <p>
              Due: <span data-testid="next-renewal-date">{next.renewal_date}</span>
            </p>
          )}
          {next.probability != null && (
            <p>
              Probability:{" "}
              <span data-testid="next-renewal-probability">{next.probability}%</span>
            </p>
          )}
          {next.expected_value && (
            <p>
              Expected:{" "}
              <span data-testid="next-renewal-expected-value">
                ₹{parseFloat(next.expected_value).toLocaleString()}
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
