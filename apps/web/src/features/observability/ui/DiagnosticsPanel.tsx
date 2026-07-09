"use client";

import React from "react";
import type { RecentErrors } from "@/features/observability/types";

interface DiagnosticsPanelProps {
  errors: RecentErrors;
}

export function DiagnosticsPanel({ errors }: DiagnosticsPanelProps) {
  if (errors.total === 0) {
    return (
      <div data-testid="diagnostics-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Recent Diagnostics
        </h3>
        <p data-testid="no-errors" className="text-sm text-green-600 dark:text-green-400">
          No warnings or critical events in the last 24 hours.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="diagnostics-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Recent Diagnostics
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Last 24h · {errors.total} event{errors.total !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {errors.errors.map((err, idx) => (
          <div
            key={`${err.source}-${err.occurred_at}-${idx}`}
            data-testid="error-item"
            className="flex items-start gap-3 rounded-md border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800 px-3 py-2"
          >
            <span
              data-testid={`error-severity-${err.severity}`}
              className={`mt-0.5 inline-flex shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium ${
                err.severity === "critical"
                  ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
                  : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
              }`}
            >
              {err.severity}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">
                {err.message}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {err.source}
              </p>
            </div>
            <time className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
              {new Date(err.occurred_at).toLocaleTimeString()}
            </time>
          </div>
        ))}
      </div>
    </div>
  );
}
