"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Bell } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useUnreadCount,
  useNotifications,
  useMarkAllRead,
} from "@/features/notifications/api/use-notifications";
import type { NotificationOut, NotificationPriority } from "@/features/notifications/types";

// ── Priority badge ────────────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: NotificationPriority }) {
  const colors: Record<NotificationPriority, string> = {
    low: "bg-slate-100 text-slate-600",
    medium: "bg-blue-100 text-blue-700",
    high: "bg-amber-100 text-amber-700",
    urgent: "bg-red-100 text-red-700",
  };
  return (
    <span
      data-testid={`notification-priority-badge-${priority}`}
      className={`rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${colors[priority]}`}
    >
      {priority}
    </span>
  );
}

// ── Notification preview item ─────────────────────────────────────────────────

function NotificationPreviewItem({ notification }: { notification: NotificationOut }) {
  return (
    <div
      data-testid={`notification-preview-item-${notification.id}`}
      className={`border-b px-4 py-3 last:border-0 ${
        notification.is_read ? "opacity-60" : "bg-blue-50/30"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p
            data-testid={`notification-preview-title-${notification.id}`}
            className="truncate text-sm font-medium"
          >
            {notification.title}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {notification.message}
          </p>
        </div>
        <PriorityBadge priority={notification.priority} />
      </div>
      {!notification.is_read && (
        <span
          data-testid={`notification-unread-dot-${notification.id}`}
          className="mt-1 inline-block h-1.5 w-1.5 rounded-full bg-blue-500"
        />
      )}
    </div>
  );
}

// ── Notification bell ─────────────────────────────────────────────────────────

export function NotificationBell() {
  const { workspaceId } = useWorkspace();
  const [open, setOpen] = useState(false);

  const { data: countData, isLoading: countLoading } = useUnreadCount(workspaceId);
  const { data: listData, isLoading: listLoading, isError: listError } = useNotifications(
    open ? workspaceId : null,
    { is_read: undefined },
  );
  const markAllMutation = useMarkAllRead(workspaceId ?? "");

  const unreadCount = countData?.count ?? 0;

  if (!workspaceId) return null;

  return (
    <div className="relative" data-testid="notification-bell-wrapper">
      <Button
        variant="ghost"
        size="sm"
        className="relative"
        data-testid="notification-bell"
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {!countLoading && unreadCount > 0 && (
          <span
            data-testid="unread-badge"
            className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </Button>

      {open && (
        <div
          data-testid="notification-dropdown"
          className="absolute right-0 top-10 z-50 w-80 rounded-lg border bg-background shadow-lg"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b px-4 py-3">
            <span className="text-sm font-semibold">Notifications</span>
            <Button
              variant="ghost"
              size="sm"
              data-testid="mark-all-read-bell-btn"
              disabled={unreadCount === 0 || markAllMutation.isPending}
              onClick={() => markAllMutation.mutate()}
              className="text-xs"
            >
              Mark all read
            </Button>
          </div>

          {/* Body */}
          <div className="max-h-80 overflow-y-auto">
            {listLoading && (
              <div data-testid="notification-dropdown-skeleton" className="space-y-2 p-4">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            )}

            {listError && !listLoading && (
              <div
                data-testid="notification-dropdown-error"
                className="p-4 text-center text-sm text-destructive"
              >
                Failed to load notifications.
              </div>
            )}

            {!listLoading && !listError && listData?.items.length === 0 && (
              <div
                data-testid="notification-dropdown-empty"
                className="p-4 text-center text-sm text-muted-foreground"
              >
                No notifications yet.
              </div>
            )}

            {!listLoading &&
              !listError &&
              listData?.items.map((n) => (
                <NotificationPreviewItem key={n.id} notification={n} />
              ))}
          </div>

          {/* Footer */}
          <div className="border-t px-4 py-2 text-center">
            <Link
              href={"/notifications" as Route}
              data-testid="view-all-link"
              className="text-xs text-primary hover:underline"
              onClick={() => setOpen(false)}
            >
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
