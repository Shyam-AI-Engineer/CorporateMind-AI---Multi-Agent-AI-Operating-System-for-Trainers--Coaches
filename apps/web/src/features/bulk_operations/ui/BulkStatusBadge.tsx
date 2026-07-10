"use client";

import React from "react";
import type { OperationStatus } from "@/features/bulk_operations/types";
import { OPERATION_STATUS_LABELS } from "@/features/bulk_operations/types";

interface BulkStatusBadgeProps {
  status: OperationStatus;
}

const STATUS_CLASSES: Record<OperationStatus, string> = {
  pending: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  completed: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  cancelled: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
};

export function BulkStatusBadge({ status }: BulkStatusBadgeProps) {
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        STATUS_CLASSES[status] ?? STATUS_CLASSES.pending
      }`}
    >
      {OPERATION_STATUS_LABELS[status] ?? status}
    </span>
  );
}
