/**
 * Sprint 56 — Reporting & Export Center frontend tests (file 1).
 * Covers: types, constants, ReportStatusBadge, DownloadBadge, ReportHistoryTable.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { describe, it, expect, beforeEach } from "vitest";

// ── Types & constants ─────────────────────────────────────────────────────────
import {
  REPORT_TYPE_LABELS,
  REPORT_FORMAT_LABELS,
  type ReportExport,
  type ReportType,
  type ReportFormat,
  type ReportStatus,
} from "../types";

// ── Components ────────────────────────────────────────────────────────────────
import { ReportStatusBadge } from "./ReportStatusBadge";
import { DownloadBadge } from "./DownloadBadge";
import { ReportHistoryTable } from "./ReportHistoryTable";

// ── Mock TanStack Query hooks used inside ReportHistoryTable ──────────────────
const mockDeleteReport = vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false });
const mockGenerateReport = vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, error: null });
const mockUseReports = vi.fn().mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isError: false, error: null });

vi.mock("../api/use-reporting", () => ({
  useDeleteReport: (...args: unknown[]) => mockDeleteReport(...args),
  useGenerateReport: (...args: unknown[]) => mockGenerateReport(...args),
  useReports: (...args: unknown[]) => mockUseReports(...args),
  reportingKeys: {
    all: ["reports"],
    list: (wsId: string) => ["reports", "list", wsId, "all"],
    detail: (id: string) => ["reports", "detail", id],
  },
}));


// ── Helpers ───────────────────────────────────────────────────────────────────

const WS_ID = "ws-0001-0000-0000-000000000001";
const USER_ID = "usr-0001-0000-0000-000000000001";
const REPORT_ID = "rpt-0001-0000-0000-000000000001";
const TENANT_ID = "ten-0001-0000-0000-000000000001";

function makeReport(overrides: Partial<ReportExport> = {}): ReportExport {
  return {
    id: REPORT_ID,
    tenant_id: TENANT_ID,
    workspace_id: WS_ID,
    report_type: "customers",
    format: "csv",
    status: "ready",
    generated_by: USER_ID,
    generated_at: "2026-07-08T10:00:00Z",
    download_name: "customers_20260708_100000.csv",
    row_count: 42,
    file_size_bytes: 1024,
    created_at: "2026-07-08T10:00:00Z",
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. Type constants
// ─────────────────────────────────────────────────────────────────────────────

describe("REPORT_TYPE_LABELS", () => {
  it("has label for customers", () => {
    expect(REPORT_TYPE_LABELS.customers).toBe("Customers");
  });

  it("has label for training", () => {
    expect(REPORT_TYPE_LABELS.training).toBe("Training Engagements");
  });

  it("has label for invoices", () => {
    expect(REPORT_TYPE_LABELS.invoices).toBe("Invoices");
  });

  it("has label for payments", () => {
    expect(REPORT_TYPE_LABELS.payments).toBe("Payments");
  });

  it("has label for executive_kpis", () => {
    expect(REPORT_TYPE_LABELS.executive_kpis).toBe("Executive KPIs");
  });

  it("has label for workflow_analytics", () => {
    expect(REPORT_TYPE_LABELS.workflow_analytics).toBe("Workflow Analytics");
  });

  it("has label for audit_logs", () => {
    expect(REPORT_TYPE_LABELS.audit_logs).toBe("Audit Logs");
  });

  it("has exactly 7 entries", () => {
    expect(Object.keys(REPORT_TYPE_LABELS)).toHaveLength(7);
  });
});

describe("REPORT_FORMAT_LABELS", () => {
  it("has label for csv", () => {
    expect(REPORT_FORMAT_LABELS.csv).toBe("CSV");
  });

  it("has label for xlsx", () => {
    expect(REPORT_FORMAT_LABELS.xlsx).toBe("Excel (XLSX)");
  });

  it("has exactly 2 entries", () => {
    expect(Object.keys(REPORT_FORMAT_LABELS)).toHaveLength(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. ReportStatusBadge
// ─────────────────────────────────────────────────────────────────────────────

describe("ReportStatusBadge", () => {
  it("renders 'Ready' for ready status", () => {
    render(<ReportStatusBadge status="ready" />);
    expect(screen.getByText("Ready")).not.toBeNull();
  });

  it("renders 'Pending' for pending status", () => {
    render(<ReportStatusBadge status="pending" />);
    expect(screen.getByText("Pending")).not.toBeNull();
  });

  it("renders 'Failed' for failed status", () => {
    render(<ReportStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).not.toBeNull();
  });

  it("applies green class for ready", () => {
    const { container } = render(<ReportStatusBadge status="ready" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("green");
  });

  it("applies yellow class for pending", () => {
    const { container } = render(<ReportStatusBadge status="pending" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("yellow");
  });

  it("applies red class for failed", () => {
    const { container } = render(<ReportStatusBadge status="failed" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("red");
  });

  it("renders as a span element", () => {
    const { container } = render(<ReportStatusBadge status="ready" />);
    expect(container.querySelector("span")).not.toBeNull();
  });

  it("has rounded-full class", () => {
    const { container } = render(<ReportStatusBadge status="ready" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("rounded-full");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. DownloadBadge
// ─────────────────────────────────────────────────────────────────────────────

describe("DownloadBadge", () => {
  it("renders null for pending status", () => {
    const { container } = render(
      <DownloadBadge report={makeReport({ status: "pending", download_name: null })} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders null for failed status", () => {
    const { container } = render(
      <DownloadBadge report={makeReport({ status: "failed", download_name: null })} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders null when download_name is null even if ready", () => {
    const { container } = render(
      <DownloadBadge report={makeReport({ status: "ready", download_name: null })} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows download_name for ready status", () => {
    render(<DownloadBadge report={makeReport()} />);
    expect(
      screen.getByText("customers_20260708_100000.csv")
    ).not.toBeNull();
  });

  it("shows formatted file size in KB", () => {
    render(<DownloadBadge report={makeReport({ file_size_bytes: 2048 })} />);
    expect(screen.getByText("(2.0 KB)")).not.toBeNull();
  });

  it("shows file size in B for < 1024", () => {
    render(<DownloadBadge report={makeReport({ file_size_bytes: 512 })} />);
    expect(screen.getByText("(512 B)")).not.toBeNull();
  });

  it("shows row count", () => {
    render(<DownloadBadge report={makeReport({ row_count: 42 })} />);
    expect(screen.getByText("· 42 rows")).not.toBeNull();
  });

  it("does not show row count when null", () => {
    render(<DownloadBadge report={makeReport({ row_count: null })} />);
    expect(screen.queryByText(/rows/)).toBeNull();
  });

  it("does not show size when null", () => {
    render(<DownloadBadge report={makeReport({ file_size_bytes: null })} />);
    expect(screen.queryByText(/KB|MB|B\)/)).toBeNull();
  });

  it("shows file size in MB for large files", () => {
    render(
      <DownloadBadge report={makeReport({ file_size_bytes: 2 * 1024 * 1024 })} />
    );
    expect(screen.getByText("(2.0 MB)")).not.toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. ReportHistoryTable
// ─────────────────────────────────────────────────────────────────────────────

describe("ReportHistoryTable", () => {
  it("shows empty state when no reports", () => {
    render(<ReportHistoryTable reports={[]} workspaceId={WS_ID} />);
    expect(screen.getByText("No reports generated yet.")).not.toBeNull();
  });

  it("renders a row per report", () => {
    const reports = [
      makeReport({ id: "r1", report_type: "customers" }),
      makeReport({ id: "r2", report_type: "invoices" }),
    ];
    render(<ReportHistoryTable reports={reports} workspaceId={WS_ID} />);
    expect(screen.getByText("Customers")).not.toBeNull();
    expect(screen.getByText("Invoices")).not.toBeNull();
  });

  it("renders column headers", () => {
    render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    expect(screen.getByText("Type")).not.toBeNull();
    expect(screen.getByText("Status")).not.toBeNull();
    expect(screen.getByText("File")).not.toBeNull();
    expect(screen.getByText("Generated")).not.toBeNull();
    expect(screen.getByText("Actions")).not.toBeNull();
  });

  it("renders ReportStatusBadge for each row", () => {
    render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    expect(screen.getByText("Ready")).not.toBeNull();
  });

  it("renders DownloadBadge for ready reports", () => {
    render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    expect(
      screen.getByText("customers_20260708_100000.csv")
    ).not.toBeNull();
  });

  it("has delete button for each row", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ id: "r1" }), makeReport({ id: "r2" })]}
        workspaceId={WS_ID}
      />
    );
    const btns = screen.getAllByRole("button", { name: /delete/i });
    expect(btns).toHaveLength(2);
  });

  it("shows em-dash for null generated_at", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ generated_at: null, status: "pending" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("—")).not.toBeNull();
  });

  it("calls deleteReport.mutate on delete click", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    mockDeleteReport.mockReturnValue({ mutate, isPending: false });

    render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    await user.click(screen.getByRole("button", { name: /delete/i }));
    expect(mutate).toHaveBeenCalledWith(REPORT_ID);
  });

  it("disables delete button while pending", () => {
    mockDeleteReport.mockReturnValue({ mutate: vi.fn(), isPending: true });

    render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    const btn = screen.getByRole("button", { name: /delete/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("shows training label for training report type", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ report_type: "training" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("Training Engagements")).not.toBeNull();
  });

  it("shows workflow analytics label", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ report_type: "workflow_analytics" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("Workflow Analytics")).not.toBeNull();
  });

  it("shows executive KPIs label", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ report_type: "executive_kpis" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("Executive KPIs")).not.toBeNull();
  });

  it("shows audit logs label", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ report_type: "audit_logs" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("Audit Logs")).not.toBeNull();
  });

  it("shows payment label", () => {
    render(
      <ReportHistoryTable
        reports={[makeReport({ report_type: "payments" })]}
        workspaceId={WS_ID}
      />
    );
    expect(screen.getByText("Payments")).not.toBeNull();
  });

  it("renders a table element", () => {
    const { container } = render(
      <ReportHistoryTable reports={[makeReport()]} workspaceId={WS_ID} />
    );
    expect(container.querySelector("table")).not.toBeNull();
  });
});
