"use client";

import React from "react";
import type { BulkOperationOut } from "@/features/bulk_operations/types";
import { ENTITY_TYPE_LABELS, OPERATION_TYPE_LABELS } from "@/features/bulk_operations/types";
import { BulkStatusBadge } from "@/features/bulk_operations/ui/BulkStatusBadge";

interface ImportSummaryCardProps {
  operation: BulkOperationOut;
}

export function ImportSummaryCard({ operation }: ImportSummaryCardProps) {
  const successRate =
    operation.total_records > 0
      ? Math.round((operation.successful_records / operation.total_records) * 100)
      : 0;

  return (
    <div
      data-testid="import-summary-card"
      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <p data-testid="summary-operation-type" className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {OPERATION_TYPE_LABELS[operation.operation_type] ?? operation.operation_type}
          </p>
          <p data-testid="summary-entity-type" className="text-xs text-gray-500 dark:text-gray-400">
            {ENTITY_TYPE_LABELS[operation.entity_type] ?? operation.entity_type}
          </p>
        </div>
        <BulkStatusBadge status={operation.status} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-3">
        <div data-testid="summary-total" className="text-center">
          <p className="text-xl font-bold tabular-nums text-gray-900 dark:text-gray-100">
            {operation.total_records}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Total</p>
        </div>
        <div data-testid="summary-processed" className="text-center">
          <p className="text-xl font-bold tabular-nums text-gray-900 dark:text-gray-100">
            {operation.processed_records}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Processed</p>
        </div>
        <div data-testid="summary-successful" className="text-center">
          <p className="text-xl font-bold tabular-nums text-green-600 dark:text-green-400">
            {operation.successful_records}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Successful</p>
        </div>
        <div data-testid="summary-failed" className="text-center">
          <p className={`text-xl font-bold tabular-nums ${
            operation.failed_records > 0
              ? "text-red-600 dark:text-red-400"
              : "text-gray-900 dark:text-gray-100"
          }`}>
            {operation.failed_records}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">Failed</p>
        </div>
      </div>

      <div data-testid="summary-success-rate" className="mb-2">
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
          <span>Success rate</span>
          <span className="tabular-nums font-medium">{successRate}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-gray-100 dark:bg-gray-800">
          <div
            data-testid="summary-progress-bar"
            className={`h-1.5 rounded-full ${
              successRate === 100
                ? "bg-green-500"
                : successRate >= 80
                ? "bg-yellow-500"
                : "bg-red-500"
            }`}
            style={{ width: `${successRate}%` }}
          />
        </div>
      </div>

      {operation.error_summary && (
        <div data-testid="summary-error-section" className="mt-3 rounded-md bg-red-50 dark:bg-red-950 p-2">
          <p className="text-xs font-medium text-red-700 dark:text-red-300 mb-1">Errors</p>
          <pre data-testid="summary-error-text" className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap break-words">
            {operation.error_summary}
          </pre>
        </div>
      )}
    </div>
  );
}
