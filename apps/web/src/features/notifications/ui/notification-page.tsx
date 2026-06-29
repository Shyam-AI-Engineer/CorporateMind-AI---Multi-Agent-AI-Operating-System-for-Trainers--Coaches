"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useNotifications,
  useUnreadCount,
  useMarkAllRead,
  useMarkNotificationRead,
  useDeleteNotification,
} from "@/features/notifications/api/use-notifications";
import type { NotificationOut, NotificationPriority } from "@/features/notifications/types";

// ── Priority badge ────────────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: NotificationPriority }) {
  const colors: Record<NotificationPriority, string> = {
    low: "bg-slate-100 text-slate-600 border-slate-200",
    medium: "bg-blue-100 text-blue-700 border-blue-200",
    high: "bg-amber-100 text-amber-700 border-amber-200",
    urgent: "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <span
      data-testid={`priority-badge-${priority}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[priority]}`}
    >
      {priority}
    </span>
  );
}

// ── Notification item ─────────────────────────────────────────────────────────

interface NotificationItemProps {
  notification: NotificationOut;
  workspaceId: string;
}

function NotificationItem({ notification, workspaceId }: NotificationItemProps) {
  const markRead = useMarkNotificationRead(workspaceId);
  const deleteN = useDeleteNotification(workspaceId);

  return (
    <div
      data-testid={`notification-item-${notification.id}`}
      className={`flex items-start gap-3 rounded-lg border p-4 ${
        notification.is_read ? "opacity-70" : "border-blue-200 bg-blue-50/20"
      }`}
    >
      {/* Read indicator */}
      {!notification.is_read && (
        <span
          data-testid={`notification-unread-indicator-${notification.id}`}
          className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500"
        />
      )}
      {notification.is_read && (
        <span
          data-testid={`notification-read-indicator-${notification.id}`}
          className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-transparent border border-slate-300"
        />
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p
            data-testid={`notification-title-${notification.id}`}
            className="text-sm font-medium"
          >
            {notification.title}
          </p>
          <PriorityBadge priority={notification.priority} />
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">{notification.message}</p>
        {notification.entity_type && (
          <p
            data-testid={`notification-entity-type-${notification.id}`}
            className="mt-1 text-xs text-muted-foreground"
          >
            {notification.entity_type}
          </p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          {new Date(notification.created_at).toLocaleString()}
        </p>
      </div>

      <div className="flex shrink-0 gap-1">
        {!notification.is_read && (
          <Button
            variant="ghost"
            size="sm"
            data-testid={`mark-read-btn-${notification.id}`}
            disabled={markRead.isPending}
            onClick={() => markRead.mutate(notification.id)}
            className="text-xs"
          >
            Mark read
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          data-testid={`delete-btn-${notification.id}`}
          disabled={deleteN.isPending}
          onClick={() => deleteN.mutate(notification.id)}
          className="text-xs text-destructive hover:text-destructive"
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterState {
  is_read: "" | "true" | "false";
  priority: string;
  entity_type: string;
}

const EMPTY_FILTERS: FilterState = { is_read: "", priority: "", entity_type: "" };

function filtersActive(f: FilterState): boolean {
  return f.is_read !== "" || f.priority !== "" || f.entity_type !== "";
}

interface FilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

function FilterBar({ filters, onChange }: FilterBarProps) {
  return (
    <div data-testid="notification-filters" className="flex flex-wrap items-center gap-2">
      <select
        data-testid="filter-is-read"
        className="rounded border bg-background px-2 py-1 text-sm"
        value={filters.is_read}
        onChange={(e) => onChange({ ...filters, is_read: e.target.value as FilterState["is_read"] })}
      >
        <option value="">All</option>
        <option value="false">Unread</option>
        <option value="true">Read</option>
      </select>

      <select
        data-testid="filter-priority"
        className="rounded border bg-background px-2 py-1 text-sm"
        value={filters.priority}
        onChange={(e) => onChange({ ...filters, priority: e.target.value })}
      >
        <option value="">All priorities</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="urgent">Urgent</option>
      </select>

      <input
        data-testid="filter-entity-type"
        type="text"
        placeholder="Entity type..."
        className="rounded border bg-background px-2 py-1 text-sm"
        value={filters.entity_type}
        onChange={(e) => onChange({ ...filters, entity_type: e.target.value })}
      />

      {filtersActive(filters) && (
        <Button
          variant="ghost"
          size="sm"
          data-testid="clear-filters-btn"
          onClick={() => onChange(EMPTY_FILTERS)}
          className="text-xs"
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}

// ── Section grouping helpers ──────────────────────────────────────────────────

function groupBySection(items: NotificationOut[]): {
  unread: NotificationOut[];
  today: NotificationOut[];
  earlier: NotificationOut[];
} {
  const todayStr = new Date().toDateString();
  const unread: NotificationOut[] = [];
  const today: NotificationOut[] = [];
  const earlier: NotificationOut[] = [];

  for (const n of items) {
    if (!n.is_read) {
      unread.push(n);
    } else if (new Date(n.created_at).toDateString() === todayStr) {
      today.push(n);
    } else {
      earlier.push(n);
    }
  }
  return { unread, today, earlier };
}

// ── Main page component ───────────────────────────────────────────────────────

export function NotificationPage() {
  const { workspaceId } = useWorkspace();
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [prevCursors, setPrevCursors] = useState<string[]>([]);

  const isReadFilter =
    filters.is_read === "true" ? true : filters.is_read === "false" ? false : undefined;

  const { data, isLoading, isError } = useNotifications(workspaceId, {
    cursor,
    is_read: isReadFilter,
    priority: filters.priority || undefined,
    entity_type: filters.entity_type || undefined,
  });

  const { data: countData } = useUnreadCount(workspaceId);
  const markAllMutation = useMarkAllRead(workspaceId ?? "");

  if (!workspaceId) {
    return (
      <div data-testid="notifications-no-workspace" className="p-6 text-muted-foreground">
        Select a workspace to view notifications.
      </div>
    );
  }

  const handleNext = () => {
    if (data?.next_cursor) {
      setPrevCursors((p) => [...p, cursor ?? ""]);
      setCursor(data.next_cursor);
    }
  };

  const handlePrev = () => {
    const prev = [...prevCursors];
    const last = prev.pop() ?? undefined;
    setPrevCursors(prev);
    setCursor(last === "" ? undefined : last);
  };

  const handleFilterChange = (f: FilterState) => {
    setFilters(f);
    setCursor(undefined);
    setPrevCursors([]);
  };

  const grouped = data ? groupBySection(data.items) : null;

  return (
    <div data-testid="notification-page" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">Notifications</h2>
          {(countData?.count ?? 0) > 0 && (
            <span
              data-testid="page-unread-count"
              className="rounded-full bg-red-500 px-2 py-0.5 text-xs font-bold text-white"
            >
              {countData!.count}
            </span>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          data-testid="mark-all-read-btn"
          disabled={(countData?.count ?? 0) === 0 || markAllMutation.isPending}
          onClick={() => markAllMutation.mutate()}
        >
          Mark all read
        </Button>
      </div>

      <FilterBar filters={filters} onChange={handleFilterChange} />

      {/* Content */}
      {isLoading && (
        <div data-testid="notification-list-skeleton" className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}

      {isError && !isLoading && (
        <div
          data-testid="notification-list-error"
          className="rounded-lg border border-destructive/30 p-6 text-center text-sm text-destructive"
        >
          Failed to load notifications. Please try again.
        </div>
      )}

      {!isLoading && !isError && data?.items.length === 0 && (
        <div
          data-testid="notification-list-empty"
          className="rounded-lg border p-8 text-center text-sm text-muted-foreground"
        >
          No notifications to show.
        </div>
      )}

      {!isLoading && !isError && data && data.items.length > 0 && (
        <div data-testid="notification-list" className="space-y-6">
          {/* Unread section */}
          {grouped && grouped.unread.length > 0 && (
            <section data-testid="section-unread">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Unread
              </h3>
              <div className="space-y-2">
                {grouped.unread.map((n) => (
                  <NotificationItem key={n.id} notification={n} workspaceId={workspaceId} />
                ))}
              </div>
            </section>
          )}

          {/* Today section */}
          {grouped && grouped.today.length > 0 && (
            <section data-testid="section-today">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Today
              </h3>
              <div className="space-y-2">
                {grouped.today.map((n) => (
                  <NotificationItem key={n.id} notification={n} workspaceId={workspaceId} />
                ))}
              </div>
            </section>
          )}

          {/* Earlier section */}
          {grouped && grouped.earlier.length > 0 && (
            <section data-testid="section-earlier">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Earlier
              </h3>
              <div className="space-y-2">
                {grouped.earlier.map((n) => (
                  <NotificationItem key={n.id} notification={n} workspaceId={workspaceId} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Pagination */}
      {!isLoading && !isError && (
        <div className="flex items-center gap-2">
          {prevCursors.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              data-testid="notification-list-prev-btn"
              onClick={handlePrev}
            >
              Previous
            </Button>
          )}
          {data?.has_more && (
            <Button
              variant="outline"
              size="sm"
              data-testid="notification-list-next-btn"
              onClick={handleNext}
            >
              Next
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
