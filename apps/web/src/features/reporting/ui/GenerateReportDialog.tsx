"use client";

import { useState } from "react";
import type { ReportFormat, ReportType } from "../types";
import { REPORT_FORMAT_LABELS, REPORT_TYPE_LABELS } from "../types";
import { useGenerateReport } from "../api/use-reporting";

const REPORT_TYPES: ReportType[] = [
  "customers",
  "training",
  "invoices",
  "payments",
  "executive_kpis",
  "workflow_analytics",
  "audit_logs",
];

const FORMATS: ReportFormat[] = ["csv", "xlsx"];

interface Props {
  workspaceId: string;
  trigger?: React.ReactNode;
}

export function GenerateReportDialog({ workspaceId, trigger }: Props) {
  const [open, setOpen] = useState(false);
  const [reportType, setReportType] = useState<ReportType>("customers");
  const [format, setFormat] = useState<ReportFormat>("csv");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const generate = useGenerateReport(workspaceId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    generate.mutate(
      {
        workspace_id: workspaceId,
        report_type: reportType,
        format,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setDateFrom("");
          setDateTo("");
        },
      }
    );
  }

  return (
    <>
      {trigger ? (
        <span
          onClick={() => setOpen(true)}
          onKeyDown={(e) => e.key === "Enter" && setOpen(true)}
          className="inline-flex cursor-pointer"
        >
          {trigger}
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Generate Report
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Generate Report"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          data-testid="generate-report-dialog"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-gray-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
              Generate Report
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="report-type"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Report Type
                </label>
                <select
                  id="report-type"
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value as ReportType)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                >
                  {REPORT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {REPORT_TYPE_LABELS[t]}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="format"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Format
                </label>
                <select
                  id="format"
                  value={format}
                  onChange={(e) => setFormat(e.target.value as ReportFormat)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                >
                  {FORMATS.map((f) => (
                    <option key={f} value={f}>
                      {REPORT_FORMAT_LABELS[f]}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="date-from"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    From (optional)
                  </label>
                  <input
                    id="date-from"
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                  />
                </div>
                <div>
                  <label
                    htmlFor="date-to"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    To (optional)
                  </label>
                  <input
                    id="date-to"
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                  />
                </div>
              </div>

              {generate.isError && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {generate.error?.message ?? "Generation failed."}
                </p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={generate.isPending}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {generate.isPending ? "Generating…" : "Generate"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
