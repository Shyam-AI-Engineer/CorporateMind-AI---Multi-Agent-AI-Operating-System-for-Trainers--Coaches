"use client";

import type { ReportStatus } from "../types";

interface Props {
  status: ReportStatus;
}

const CONFIG: Record<ReportStatus, { label: string; className: string }> = {
  pending: {
    label: "Pending",
    className:
      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
  },
  ready: {
    label: "Ready",
    className:
      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  },
  failed: {
    label: "Failed",
    className:
      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
  },
};

export function ReportStatusBadge({ status }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.pending;
  return <span className={cfg.className}>{cfg.label}</span>;
}
