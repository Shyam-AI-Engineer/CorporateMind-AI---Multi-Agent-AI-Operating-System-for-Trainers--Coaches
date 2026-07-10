"use client";

import React from "react";
import type { BulkOperationOut } from "@/features/bulk_operations/types";
import { ENTITY_TYPE_LABELS, OPERATION_TYPE_LABELS } from "@/features/bulk_operations/types";
import { BulkStatusBadge } from "@/features/bulk_operations/ui/BulkStatusBadge";

interface BulkOperationHistoryProps {
  operations: BulkOperationOut[];
  total: number;
}

export function BulkOperationHistory({ operations, total }: BulkOperationHistoryProps) {
  if (total === 0) {
    return (
      <div data-testid="bulk-operation-history" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
        <p data-testid="no-history" className="text-sm text-gray-500 dark:text-gray-400">
          No bulk operations yet.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="bulk-operation-history" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Operation History
        </h3>
        <span data-testid="history-count" className="text-xs text-gray-500 dark:text-gray-400">
          {total} operation{total !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="divide-y divide-gray-50 dark:divide-gray-800">
        {operations.map((op) => (
          <div
            key={op.id}
            data-testid={`history-row-${op.id}`}
            className="flex items-center gap-3 px-4 py-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  data-testid={`history-op-type-${op.id}`}
                  className="text-sm font-medium text-gray-900 dark:text-gray-100"
                >
                  {OPERATION_TYPE_LABELS[op.operation_type] ?? op.operation_type}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500">·</span>
                <span
                  data-testid={`history-entity-type-${op.id}`}
                  className="text-xs text-gray-500 dark:text-gray-400"
                >
                  {ENTITY_TYPE_LABELS[op.entity_type] ?? op.entity_type}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                <span data-testid={`history-records-${op.id}`}>
                  {op.successful_records}/{op.total_records} succeeded
                </span>
                {op.failed_records > 0 && (
                  <span data-testid={`history-failed-${op.id}`} className="text-red-600 dark:text-red-400">
                    {op.failed_records} failed
                  </span>
                )}
              </div>
            </div>
            <BulkStatusBadge status={op.status} />
          </div>
        ))}
      </div>
    </div>
  );
}
