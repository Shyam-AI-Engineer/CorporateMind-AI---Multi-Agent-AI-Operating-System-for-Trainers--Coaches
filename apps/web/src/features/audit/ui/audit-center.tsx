"use client";

import React, { useState } from "react";
import {
  useAuditEvents,
  useAuditEvent,
  useEntityAuditEvents,
  useAuditStatistics,
} from "@/features/audit/api/use-audit";
import type {
  AuditLog,
  AuditLogFilters,
  AuditSeverity,
  AuditStatisticsOut,
} from "@/features/audit/types-audit";
import { AUDIT_SEVERITIES } from "@/features/audit/types-audit";

// ── SeverityBadge ─────────────────────────────────────────────────────────────

interface SeverityBadgeProps {
  severity: AuditSeverity | string;
}

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  critical: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const cls = SEVERITY_STYLES[severity] ?? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200";
  return (
    <span
      data-testid="severity-badge"
      data-severity={severity}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {severity}
    </span>
  );
}

// ── StatisticsCards ───────────────────────────────────────────────────────────

interface StatisticsCardsProps {
  workspaceId: string;
  periodDays?: number;
}

export function StatisticsCards({ workspaceId, periodDays = 30 }: StatisticsCardsProps) {
  const { data, isLoading, isError } = useAuditStatistics(workspaceId, periodDays);

  if (isLoading) {
    return (
      <div data-testid="statistics-loading" className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div data-testid="statistics-error" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:bg-red-900/20 dark:text-red-300">
        Failed to load statistics.
      </div>
    );
  }

  const stats = data.data;

  return (
    <div data-testid="statistics-cards" className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div data-testid="stat-total" className="rounded-lg border bg-white p-4 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Total Events</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{stats.total_events.toLocaleString()}</p>
        <p className="text-xs text-gray-400">Last {stats.period_days} days</p>
      </div>
      <div data-testid="stat-critical" className="rounded-lg border bg-white p-4 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Critical</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-red-600 dark:text-red-400">
          {(stats.by_severity["critical"] ?? 0).toLocaleString()}
        </p>
        <p className="text-xs text-gray-400">High severity</p>
      </div>
      <div data-testid="stat-warning" className="rounded-lg border bg-white p-4 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Warnings</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-yellow-600 dark:text-yellow-400">
          {(stats.by_severity["warning"] ?? 0).toLocaleString()}
        </p>
        <p className="text-xs text-gray-400">Needs review</p>
      </div>
      <div data-testid="stat-modules" className="rounded-lg border bg-white p-4 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Active Modules</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {Object.keys(stats.by_module).length}
        </p>
        <p className="text-xs text-gray-400">Reporting activity</p>
      </div>
    </div>
  );
}

// ── AuditFilters ──────────────────────────────────────────────────────────────

interface AuditFiltersProps {
  filters: Partial<AuditLogFilters>;
  onChange: (updated: Partial<AuditLogFilters>) => void;
  availableModules?: string[];
}

export function AuditFilters({ filters, onChange, availableModules = [] }: AuditFiltersProps) {
  return (
    <div data-testid="audit-filters" className="flex flex-wrap gap-3">
      <input
        data-testid="filter-search"
        type="text"
        placeholder="Search actions, modules…"
        value={filters.search ?? ""}
        onChange={(e) => onChange({ ...filters, search: e.target.value || undefined })}
        className="rounded-md border px-3 py-1.5 text-sm dark:bg-gray-800 dark:border-gray-700"
      />
      <select
        data-testid="filter-severity"
        value={filters.severity ?? ""}
        onChange={(e) =>
          onChange({ ...filters, severity: (e.target.value as AuditSeverity) || undefined })
        }
        className="rounded-md border px-3 py-1.5 text-sm dark:bg-gray-800 dark:border-gray-700"
      >
        <option value="">All severities</option>
        {AUDIT_SEVERITIES.map((s) => (
          <option key={s} value={s}>
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </option>
        ))}
      </select>
      {availableModules.length > 0 && (
        <select
          data-testid="filter-module"
          value={filters.module ?? ""}
          onChange={(e) => onChange({ ...filters, module: e.target.value || undefined })}
          className="rounded-md border px-3 py-1.5 text-sm dark:bg-gray-800 dark:border-gray-700"
        >
          <option value="">All modules</option>
          {availableModules.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      )}
      <input
        data-testid="filter-date-from"
        type="datetime-local"
        value={filters.date_from ?? ""}
        onChange={(e) => onChange({ ...filters, date_from: e.target.value || undefined })}
        className="rounded-md border px-3 py-1.5 text-sm dark:bg-gray-800 dark:border-gray-700"
      />
      <input
        data-testid="filter-date-to"
        type="datetime-local"
        value={filters.date_to ?? ""}
        onChange={(e) => onChange({ ...filters, date_to: e.target.value || undefined })}
        className="rounded-md border px-3 py-1.5 text-sm dark:bg-gray-800 dark:border-gray-700"
      />
      {(filters.search || filters.severity || filters.module || filters.date_from || filters.date_to) && (
        <button
          data-testid="filter-clear"
          onClick={() => onChange({ workspace_id: filters.workspace_id })}
          className="rounded-md border px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

// ── AuditTable ────────────────────────────────────────────────────────────────

interface AuditTableProps {
  items: AuditLog[];
  isLoading?: boolean;
  onSelect?: (log: AuditLog) => void;
  selectedId?: string | null;
}

export function AuditTable({ items, isLoading, onSelect, selectedId }: AuditTableProps) {
  if (isLoading) {
    return (
      <div data-testid="audit-table-loading" className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div data-testid="audit-table-empty" className="py-12 text-center text-gray-500 dark:text-gray-400">
        No audit events found.
      </div>
    );
  }

  return (
    <div data-testid="audit-table" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b text-left text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
          <tr>
            <th className="pb-2 pr-4">Severity</th>
            <th className="pb-2 pr-4">Action</th>
            <th className="pb-2 pr-4">Module</th>
            <th className="pb-2 pr-4">Entity</th>
            <th className="pb-2">Time</th>
          </tr>
        </thead>
        <tbody>
          {items.map((log) => (
            <tr
              key={log.id}
              data-testid={`audit-row-${log.id}`}
              onClick={() => onSelect?.(log)}
              className={`cursor-pointer border-b last:border-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50 ${
                selectedId === log.id ? "bg-blue-50 dark:bg-blue-900/20" : ""
              }`}
            >
              <td className="py-2 pr-4">
                <SeverityBadge severity={log.severity} />
              </td>
              <td className="py-2 pr-4 font-mono text-xs">{log.action}</td>
              <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{log.module}</td>
              <td className="py-2 pr-4 text-gray-500 dark:text-gray-500">
                {log.entity_type ? `${log.entity_type}` : "—"}
              </td>
              <td className="py-2 text-gray-400 dark:text-gray-500">
                {new Date(log.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── AuditDetailDrawer ─────────────────────────────────────────────────────────

interface AuditDetailDrawerProps {
  logId: string | null;
  onClose: () => void;
}

export function AuditDetailDrawer({ logId, onClose }: AuditDetailDrawerProps) {
  const { data, isLoading } = useAuditEvent(logId);

  if (!logId) return null;

  return (
    <div data-testid="audit-detail-drawer" className="fixed inset-y-0 right-0 z-40 flex w-96 flex-col bg-white shadow-xl dark:bg-gray-900">
      <div className="flex items-center justify-between border-b p-4 dark:border-gray-700">
        <h2 className="font-semibold">Event Details</h2>
        <button
          data-testid="drawer-close"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
          aria-label="Close drawer"
        >
          ✕
        </button>
      </div>

      {isLoading && (
        <div data-testid="drawer-loading" className="flex flex-1 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
        </div>
      )}

      {data && (
        <div data-testid="drawer-content" className="flex-1 overflow-y-auto p-4">
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500">Severity</dt>
              <dd className="mt-1"><SeverityBadge severity={data.data.severity} /></dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500">Action</dt>
              <dd data-testid="drawer-action" className="mt-1 font-mono text-xs">{data.data.action}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500">Module</dt>
              <dd data-testid="drawer-module" className="mt-1">{data.data.module}</dd>
            </div>
            {data.data.entity_type && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">Entity</dt>
                <dd data-testid="drawer-entity" className="mt-1">
                  {data.data.entity_type} · <span className="font-mono text-xs">{data.data.entity_id}</span>
                </dd>
              </div>
            )}
            {data.data.user_id && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">User</dt>
                <dd data-testid="drawer-user" className="mt-1 font-mono text-xs">{data.data.user_id}</dd>
              </div>
            )}
            {data.data.ip_address && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">IP Address</dt>
                <dd data-testid="drawer-ip" className="mt-1 font-mono text-xs">{data.data.ip_address}</dd>
              </div>
            )}
            <div>
              <dt className="text-xs uppercase tracking-wide text-gray-500">Timestamp</dt>
              <dd data-testid="drawer-timestamp" className="mt-1">
                {new Date(data.data.created_at).toLocaleString()}
              </dd>
            </div>
            {Object.keys(data.data.metadata).length > 0 && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-gray-500">Metadata</dt>
                <dd data-testid="drawer-metadata" className="mt-1">
                  <pre className="overflow-x-auto rounded bg-gray-100 p-2 font-mono text-xs dark:bg-gray-800">
                    {JSON.stringify(data.data.metadata, null, 2)}
                  </pre>
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}

// ── EntityAuditHistory ────────────────────────────────────────────────────────

interface EntityAuditHistoryProps {
  entityType: string;
  entityId: string;
  workspaceId: string;
}

export function EntityAuditHistory({ entityType, entityId, workspaceId }: EntityAuditHistoryProps) {
  const { data, isLoading } = useEntityAuditEvents(entityType, entityId, workspaceId);

  return (
    <div data-testid="entity-audit-history">
      <h3 className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
        Activity History
      </h3>
      {isLoading && (
        <div data-testid="entity-history-loading" className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          ))}
        </div>
      )}
      {!isLoading && (!data || data.data.length === 0) && (
        <p data-testid="entity-history-empty" className="text-sm text-gray-400">
          No activity recorded.
        </p>
      )}
      {data && data.data.length > 0 && (
        <ul data-testid="entity-history-list" className="space-y-2">
          {data.data.map((log) => (
            <li
              key={log.id}
              data-testid={`entity-history-item-${log.id}`}
              className="flex items-start gap-2 text-sm"
            >
              <SeverityBadge severity={log.severity} />
              <span className="font-mono text-xs text-gray-600 dark:text-gray-400">
                {log.action}
              </span>
              <span className="ml-auto text-xs text-gray-400">
                {new Date(log.created_at).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── AuditCenter ───────────────────────────────────────────────────────────────

interface AuditCenterProps {
  workspaceId: string;
}

export function AuditCenter({ workspaceId }: AuditCenterProps) {
  const [filters, setFilters] = useState<Partial<AuditLogFilters>>({ workspace_id: workspaceId });
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | undefined>(undefined);

  const { data, isLoading, isError } = useAuditEvents({
    workspace_id: workspaceId,
    ...filters,
    cursor,
  });

  function handleFiltersChange(updated: Partial<AuditLogFilters>) {
    setFilters(updated);
    setCursor(undefined);
  }

  function handleLoadMore() {
    if (data?.data.next_cursor) setCursor(data.data.next_cursor);
  }

  return (
    <div data-testid="audit-center" className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Audit Log</h1>
        <span data-testid="audit-total" className="text-sm text-gray-500">
          {data ? `${data.data.total.toLocaleString()} events` : "—"}
        </span>
      </div>

      <StatisticsCards workspaceId={workspaceId} />

      <AuditFilters filters={filters} onChange={handleFiltersChange} />

      {isError && (
        <div data-testid="audit-error" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:bg-red-900/20 dark:text-red-300">
          Failed to load audit events.
        </div>
      )}

      <AuditTable
        items={data?.data.items ?? []}
        isLoading={isLoading}
        onSelect={(log) => setSelectedLogId(log.id)}
        selectedId={selectedLogId}
      />

      {data?.data.has_more && (
        <div className="flex justify-center">
          <button
            data-testid="load-more"
            onClick={handleLoadMore}
            className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Load more
          </button>
        </div>
      )}

      {selectedLogId && (
        <>
          <div
            data-testid="drawer-backdrop"
            onClick={() => setSelectedLogId(null)}
            className="fixed inset-0 z-30 bg-black/20"
          />
          <AuditDetailDrawer logId={selectedLogId} onClose={() => setSelectedLogId(null)} />
        </>
      )}
    </div>
  );
}
