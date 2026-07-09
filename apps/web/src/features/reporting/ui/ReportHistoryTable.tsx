"use client";

import type { ReportExport, ReportType } from "../types";
import { REPORT_TYPE_LABELS } from "../types";
import { ReportStatusBadge } from "./ReportStatusBadge";
import { DownloadBadge } from "./DownloadBadge";
import { useDeleteReport } from "../api/use-reporting";

interface Props {
  reports: ReportExport[];
  workspaceId: string;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function ReportHistoryTable({ reports, workspaceId }: Props) {
  const deleteReport = useDeleteReport(workspaceId);

  if (reports.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-gray-500 dark:text-gray-400">
        No reports generated yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/50">
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">
              Type
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">
              Status
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">
              File
            </th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">
              Generated
            </th>
            <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {reports.map((r) => (
            <tr
              key={r.id}
              className="bg-white transition-colors hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900/40"
            >
              <td className="px-4 py-3 font-medium">
                {REPORT_TYPE_LABELS[r.report_type as ReportType] ?? r.report_type}
              </td>
              <td className="px-4 py-3">
                <ReportStatusBadge status={r.status} />
              </td>
              <td className="px-4 py-3">
                <DownloadBadge report={r} />
              </td>
              <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                {formatDate(r.generated_at)}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  className="text-sm text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50"
                  disabled={deleteReport.isPending}
                  onClick={() => deleteReport.mutate(r.id)}
                  aria-label={`Delete report ${r.download_name ?? r.id}`}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
