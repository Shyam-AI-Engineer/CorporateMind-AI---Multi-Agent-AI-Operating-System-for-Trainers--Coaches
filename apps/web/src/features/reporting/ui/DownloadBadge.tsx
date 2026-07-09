"use client";

import type { ReportExport } from "../types";

interface Props {
  report: ReportExport;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DownloadBadge({ report }: Props) {
  if (report.status !== "ready" || !report.download_name) {
    return null;
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {report.download_name}
      </span>
      {report.file_size_bytes != null && (
        <span className="text-xs text-gray-400 dark:text-gray-500">
          ({formatBytes(report.file_size_bytes)})
        </span>
      )}
      {report.row_count != null && (
        <span className="text-xs text-gray-400 dark:text-gray-500">
          · {report.row_count.toLocaleString()} rows
        </span>
      )}
    </div>
  );
}
