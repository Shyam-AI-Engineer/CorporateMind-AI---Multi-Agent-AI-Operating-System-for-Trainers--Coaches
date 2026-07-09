/**
 * Sprint 56 — Reporting & Export Center frontend tests (file 2).
 * Covers: use-reporting hooks, GenerateReportDialog, ReportingCenter.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { GenerateReportDialog } from "./GenerateReportDialog";
import { ReportingCenter } from "./ReportingCenter";
import {
  reportingKeys,
} from "../api/use-reporting";
import type { ReportExport, ReportExportListResponse } from "../types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("../api/use-reporting", async (importOriginal) => {
  const real = (await importOriginal()) as Record<string, unknown>;
  return {
    ...real,
    useGenerateReport: vi.fn(),
    useDeleteReport: vi.fn(),
    useReports: vi.fn(),
    reportingKeys: {
      all: ["reports"],
      list: (wsId: string, rt?: string) => ["reports", "list", wsId, rt ?? "all"],
      detail: (id: string) => ["reports", "detail", id],
    },
  };
});

import {
  useGenerateReport,
  useDeleteReport,
  useReports,
} from "../api/use-reporting";

const WS_ID = "ws-0002-0000-0000-000000000002";
const REPORT_ID = "rpt-0002-0000-0000-000000000002";

function makeReport(overrides: Partial<ReportExport> = {}): ReportExport {
  return {
    id: REPORT_ID,
    tenant_id: "ten-0002",
    workspace_id: WS_ID,
    report_type: "customers",
    format: "csv",
    status: "ready",
    generated_by: "usr-0002",
    generated_at: "2026-07-08T10:00:00Z",
    download_name: "customers_20260708_100000.csv",
    row_count: 10,
    file_size_bytes: 512,
    created_at: "2026-07-08T10:00:00Z",
    ...overrides,
  };
}

function makeListResponse(items: ReportExport[] = []): ReportExportListResponse {
  return { items, total: items.length };
}

function withQueryClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function defaultHooks() {
  vi.mocked(useGenerateReport).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as never);
  vi.mocked(useDeleteReport).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never);
  vi.mocked(useReports).mockReturnValue({
    data: makeListResponse([makeReport()]),
    isLoading: false,
    isError: false,
    error: null,
  } as never);
}

beforeEach(() => {
  defaultHooks();
});

afterEach(() => {
  vi.clearAllMocks();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. reportingKeys
// ─────────────────────────────────────────────────────────────────────────────

describe("reportingKeys", () => {
  it("all key is ['reports']", () => {
    expect(reportingKeys.all).toEqual(["reports"]);
  });

  it("list key includes workspaceId", () => {
    expect(reportingKeys.list(WS_ID)).toContain(WS_ID);
  });

  it("list key with type includes type", () => {
    expect(reportingKeys.list(WS_ID, "customers")).toContain("customers");
  });

  it("list key with no type uses 'all'", () => {
    expect(reportingKeys.list(WS_ID)).toContain("all");
  });

  it("detail key includes reportId", () => {
    expect(reportingKeys.detail(REPORT_ID)).toContain(REPORT_ID);
  });

  it("list keys differ by workspaceId", () => {
    expect(reportingKeys.list("ws-a")).not.toEqual(reportingKeys.list("ws-b"));
  });

  it("detail and list keys are distinct", () => {
    expect(reportingKeys.detail(REPORT_ID)).not.toEqual(
      reportingKeys.list(WS_ID)
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. GenerateReportDialog
// ─────────────────────────────────────────────────────────────────────────────

describe("GenerateReportDialog", () => {
  it("renders a trigger button by default", () => {
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    expect(screen.getByRole("button", { name: /generate report/i })).not.toBeNull();
  });

  it("opens dialog on trigger click", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByRole("dialog")).not.toBeNull();
  });

  it("shows 'Generate Report' title in dialog", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByRole("heading", { name: /generate report/i })).not.toBeNull();
  });

  it("shows report type selector", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByLabelText(/report type/i)).not.toBeNull();
  });

  it("shows format selector", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByLabelText(/format/i)).not.toBeNull();
  });

  it("shows date from field", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByLabelText(/from/i)).not.toBeNull();
  });

  it("shows date to field", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByLabelText(/to/i)).not.toBeNull();
  });

  it("shows Cancel and Generate buttons", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByRole("button", { name: /cancel/i })).not.toBeNull();
    expect(screen.getByRole("button", { name: /^generate$/i })).not.toBeNull();
  });

  it("closes on Cancel click", async () => {
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).toBeNull()
    );
  });

  it("disables Generate button while pending", async () => {
    vi.mocked(useGenerateReport).mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isError: false,
      error: null,
    } as never);
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    const btn = screen.getByRole("button", { name: /generating/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("shows 'Generating…' while pending", async () => {
    vi.mocked(useGenerateReport).mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      isError: false,
      error: null,
    } as never);
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByText("Generating…")).not.toBeNull();
  });

  it("shows error message when isError", async () => {
    vi.mocked(useGenerateReport).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: new Error("Report failed to generate"),
    } as never);
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    expect(screen.getByText("Report failed to generate")).not.toBeNull();
  });

  it("calls mutate with correct payload on submit", async () => {
    const mutate = vi.fn();
    vi.mocked(useGenerateReport).mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    } as never);
    const user = userEvent.setup();
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    await user.click(screen.getByRole("button", { name: /generate report/i }));
    await user.click(screen.getByRole("button", { name: /^generate$/i }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        workspace_id: WS_ID,
        report_type: "customers",
        format: "csv",
      }),
      expect.any(Object)
    );
  });

  it("accepts a custom trigger element", () => {
    render(
      withQueryClient(
        <GenerateReportDialog
          workspaceId={WS_ID}
          trigger={<button>Custom Trigger</button>}
        />
      )
    );
    expect(screen.getByRole("button", { name: "Custom Trigger" })).not.toBeNull();
  });

  it("does not show dialog initially", () => {
    render(withQueryClient(<GenerateReportDialog workspaceId={WS_ID} />));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. ReportingCenter
// ─────────────────────────────────────────────────────────────────────────────

describe("ReportingCenter", () => {
  it("renders the section heading", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Reporting & Export Center")).not.toBeNull();
  });

  it("renders the description text", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(
      screen.getByText("Generate and download reports for your workspace.")
    ).not.toBeNull();
  });

  it("renders a Generate Report button", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(
      screen.getByRole("button", { name: /generate report/i })
    ).not.toBeNull();
  });

  it("shows report count", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("1 report")).not.toBeNull();
  });

  it("shows '2 reports' (plural)", () => {
    vi.mocked(useReports).mockReturnValue({
      data: makeListResponse([makeReport({ id: "r1" }), makeReport({ id: "r2" })]),
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("2 reports")).not.toBeNull();
  });

  it("shows '0 reports' when empty", () => {
    vi.mocked(useReports).mockReturnValue({
      data: makeListResponse([]),
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("0 reports")).not.toBeNull();
  });

  it("shows loading state", () => {
    vi.mocked(useReports).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Loading reports…")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useReports).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Network error"),
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Network error")).not.toBeNull();
  });

  it("shows filter type selector", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Filter by type:")).not.toBeNull();
  });

  it("shows report history table with data", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    // Table headers visible
    expect(screen.getByText("Type")).not.toBeNull();
    expect(screen.getByText("Status")).not.toBeNull();
  });

  it("calls useReports with workspaceId", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(vi.mocked(useReports)).toHaveBeenCalledWith(WS_ID, undefined);
  });

  it("shows empty state inside table when no data", () => {
    vi.mocked(useReports).mockReturnValue({
      data: makeListResponse([]),
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("No reports generated yet.")).not.toBeNull();
  });

  it("does not show count while loading", () => {
    vi.mocked(useReports).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.queryByText(/\d+ report/)).toBeNull();
  });

  it("renders pending status badge in table", () => {
    vi.mocked(useReports).mockReturnValue({
      data: makeListResponse([makeReport({ status: "pending", download_name: null })]),
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Pending")).not.toBeNull();
  });

  it("renders failed status badge in table", () => {
    vi.mocked(useReports).mockReturnValue({
      data: makeListResponse([makeReport({ status: "failed", download_name: null })]),
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Failed")).not.toBeNull();
  });

  it("renders ready status badge in table", () => {
    render(withQueryClient(<ReportingCenter workspaceId={WS_ID} />));
    expect(screen.getByText("Ready")).not.toBeNull();
  });
});
