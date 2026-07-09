"use client";

import React from "react";
import type { ModuleHealth } from "@/features/observability/types";
import { MODULE_DISPLAY_NAMES } from "@/features/observability/types";

interface ModuleHealthTableProps {
  health: ModuleHealth;
}

export function ModuleHealthTable({ health }: ModuleHealthTableProps) {
  if (health.modules.length === 0) {
    return (
      <p data-testid="no-modules" className="text-sm text-gray-500 dark:text-gray-400 py-4">
        No modules to display.
      </p>
    );
  }

  return (
    <div data-testid="module-health-table" className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {health.healthy} of {health.total} healthy
        </span>
        {health.warning > 0 && (
          <span data-testid="warning-badge" className="text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
            {health.warning} warning{health.warning !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Module</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Records</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Cache</th>
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
          {health.modules.map((mod) => (
            <tr key={mod.module} data-testid={`module-row-${mod.module}`}>
              <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                {MODULE_DISPLAY_NAMES[mod.module] ?? mod.module}
              </td>
              <td className="px-4 py-3">
                <span
                  data-testid={`module-status-${mod.module}`}
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    mod.healthy
                      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                      : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                  }`}
                >
                  {mod.healthy ? "Healthy" : "Warning"}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400 font-variant-numeric">
                {mod.record_count.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-center">
                <span
                  data-testid={`module-cache-${mod.module}`}
                  className={`text-xs ${mod.cache_enabled ? "text-green-600 dark:text-green-400" : "text-gray-400 dark:text-gray-600"}`}
                >
                  {mod.cache_enabled ? "Yes" : "No"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
