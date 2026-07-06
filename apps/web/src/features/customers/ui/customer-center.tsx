"use client";

import { useState } from "react";
import {
  useCustomers,
  useCreateCustomer,
  useUpdateCustomer,
  useArchiveCustomer,
  useAssignOwner,
  useUpdateCustomerHealth,
} from "@/features/customers/api/use-customers";
import type {
  Customer,
  CustomerCreate,
  CustomerFilters,
  CustomerHealthStatus,
  CustomerStatus,
} from "@/features/customers/types";
import {
  CUSTOMER_HEALTH_STATUSES,
  CUSTOMER_STATUSES,
} from "@/features/customers/types";
import { useCustomerFeedback } from "@/features/training/api/use-training";

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusColor(status: CustomerStatus): string {
  switch (status) {
    case "active": return "bg-green-100 text-green-800";
    case "prospect": return "bg-blue-100 text-blue-800";
    case "inactive": return "bg-gray-100 text-gray-600";
    case "former": return "bg-red-100 text-red-700";
  }
}

function healthColor(health: CustomerHealthStatus): string {
  switch (health) {
    case "healthy": return "bg-green-100 text-green-800";
    case "attention": return "bg-yellow-100 text-yellow-800";
    case "at_risk": return "bg-red-100 text-red-700";
    case "inactive": return "bg-gray-100 text-gray-600";
  }
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

export function CustomerStatusBadge({ status }: { status: CustomerStatus }) {
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusColor(status)}`}
    >
      {status}
    </span>
  );
}

// ── HealthBadge ───────────────────────────────────────────────────────────────

export function CustomerHealthBadge({ health }: { health: CustomerHealthStatus }) {
  return (
    <span
      data-testid={`health-badge-${health}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${healthColor(health)}`}
    >
      {health.replace("_", " ")}
    </span>
  );
}

// ── KPI row ───────────────────────────────────────────────────────────────────

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

function KpiSection({ customers }: { customers: Customer[] }) {
  const active = customers.filter((c) => c.status === "active").length;
  const atRisk = customers.filter((c) => c.health_status === "at_risk").length;
  const prospects = customers.filter((c) => c.status === "prospect").length;
  const healthy = customers.filter((c) => c.health_status === "healthy").length;
  return (
    <div
      className="grid grid-cols-2 gap-4 md:grid-cols-4"
      data-testid="kpi-section"
    >
      <KpiCard label="Active" value={active} testId="kpi-active" />
      <KpiCard label="Prospects" value={prospects} testId="kpi-prospects" />
      <KpiCard label="At Risk" value={atRisk} testId="kpi-at-risk" />
      <KpiCard label="Healthy" value={healthy} testId="kpi-healthy" />
    </div>
  );
}

// ── Filters ───────────────────────────────────────────────────────────────────

interface FilterBarProps {
  search: string;
  status: string;
  health: string;
  onSearch: (v: string) => void;
  onStatus: (v: string) => void;
  onHealth: (v: string) => void;
}

function FilterBar({ search, status, health, onSearch, onStatus, onHealth }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="filter-bar">
      <input
        type="text"
        placeholder="Search customers…"
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
        {CUSTOMER_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select
        value={health}
        onChange={(e) => onHealth(e.target.value)}
        data-testid="health-select"
        className="rounded border px-3 py-1.5 text-sm"
      >
        <option value="">All health</option>
        {CUSTOMER_HEALTH_STATUSES.map((h) => (
          <option key={h} value={h}>
            {h.replace("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Customer table ────────────────────────────────────────────────────────────

function CustomerTable({
  customers,
  onSelect,
}: {
  customers: Customer[];
  onSelect: (c: Customer) => void;
}) {
  if (customers.length === 0) {
    return (
      <p data-testid="empty-state" className="py-8 text-center text-muted-foreground">
        No customers found.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border" data-testid="customer-table">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-2 text-left">Company</th>
            <th className="px-4 py-2 text-left">Industry</th>
            <th className="px-4 py-2 text-left">Status</th>
            <th className="px-4 py-2 text-left">Health</th>
            <th className="px-4 py-2 text-left">Contact</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr
              key={c.id}
              onClick={() => onSelect(c)}
              data-testid={`customer-row-${c.id}`}
              className="cursor-pointer border-t hover:bg-muted/30"
            >
              <td className="px-4 py-2 font-medium">{c.display_name}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.industry ?? "—"}</td>
              <td className="px-4 py-2">
                <CustomerStatusBadge status={c.status} />
              </td>
              <td className="px-4 py-2">
                <CustomerHealthBadge health={c.health_status} />
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {c.primary_contact_name ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Detail drawer ─────────────────────────────────────────────────────────────

interface DetailDrawerProps {
  customer: Customer;
  workspaceId: string;
  onClose: () => void;
  onArchive: (id: string) => void;
  onHealthChange: (id: string, h: CustomerHealthStatus) => void;
}

function DetailDrawer({
  customer,
  workspaceId,
  onClose,
  onArchive,
  onHealthChange,
}: DetailDrawerProps) {
  return (
    <div
      data-testid="detail-drawer"
      className="fixed right-0 top-0 h-full w-96 overflow-y-auto border-l bg-white p-6 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold" data-testid="drawer-company-name">
          {customer.display_name}
        </h2>
        <button onClick={onClose} data-testid="drawer-close" className="text-muted-foreground hover:text-foreground">
          ✕
        </button>
      </div>

      <div className="space-y-3 text-sm">
        <div>
          <span className="text-muted-foreground">Status: </span>
          <CustomerStatusBadge status={customer.status} />
        </div>
        <div>
          <span className="text-muted-foreground">Health: </span>
          <CustomerHealthBadge health={customer.health_status} />
        </div>
        {customer.industry && (
          <div>
            <span className="text-muted-foreground">Industry: </span>
            <span data-testid="drawer-industry">{customer.industry}</span>
          </div>
        )}
        {customer.email && (
          <div>
            <span className="text-muted-foreground">Email: </span>
            <span data-testid="drawer-email">{customer.email}</span>
          </div>
        )}
        {customer.website && (
          <div>
            <span className="text-muted-foreground">Website: </span>
            <span data-testid="drawer-website">{customer.website}</span>
          </div>
        )}
        {customer.notes && (
          <div>
            <span className="text-muted-foreground">Notes: </span>
            <span data-testid="drawer-notes">{customer.notes}</span>
          </div>
        )}
      </div>

      <div className="mt-6 space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Change health</p>
        <div className="flex flex-wrap gap-2">
          {CUSTOMER_HEALTH_STATUSES.map((h) => (
            <button
              key={h}
              onClick={() => onHealthChange(customer.id, h)}
              data-testid={`health-btn-${h}`}
              className="rounded border px-2 py-1 text-xs hover:bg-muted"
            >
              {h.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Feedback history */}
      <CustomerFeedbackHistory customerId={customer.id} workspaceId={workspaceId} />

      <div className="mt-6">
        <button
          onClick={() => onArchive(customer.id)}
          data-testid="archive-btn"
          className="w-full rounded border border-red-300 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
        >
          Archive customer
        </button>
      </div>
    </div>
  );
}

// ── Customer feedback history (read-only) ─────────────────────────────────────

export function CustomerFeedbackHistory({
  customerId,
  workspaceId,
}: {
  customerId: string;
  workspaceId: string;
}) {
  const { data, isLoading } = useCustomerFeedback(customerId, workspaceId);
  const items = data?.data ?? [];

  return (
    <div data-testid="customer-feedback-history" className="mt-6">
      <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Feedback History
      </p>
      {isLoading && (
        <p data-testid="feedback-history-loading" className="text-xs text-muted-foreground">
          Loading…
        </p>
      )}
      {!isLoading && items.length === 0 && (
        <p data-testid="feedback-history-empty" className="text-xs text-muted-foreground">
          No feedback recorded yet.
        </p>
      )}
      {!isLoading && items.length > 0 && (
        <ul data-testid="feedback-history-list" className="space-y-2">
          {items.map((f) => (
            <li
              key={f.id}
              data-testid="feedback-history-item"
              className="rounded border px-3 py-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">
                  {f.overall_rating != null ? `★ ${f.overall_rating}/5` : "No rating"}
                </span>
                <span className="text-muted-foreground">
                  {new Date(f.submitted_at).toLocaleDateString()}
                </span>
              </div>
              {f.comments && (
                <p data-testid="feedback-history-comment" className="mt-1 text-muted-foreground truncate">
                  {f.comments}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

interface CreateDialogProps {
  workspaceId: string;
  onClose: () => void;
  onCreate: (req: CustomerCreate) => void;
}

function CreateDialog({ workspaceId, onClose, onCreate }: CreateDialogProps) {
  const [companyName, setCompanyName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [industry, setIndustry] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!companyName || !displayName) return;
    onCreate({
      workspace_id: workspaceId,
      company_name: companyName,
      display_name: displayName,
      industry: industry || undefined,
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
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Add customer</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="text"
            placeholder="Company name *"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            data-testid="create-company-name"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Display name *"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            data-testid="create-display-name"
            required
            className="w-full rounded border px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            data-testid="create-industry"
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
              disabled={!companyName || !displayName}
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

interface CustomerCenterProps {
  workspaceId: string;
}

export function CustomerCenter({ workspaceId }: CustomerCenterProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [healthFilter, setHealthFilter] = useState<string>("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<Customer | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const filters: CustomerFilters = {
    workspace_id: workspaceId,
    ...(statusFilter ? { status: statusFilter as CustomerStatus } : {}),
    ...(healthFilter ? { health_status: healthFilter as CustomerHealthStatus } : {}),
    ...(search ? { search } : {}),
    ...(cursor ? { cursor } : {}),
  };

  const { data, isLoading, isError } = useCustomers(filters);
  const createMut = useCreateCustomer(workspaceId);
  const archiveMut = useArchiveCustomer(workspaceId);
  const healthMut = useUpdateCustomerHealth(workspaceId);

  const customers = data?.data?.items ?? [];
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? undefined;
  const total = data?.data?.total ?? 0;

  function handleArchive(id: string) {
    archiveMut.mutate(id, { onSuccess: () => setSelected(null) });
  }

  function handleHealthChange(id: string, health: CustomerHealthStatus) {
    healthMut.mutate({ id, body: { health_status: health } });
  }

  return (
    <div className="space-y-6" data-testid="customer-center">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Customers</h1>
          <p className="text-sm text-muted-foreground" data-testid="customer-total">
            {total} customer{total !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="add-customer-btn"
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          Add customer
        </button>
      </div>

      {/* KPIs */}
      <KpiSection customers={customers} />

      {/* Filters */}
      <FilterBar
        search={search}
        status={statusFilter}
        health={healthFilter}
        onSearch={(v) => { setSearch(v); setCursor(undefined); }}
        onStatus={(v) => { setStatusFilter(v); setCursor(undefined); }}
        onHealth={(v) => { setHealthFilter(v); setCursor(undefined); }}
      />

      {/* Table */}
      {isLoading && (
        <p data-testid="loading-state" className="py-8 text-center text-muted-foreground">
          Loading customers…
        </p>
      )}
      {isError && (
        <p data-testid="error-state" className="py-4 text-center text-red-600">
          Failed to load customers.
        </p>
      )}
      {!isLoading && !isError && (
        <CustomerTable customers={customers} onSelect={setSelected} />
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
          customer={selected}
          workspaceId={workspaceId}
          onClose={() => setSelected(null)}
          onArchive={handleArchive}
          onHealthChange={handleHealthChange}
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
    </div>
  );
}
