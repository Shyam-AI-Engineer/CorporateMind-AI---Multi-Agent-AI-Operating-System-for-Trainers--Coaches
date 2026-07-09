"use client";

import React from "react";
import type { DatabaseHealth } from "@/features/observability/types";

interface DatabaseHealthPanelProps {
  health: DatabaseHealth;
}

export function DatabaseHealthPanel({ health }: DatabaseHealthPanelProps) {
  const latencyColor =
    health.estimated_latency_ms < 0
      ? "text-red-600 dark:text-red-400"
      : health.estimated_latency_ms < 50
      ? "text-green-600 dark:text-green-400"
      : health.estimated_latency_ms < 200
      ? "text-yellow-500 dark:text-yellow-400"
      : "text-red-600 dark:text-red-400";

  return (
    <div data-testid="database-health-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">PostgreSQL</h3>
        <span
          data-testid="connection-status"
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            health.connection_ok
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
          }`}
        >
          {health.connection_ok ? "Connected" : "Disconnected"}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <p className="text-xs text-gray-500 dark:text-gray-400">Latency</p>
          <p data-testid="latency-value" className={`text-lg font-bold ${latencyColor}`}>
            {health.estimated_latency_ms >= 0
              ? `${health.estimated_latency_ms.toFixed(1)}ms`
              : "N/A"}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 dark:text-gray-400">Tables</p>
          <p data-testid="table-count" className="text-lg font-bold text-gray-900 dark:text-gray-100">
            {health.table_count}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 dark:text-gray-400">Migration</p>
          <p data-testid="migration-version" className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate mt-1">
            {health.migration_version === "unknown" ? "—" : health.migration_version}
          </p>
        </div>
      </div>
    </div>
  );
}
