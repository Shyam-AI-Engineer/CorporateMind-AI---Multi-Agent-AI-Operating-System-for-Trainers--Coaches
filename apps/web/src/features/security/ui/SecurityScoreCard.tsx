"use client";

import React from "react";
import type { SecuritySummary } from "@/features/security/types";

interface SecurityScoreCardProps {
  summary: SecuritySummary;
}

export function SecurityScoreCard({ summary }: SecurityScoreCardProps) {
  const pct = Math.round(summary.overall_security_score * 100);

  const scoreColor =
    pct >= 80
      ? "text-green-600 dark:text-green-400"
      : pct >= 60
      ? "text-yellow-600 dark:text-yellow-400"
      : "text-red-600 dark:text-red-400";

  const metrics = [
    { label: "Active API Keys", value: summary.active_api_keys, testId: "metric-active-keys" },
    { label: "Expired API Keys", value: summary.expired_api_keys, testId: "metric-expired-keys" },
    { label: "Active Members", value: summary.active_workspace_members, testId: "metric-members" },
    { label: "Org Admins", value: summary.organization_admins, testId: "metric-admins" },
    { label: "Audit Events Today", value: summary.audit_events_today, testId: "metric-audit-today" },
    { label: "Critical Events", value: summary.critical_audit_events, testId: "metric-critical" },
  ];

  return (
    <div data-testid="security-score-card" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
      {/* Score ring */}
      <div data-testid="score-ring" className="flex flex-col items-center mb-6">
        <span className={`text-4xl font-bold tabular-nums ${scoreColor}`}>
          {pct}%
        </span>
        <span className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Security Score
        </span>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {metrics.map((m) => (
          <div
            key={m.testId}
            data-testid={m.testId}
            className="rounded-md bg-gray-50 dark:bg-gray-800 px-3 py-2"
          >
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{m.label}</p>
            <p className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-100">
              {m.value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
