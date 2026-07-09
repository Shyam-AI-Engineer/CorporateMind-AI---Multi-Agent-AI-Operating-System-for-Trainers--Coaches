"use client";

import React from "react";
import type { SecurityAlerts } from "@/features/security/types";
import { ALERT_SEVERITY_LABELS, ALERT_TYPE_LABELS } from "@/features/security/types";

interface SecurityAlertsPanelProps {
  alerts: SecurityAlerts;
}

const SEVERITY_BADGE_CLASSES: Record<string, string> = {
  low: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export function SecurityAlertsPanel({ alerts }: SecurityAlertsPanelProps) {
  if (alerts.total === 0) {
    return (
      <div data-testid="security-alerts-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Security Alerts
        </h3>
        <p data-testid="no-alerts" className="text-sm text-green-600 dark:text-green-400">
          No security alerts detected.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="security-alerts-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Security Alerts
        </h3>
        <span
          data-testid="alert-count-badge"
          className="inline-flex items-center rounded-full bg-red-100 dark:bg-red-900 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300"
        >
          {alerts.total} alert{alerts.total !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-2">
        {alerts.alerts.map((alert, idx) => (
          <div
            key={`${alert.alert_type}-${idx}`}
            data-testid={`alert-item-${alert.alert_type}`}
            className="flex items-start gap-3 rounded-md border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800 px-3 py-2"
          >
            <span
              data-testid={`alert-severity-${alert.severity}`}
              className={`mt-0.5 inline-flex shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium ${
                SEVERITY_BADGE_CLASSES[alert.severity] ?? SEVERITY_BADGE_CLASSES.low
              }`}
            >
              {ALERT_SEVERITY_LABELS[alert.severity] ?? alert.severity}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-gray-800 dark:text-gray-200">
                {ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {alert.message}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
