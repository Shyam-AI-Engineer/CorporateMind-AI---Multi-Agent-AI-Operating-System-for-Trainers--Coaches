"use client";

import React from "react";
import type { ApiKeyHealth } from "@/features/security/types";

interface ApiKeyHealthPanelProps {
  health: ApiKeyHealth;
}

export function ApiKeyHealthPanel({ health }: ApiKeyHealthPanelProps) {
  const metrics = [
    { label: "Total", value: health.total_keys, testId: "key-total" },
    { label: "Active", value: health.active, testId: "key-active" },
    { label: "Expired", value: health.expired, testId: "key-expired", warn: health.expired > 0 },
    { label: "Never Used", value: health.never_used, testId: "key-never-used", warn: health.never_used > 0 },
    { label: "Used (30d)", value: health.used_last_30_days, testId: "key-used-30d" },
  ];

  return (
    <div data-testid="api-key-health-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
        API Key Health
      </h3>

      <div className="space-y-3">
        {metrics.map((m) => (
          <div key={m.testId} className="flex items-center justify-between">
            <span className="text-xs text-gray-500 dark:text-gray-400">{m.label}</span>
            <span
              data-testid={m.testId}
              className={`text-sm font-medium tabular-nums ${
                m.warn
                  ? "text-red-600 dark:text-red-400"
                  : "text-gray-900 dark:text-gray-100"
              }`}
            >
              {m.value}
            </span>
          </div>
        ))}
      </div>

      {health.expired > 0 && (
        <p
          data-testid="expired-warning"
          className="mt-3 text-xs text-red-600 dark:text-red-400"
        >
          {health.expired} key{health.expired !== 1 ? "s" : ""} expired — rotate immediately.
        </p>
      )}
    </div>
  );
}
