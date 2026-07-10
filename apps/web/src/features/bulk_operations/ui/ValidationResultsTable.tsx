"use client";

import React from "react";
import type { CsvValidationOut, ValidationRowResult } from "@/features/bulk_operations/types";

interface ValidationResultsTableProps {
  validation: CsvValidationOut;
}

function RowStatusIcon({ valid }: { valid: boolean }) {
  return (
    <span
      data-testid={valid ? "row-valid-icon" : "row-invalid-icon"}
      className={valid ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}
      aria-label={valid ? "Valid" : "Invalid"}
    >
      {valid ? "✓" : "✗"}
    </span>
  );
}

export function ValidationResultsTable({ validation }: ValidationResultsTableProps) {
  const invalidRows = validation.results.filter((r) => !r.valid);

  return (
    <div data-testid="validation-results-table" className="space-y-3">
      {/* Summary bar */}
      <div data-testid="validation-summary" className="flex items-center gap-4 text-sm">
        <span data-testid="validation-total" className="text-gray-700 dark:text-gray-300">
          <span className="font-semibold tabular-nums">{validation.total_rows}</span> rows
        </span>
        <span data-testid="validation-valid-count" className="text-green-700 dark:text-green-400">
          <span className="font-semibold tabular-nums">{validation.valid_rows}</span> valid
        </span>
        <span data-testid="validation-invalid-count" className={
          validation.invalid_rows > 0
            ? "text-red-700 dark:text-red-400"
            : "text-gray-500 dark:text-gray-400"
        }>
          <span className="font-semibold tabular-nums">{validation.invalid_rows}</span> invalid
        </span>
        {validation.dry_run && (
          <span data-testid="dry-run-badge" className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
            Dry run
          </span>
        )}
      </div>

      {/* All-valid message */}
      {validation.invalid_rows === 0 && (
        <p data-testid="all-valid-message" className="text-sm text-green-700 dark:text-green-400">
          All rows are valid.
        </p>
      )}

      {/* Error table */}
      {invalidRows.length > 0 && (
        <div data-testid="error-table" className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Row</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Status</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Field</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Error</th>
              </tr>
            </thead>
            <tbody>
              {invalidRows.map((result) =>
                result.errors.map((err, idx) => (
                  <tr
                    key={`${result.row}-${idx}`}
                    data-testid={`error-row-${result.row}`}
                    className="border-t border-gray-100 dark:border-gray-800"
                  >
                    <td className="px-3 py-1.5 tabular-nums text-gray-700 dark:text-gray-300">
                      {result.row}
                    </td>
                    <td className="px-3 py-1.5">
                      <RowStatusIcon valid={false} />
                    </td>
                    <td className="px-3 py-1.5 font-mono text-gray-700 dark:text-gray-300">
                      {err.field}
                    </td>
                    <td className="px-3 py-1.5 text-red-600 dark:text-red-400">
                      {err.message}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
