"use client";

import React from "react";
import {
  useApiHealth,
  useCacheHealth,
  useDatabaseHealth,
  useModuleHealth,
  usePlatformSummary,
  useRecentErrors,
} from "@/features/observability/api/use-observability";
import { PlatformHealthCards } from "@/features/observability/ui/PlatformHealthCards";
import { ModuleHealthTable } from "@/features/observability/ui/ModuleHealthTable";
import { CacheHealthPanel } from "@/features/observability/ui/CacheHealthPanel";
import { DatabaseHealthPanel } from "@/features/observability/ui/DatabaseHealthPanel";
import { ApiHealthPanel } from "@/features/observability/ui/ApiHealthPanel";
import { DiagnosticsPanel } from "@/features/observability/ui/DiagnosticsPanel";

export function ObservabilityCenter() {
  const summary = usePlatformSummary();
  const cache = useCacheHealth();
  const database = useDatabaseHealth();
  const api = useApiHealth();
  const modules = useModuleHealth();
  const errors = useRecentErrors();

  const isLoading =
    summary.isLoading ||
    cache.isLoading ||
    database.isLoading ||
    api.isLoading ||
    modules.isLoading ||
    errors.isLoading;

  const hasError =
    summary.isError ||
    cache.isError ||
    database.isError ||
    api.isError ||
    modules.isError ||
    errors.isError;

  if (isLoading) {
    return (
      <div data-testid="observability-loading" className="flex items-center justify-center py-16">
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading platform diagnostics…</p>
      </div>
    );
  }

  if (hasError) {
    return (
      <div data-testid="observability-error" className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-4">
        <p className="text-sm text-red-700 dark:text-red-300">
          Failed to load observability data. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="observability-center" className="space-y-8">
      {/* Section: Platform Overview */}
      <section aria-labelledby="platform-overview-heading">
        <h2
          id="platform-overview-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Platform Overview
        </h2>
        {summary.data && <PlatformHealthCards summary={summary.data} />}
      </section>

      {/* Section: Infrastructure */}
      <section aria-labelledby="infra-heading">
        <h2
          id="infra-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Infrastructure
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {cache.data && <CacheHealthPanel health={cache.data} />}
          {database.data && <DatabaseHealthPanel health={database.data} />}
          {api.data && <ApiHealthPanel health={api.data} />}
        </div>
      </section>

      {/* Section: Module Health */}
      <section aria-labelledby="modules-heading">
        <h2
          id="modules-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Module Health
        </h2>
        {modules.data && <ModuleHealthTable health={modules.data} />}
      </section>

      {/* Section: Diagnostics */}
      <section aria-labelledby="diagnostics-heading">
        <h2
          id="diagnostics-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Diagnostics
        </h2>
        {errors.data && <DiagnosticsPanel errors={errors.data} />}
      </section>
    </div>
  );
}
