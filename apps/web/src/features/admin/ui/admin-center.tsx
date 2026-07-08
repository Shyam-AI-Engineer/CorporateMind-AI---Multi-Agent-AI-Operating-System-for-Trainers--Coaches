"use client";

import React, { useState } from "react";
import {
  useAdminSettings,
  useUpdateAdminSettings,
  useAdminDashboard,
  useAdminModules,
  useAdminSystemStatus,
} from "@/features/admin/api/use-admin";
import type {
  ModuleStatus,
  OrganizationSettings,
  OrganizationSettingsUpdate,
  SystemStatus,
} from "@/features/admin/types-admin";
import {
  ADMIN_CURRENCIES,
  ADMIN_DATE_FORMATS,
  ADMIN_LANGUAGES,
  MODULE_NAMES,
} from "@/features/admin/types-admin";

// ── HealthBadge ───────────────────────────────────────────────────────────────

interface HealthBadgeProps {
  healthy: boolean;
}

export function HealthBadge({ healthy }: HealthBadgeProps) {
  const cls = healthy
    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return (
    <span
      data-testid="health-badge"
      data-healthy={healthy ? "true" : "false"}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {healthy ? "Healthy" : "Degraded"}
    </span>
  );
}

// ── ModuleStatusTable ─────────────────────────────────────────────────────────

interface ModuleStatusTableProps {
  modules: ModuleStatus[];
}

export function ModuleStatusTable({ modules }: ModuleStatusTableProps) {
  if (modules.length === 0) {
    return (
      <div data-testid="module-status-empty" className="py-8 text-center text-sm text-gray-500">
        No modules found.
      </div>
    );
  }
  return (
    <div data-testid="module-status-table" className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">Module</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">Status</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">Enabled</th>
            <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Records</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-900">
          {modules.map((mod) => (
            <tr key={mod.name} data-testid={`module-row-${mod.name}`}>
              <td className="px-4 py-3 font-medium capitalize text-gray-900 dark:text-gray-100">
                {mod.name}
              </td>
              <td className="px-4 py-3">
                <HealthBadge healthy={mod.healthy} />
              </td>
              <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                {mod.enabled ? "Yes" : "No"}
              </td>
              <td
                className="px-4 py-3 text-right font-mono text-gray-900 dark:text-gray-100"
                data-testid={`module-count-${mod.name}`}
              >
                {mod.record_count.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── SystemStatusPanel ─────────────────────────────────────────────────────────

interface SystemStatusPanelProps {
  status: SystemStatus;
}

export function SystemStatusPanel({ status }: SystemStatusPanelProps) {
  return (
    <div data-testid="system-status-panel" className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Overall Platform Health
        </span>
        <HealthBadge healthy={status.overall_healthy} />
      </div>
      <ModuleStatusTable modules={status.modules} />
      <p className="text-xs text-gray-400">
        Last checked: {new Date(status.checked_at).toLocaleString()}
      </p>
    </div>
  );
}

// ── OrganizationSettingsCard ───────────────────────────────────────────────────

interface OrganizationSettingsCardProps {
  settings: OrganizationSettings;
  onUpdate: (patch: OrganizationSettingsUpdate) => void;
  saving: boolean;
}

export function OrganizationSettingsCard({
  settings,
  onUpdate,
  saving,
}: OrganizationSettingsCardProps) {
  const [name, setName] = useState(settings.organization_name);
  const [timezone, setTimezone] = useState(settings.timezone);
  const [currency, setCurrency] = useState(settings.currency);
  const [dateFormat, setDateFormat] = useState(settings.date_format);
  const [language, setLanguage] = useState(settings.language);
  const [invoiceDays, setInvoiceDays] = useState(String(settings.default_invoice_due_days));
  const [trainingDays, setTrainingDays] = useState(String(settings.default_training_duration_days));
  const [logoUrl, setLogoUrl] = useState(settings.logo_url ?? "");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdate({
      organization_name: name,
      timezone,
      currency,
      date_format: dateFormat,
      language,
      default_invoice_due_days: parseInt(invoiceDays, 10),
      default_training_duration_days: parseInt(trainingDays, 10),
      logo_url: logoUrl || null,
    });
  };

  return (
    <form data-testid="settings-card" onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Organization profile */}
        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Organization Name
          </label>
          <input
            data-testid="input-org-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Timezone
          </label>
          <input
            data-testid="input-timezone"
            type="text"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          />
        </div>

        {/* Regional settings */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Currency
          </label>
          <select
            data-testid="select-currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          >
            {ADMIN_CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Date Format
          </label>
          <select
            data-testid="select-date-format"
            value={dateFormat}
            onChange={(e) => setDateFormat(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          >
            {ADMIN_DATE_FORMATS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Language
          </label>
          <select
            data-testid="select-language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          >
            {ADMIN_LANGUAGES.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>

        {/* Business defaults */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Default Invoice Due Days
          </label>
          <input
            data-testid="input-invoice-days"
            type="number"
            min={1}
            max={365}
            value={invoiceDays}
            onChange={(e) => setInvoiceDays(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Default Training Duration (days)
          </label>
          <input
            data-testid="input-training-days"
            type="number"
            min={1}
            max={365}
            value={trainingDays}
            onChange={(e) => setTrainingDays(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          />
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Logo URL
          </label>
          <input
            data-testid="input-logo-url"
            type="url"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder="https://cdn.example.com/logo.png"
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
          />
        </div>
      </div>

      <div className="flex justify-end">
        <button
          data-testid="btn-save-settings"
          type="submit"
          disabled={saving}
          className="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save Settings"}
        </button>
      </div>
    </form>
  );
}

// ── OrganizationDashboard ─────────────────────────────────────────────────────

interface OrganizationDashboardProps {
  organizationName: string;
  isActive: boolean;
  moduleCount: number;
  healthyModuleCount: number;
  totalRecords: number;
  settingsLastUpdated: string;
}

export function OrganizationDashboard({
  organizationName,
  isActive,
  moduleCount,
  healthyModuleCount,
  totalRecords,
  settingsLastUpdated,
}: OrganizationDashboardProps) {
  return (
    <div data-testid="org-dashboard" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 data-testid="dashboard-org-name" className="text-xl font-semibold text-gray-900 dark:text-gray-100">
          {organizationName}
        </h2>
        <span
          data-testid="dashboard-active-badge"
          data-active={isActive ? "true" : "false"}
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            isActive
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
              : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
          }`}
        >
          {isActive ? "Active" : "Inactive"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div data-testid="stat-module-count" className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">Modules</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{moduleCount}</p>
        </div>
        <div data-testid="stat-healthy-count" className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">Healthy</p>
          <p className="mt-1 text-2xl font-bold text-green-600">{healthyModuleCount}</p>
        </div>
        <div data-testid="stat-total-records" className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">Total Records</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">{totalRecords.toLocaleString()}</p>
        </div>
        <div data-testid="stat-last-updated" className="rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">Last Updated</p>
          <p className="mt-1 text-sm font-medium text-gray-900 dark:text-gray-100">
            {new Date(settingsLastUpdated).toLocaleDateString()}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── AdminCenter ───────────────────────────────────────────────────────────────

type AdminTab = "dashboard" | "settings" | "modules" | "status";

export function AdminCenter() {
  const [activeTab, setActiveTab] = useState<AdminTab>("dashboard");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const { data: settingsData, isLoading: settingsLoading, isError: settingsError } = useAdminSettings();
  const { data: dashboardData, isLoading: dashboardLoading } = useAdminDashboard();
  const { data: modulesData } = useAdminModules();
  const { data: statusData, isLoading: statusLoading } = useAdminSystemStatus();
  const updateMutation = useUpdateAdminSettings();

  const settings = settingsData?.data;
  const dashboard = dashboardData?.data;
  const modules = modulesData?.data;
  const systemStatus = statusData?.data;

  const handleUpdate = (patch: OrganizationSettingsUpdate) => {
    setSaveError(null);
    setSaveSuccess(false);
    updateMutation.mutate(patch, {
      onSuccess: () => setSaveSuccess(true),
      onError: (err) => setSaveError(err.message),
    });
  };

  const tabs: { id: AdminTab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "settings", label: "Settings" },
    { id: "modules", label: "Modules" },
    { id: "status", label: "System Status" },
  ];

  return (
    <div data-testid="admin-center" className="space-y-6">
      {/* Tab navigation */}
      <nav data-testid="admin-tabs" className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            data-active={activeTab === tab.id ? "true" : "false"}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab panels */}
      {activeTab === "dashboard" && (
        <div data-testid="panel-dashboard">
          {dashboardLoading && (
            <div data-testid="dashboard-loading" className="py-8 text-center text-sm text-gray-500">
              Loading dashboard…
            </div>
          )}
          {!dashboardLoading && dashboard && (
            <OrganizationDashboard
              organizationName={dashboard.organization_name}
              isActive={dashboard.is_active}
              moduleCount={dashboard.module_count}
              healthyModuleCount={dashboard.healthy_module_count}
              totalRecords={dashboard.total_records}
              settingsLastUpdated={dashboard.settings_last_updated}
            />
          )}
        </div>
      )}

      {activeTab === "settings" && (
        <div data-testid="panel-settings">
          {settingsLoading && (
            <div data-testid="settings-loading" className="py-8 text-center text-sm text-gray-500">
              Loading settings…
            </div>
          )}
          {settingsError && (
            <div data-testid="settings-error" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
              Failed to load settings.
            </div>
          )}
          {!settingsLoading && !settingsError && settings && (
            <>
              {saveError && (
                <div data-testid="save-error" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {saveError}
                </div>
              )}
              {saveSuccess && (
                <div data-testid="save-success" className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-700">
                  Settings saved successfully.
                </div>
              )}
              <OrganizationSettingsCard
                settings={settings}
                onUpdate={handleUpdate}
                saving={updateMutation.isPending}
              />
            </>
          )}
        </div>
      )}

      {activeTab === "modules" && (
        <div data-testid="panel-modules">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            Registered Modules ({modules?.total ?? 0})
          </h3>
          <ul data-testid="module-list" className="space-y-1">
            {(modules?.modules ?? MODULE_NAMES).map((name) => (
              <li
                key={name}
                data-testid={`module-item-${name}`}
                className="flex items-center gap-2 rounded-md px-3 py-2 bg-gray-50 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 capitalize"
              >
                <span className="h-2 w-2 rounded-full bg-indigo-500 flex-shrink-0" />
                {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {activeTab === "status" && (
        <div data-testid="panel-status">
          {statusLoading && (
            <div data-testid="status-loading" className="py-8 text-center text-sm text-gray-500">
              Loading system status…
            </div>
          )}
          {!statusLoading && systemStatus && (
            <SystemStatusPanel status={systemStatus} />
          )}
        </div>
      )}
    </div>
  );
}
