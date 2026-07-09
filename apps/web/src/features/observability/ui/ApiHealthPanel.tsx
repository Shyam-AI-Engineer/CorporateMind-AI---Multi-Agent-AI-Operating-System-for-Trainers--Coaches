"use client";

import React from "react";
import type { ApiHealth } from "@/features/observability/types";

interface ApiHealthPanelProps {
  health: ApiHealth;
}

export function ApiHealthPanel({ health }: ApiHealthPanelProps) {
  const errorPct = Math.round(health.error_rate * 100 * 100) / 100;
  const errorColor =
    errorPct === 0
      ? "text-green-600 dark:text-green-400"
      : errorPct < 1
      ? "text-yellow-500 dark:text-yellow-400"
      : "text-red-600 dark:text-red-400";

  const bucketColor =
    health.average_response_bucket === "fast"
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : health.average_response_bucket === "moderate"
      ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
      : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";

  return (
    <div data-testid="api-health-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">API Gateway</h3>
        <span
          data-testid="response-bucket"
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${bucketColor}`}
        >
          {health.average_response_bucket}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="text-center">
          <p className="text-xs text-gray-500 dark:text-gray-400">Registered Routes</p>
          <p data-testid="route-count" className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {health.registered_routes}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 dark:text-gray-400">Error Rate (24h)</p>
          <p data-testid="error-rate" className={`text-2xl font-bold ${errorColor}`}>
            {errorPct.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  );
}
