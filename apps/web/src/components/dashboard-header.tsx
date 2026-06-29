"use client";

import { NotificationBell } from "@/features/notifications/ui/notification-bell";

export function DashboardHeader() {
  return (
    <header
      data-testid="dashboard-header"
      className="flex h-12 shrink-0 items-center justify-end border-b bg-background px-4"
    >
      <NotificationBell />
    </header>
  );
}
