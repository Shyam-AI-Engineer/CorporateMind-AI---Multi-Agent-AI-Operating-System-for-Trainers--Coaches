"use client";

import React from "react";
import {
  useApiKeyHealth,
  useAuditSummary,
  usePermissionOverview,
  useRoleDistribution,
  useSecurityAlerts,
  useSecuritySummary,
} from "@/features/security/api/use-security";
import { SecurityScoreCard } from "@/features/security/ui/SecurityScoreCard";
import { RoleDistributionChart } from "@/features/security/ui/RoleDistributionChart";
import { ApiKeyHealthPanel } from "@/features/security/ui/ApiKeyHealthPanel";
import { PermissionMatrix } from "@/features/security/ui/PermissionMatrix";
import { SecurityAlertsPanel } from "@/features/security/ui/SecurityAlertsPanel";

export function SecurityCenter() {
  const summary = useSecuritySummary();
  const roles = useRoleDistribution();
  const apiKeys = useApiKeyHealth();
  const audit = useAuditSummary();
  const permissions = usePermissionOverview();
  const alerts = useSecurityAlerts();

  const isLoading =
    summary.isLoading ||
    roles.isLoading ||
    apiKeys.isLoading ||
    audit.isLoading ||
    permissions.isLoading ||
    alerts.isLoading;

  const hasError =
    summary.isError ||
    roles.isError ||
    apiKeys.isError ||
    audit.isError ||
    permissions.isError ||
    alerts.isError;

  if (isLoading) {
    return (
      <div data-testid="security-loading" className="flex items-center justify-center py-16">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Loading security diagnostics…
        </p>
      </div>
    );
  }

  if (hasError) {
    return (
      <div
        data-testid="security-error"
        className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-4"
      >
        <p className="text-sm text-red-700 dark:text-red-300">
          Failed to load security data. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="security-center" className="space-y-8">
      {/* Section: Security Posture */}
      <section aria-labelledby="posture-heading">
        <h2
          id="posture-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Security Posture
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {summary.data && <SecurityScoreCard summary={summary.data} />}
          {alerts.data && <SecurityAlertsPanel alerts={alerts.data} />}
        </div>
      </section>

      {/* Section: Access Control */}
      <section aria-labelledby="access-heading">
        <h2
          id="access-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Access Control
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {roles.data && <RoleDistributionChart distribution={roles.data} />}
          {apiKeys.data && <ApiKeyHealthPanel health={apiKeys.data} />}
        </div>
      </section>

      {/* Section: Audit Summary */}
      <section aria-labelledby="audit-heading">
        <h2
          id="audit-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Audit Summary
        </h2>
        {audit.data && (
          <div data-testid="audit-summary-section" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div data-testid="audit-today" className="text-center">
                <p className="text-2xl font-bold tabular-nums text-gray-900 dark:text-gray-100">
                  {audit.data.events_today}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Events Today</p>
              </div>
              <div data-testid="audit-critical" className="text-center">
                <p className={`text-2xl font-bold tabular-nums ${
                  audit.data.critical_events > 0
                    ? "text-red-600 dark:text-red-400"
                    : "text-gray-900 dark:text-gray-100"
                }`}>
                  {audit.data.critical_events}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Critical</p>
              </div>
              <div data-testid="audit-warning" className="text-center">
                <p className={`text-2xl font-bold tabular-nums ${
                  audit.data.warning_events > 0
                    ? "text-yellow-600 dark:text-yellow-400"
                    : "text-gray-900 dark:text-gray-100"
                }`}>
                  {audit.data.warning_events}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Warning</p>
              </div>
            </div>

            {audit.data.top_modules.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                  Top Modules
                </p>
                <div className="space-y-1">
                  {audit.data.top_modules.map((m) => (
                    <div
                      key={m.module}
                      data-testid={`audit-module-${m.module}`}
                      className="flex items-center justify-between"
                    >
                      <span className="text-xs text-gray-700 dark:text-gray-300">
                        {m.module}
                      </span>
                      <span className="text-xs tabular-nums font-medium text-gray-900 dark:text-gray-100">
                        {m.event_count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Section: Permission Overview */}
      <section aria-labelledby="permissions-heading">
        <h2
          id="permissions-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Permission Overview
        </h2>
        {permissions.data && <PermissionMatrix overview={permissions.data} />}
      </section>
    </div>
  );
}
