"use client";

import { useState } from "react";
import type { ReportType } from "../types";
import { REPORT_TYPE_LABELS } from "../types";
import { useReports } from "../api/use-reporting";
import { GenerateReportDialog } from "./GenerateReportDialog";
import { ReportHistoryTable } from "./ReportHistoryTable";

const ALL_TYPES = "all";

interface Props {
  workspaceId: string;
}

export function ReportingCenter({ workspaceId }: Props) {
  const [filterType, setFilterType] = useState<ReportType | typeof ALL_TYPES>(
    ALL_TYPES
  );

  const { data, isLoading, isError, error } = useReports(
    workspaceId,
    filterType === ALL_TYPES ? undefined : filterType
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Reporting & Export Center
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Generate and download reports for your workspace.
          </p>
        </div>
        <GenerateReportDialog workspaceId={workspaceId} />
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          Filter by type:
        </span>
        <select
          value={filterType}
          onChange={(e) =>
            setFilterType(e.target.value as ReportType | typeof ALL_TYPES)
          }
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
        >
          <option value={ALL_TYPES}>All types</option>
          {(Object.keys(REPORT_TYPE_LABELS) as ReportType[]).map((t) => (
            <option key={t} value={t}>
              {REPORT_TYPE_LABELS[t]}
            </option>
          ))}
        </select>

        {data && (
          <span className="ml-auto text-sm text-gray-400 dark:text-gray-500">
            {data.total} report{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12 text-sm text-gray-500 dark:text-gray-400">
          Loading reports…
        </div>
      )}

      {isError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
          {(error as Error)?.message ?? "Failed to load reports."}
        </div>
      )}

      {!isLoading && !isError && (
        <ReportHistoryTable
          reports={data?.items ?? []}
          workspaceId={workspaceId}
        />
      )}
    </div>
  );
}
