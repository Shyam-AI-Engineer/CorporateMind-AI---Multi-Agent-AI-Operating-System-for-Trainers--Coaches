/**
 * Frontend unit tests — Sprint 59: Bulk Operations Center (part 2).
 * Covers: CsvUploadDialog, BulkOperationsCenter (loading/error/happy path).
 * Module-level vi.fn() mock pattern — no jest-dom matchers.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import type {
  BulkOperationOut,
  BulkOperationListOut,
  CsvValidationOut,
} from "@/features/bulk_operations/types";
import { CsvUploadDialog } from "@/features/bulk_operations/ui/CsvUploadDialog";
import { BulkOperationsCenter } from "@/features/bulk_operations/ui/BulkOperationsCenter";

// ── Module-level mock variables ────────────────────────────────────────────

const mockUseBulkOperationList = vi.fn();
const mockUseValidateCsv = vi.fn();
const mockUseImportCsv = vi.fn();
const mockUseBulkArchive = vi.fn();
const mockUseBulkAssign = vi.fn();
const mockUseBulkStatusUpdate = vi.fn();

vi.mock("@/features/bulk_operations/api/use-bulk-operations", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return {
    ...original,
    useBulkOperationList: (...args: unknown[]) => mockUseBulkOperationList(...args),
    useValidateCsv: (...args: unknown[]) => mockUseValidateCsv(...args),
    useImportCsv: (...args: unknown[]) => mockUseImportCsv(...args),
    useBulkArchive: (...args: unknown[]) => mockUseBulkArchive(...args),
    useBulkAssign: (...args: unknown[]) => mockUseBulkAssign(...args),
    useBulkStatusUpdate: (...args: unknown[]) => mockUseBulkStatusUpdate(...args),
  };
});

afterEach(() => vi.clearAllMocks());

const NOW = "2026-07-09T10:00:00Z";
const WS_ID = "ws-aabbccdd";
const USER_ID = "user-1122334455";

function makeOp(overrides: Partial<BulkOperationOut> = {}): BulkOperationOut {
  return {
    id: "op-111",
    workspace_id: WS_ID,
    operation_type: "csv_import",
    entity_type: "customers",
    status: "completed",
    requested_by: USER_ID,
    total_records: 5,
    processed_records: 5,
    successful_records: 5,
    failed_records: 0,
    started_at: NOW,
    completed_at: NOW,
    error_summary: null,
    created_at: NOW,
    ...overrides,
  };
}

function makeList(ops: BulkOperationOut[] = []): BulkOperationListOut {
  return { operations: ops, total: ops.length };
}

function makeValidation(overrides: Partial<CsvValidationOut> = {}): CsvValidationOut {
  return {
    entity_type: "customers",
    total_rows: 2,
    valid_rows: 2,
    invalid_rows: 0,
    dry_run: false,
    results: [
      { row: 1, valid: true, data: { company_name: "A" }, errors: [] },
      { row: 2, valid: true, data: { company_name: "B" }, errors: [] },
    ],
    ...overrides,
  };
}

function setupAllMocks(opts: { loading?: boolean; error?: boolean } = {}) {
  const loading = opts.loading ?? false;
  const error = opts.error ?? false;

  const validateMutation = {
    mutateAsync: vi.fn().mockResolvedValue(makeValidation()),
    isPending: false,
    isError: false,
    error: null,
  };
  const importMutation = {
    mutateAsync: vi.fn().mockResolvedValue(makeOp()),
    isPending: false,
    isError: false,
    error: null,
  };

  mockUseBulkOperationList.mockReturnValue({
    isLoading: loading,
    isError: error,
    data: loading || error ? undefined : makeList([makeOp()]),
  });
  mockUseValidateCsv.mockReturnValue(validateMutation);
  mockUseImportCsv.mockReturnValue(importMutation);
  mockUseBulkArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
  mockUseBulkAssign.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
  mockUseBulkStatusUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });

  return { validateMutation, importMutation };
}

// ── CsvUploadDialog ────────────────────────────────────────────────────────

describe("CsvUploadDialog", () => {
  it("renders the dialog", () => {
    const onValidate = vi.fn();
    const onImport = vi.fn();
    render(<CsvUploadDialog onValidate={onValidate} onImport={onImport} />);
    expect(screen.getByTestId("csv-upload-dialog")).not.toBeNull();
  });

  it("renders entity type select", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    expect(screen.getByTestId("entity-type-select")).not.toBeNull();
  });

  it("entity type select defaults to customers", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.value).toBe("customers");
  });

  it("entity type select has 4 options", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.options.length).toBe(4);
  });

  it("entity type select can be changed", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "business_tasks" } });
    expect(select.value).toBe("business_tasks");
  });

  it("renders file input", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    expect(screen.getByTestId("csv-file-input")).not.toBeNull();
  });

  it("validate button is initially disabled (no file)", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    const btn = screen.getByTestId("validate-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("import button is initially disabled (no file)", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    const btn = screen.getByTestId("import-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("validate button shows 'Validating…' when isValidating", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} isValidating={true} />);
    expect(screen.getByTestId("validate-btn").textContent).toBe("Validating…");
  });

  it("import button shows 'Importing…' when isImporting", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} isImporting={true} />);
    expect(screen.getByTestId("import-btn").textContent).toBe("Importing…");
  });

  it("no file-name shown before file selection", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    expect(screen.queryByTestId("file-name")).toBeNull();
  });

  it("no parse-error initially", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    expect(screen.queryByTestId("parse-error")).toBeNull();
  });

  it("no row-count initially", () => {
    render(<CsvUploadDialog onValidate={vi.fn()} onImport={vi.fn()} />);
    expect(screen.queryByTestId("row-count")).toBeNull();
  });
});

// ── BulkOperationsCenter ───────────────────────────────────────────────────

describe("BulkOperationsCenter", () => {
  it("shows loading state", () => {
    setupAllMocks({ loading: true });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-loading")).not.toBeNull();
  });

  it("loading text is descriptive", () => {
    setupAllMocks({ loading: true });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-loading").textContent?.length).toBeGreaterThan(0);
  });

  it("shows error state", () => {
    setupAllMocks({ error: true });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-error")).not.toBeNull();
  });

  it("error message is descriptive", () => {
    setupAllMocks({ error: true });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-error").textContent?.length).toBeGreaterThan(0);
  });

  it("renders main center when loaded", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-operations-center")).not.toBeNull();
  });

  it("does not show loading when loaded", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByTestId("bulk-loading")).toBeNull();
  });

  it("does not show error when loaded", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByTestId("bulk-error")).toBeNull();
  });

  it("shows Upload CSV section heading", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByRole("heading", { name: /^Upload CSV$/i })).not.toBeNull();
  });

  it("shows History section heading", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByRole("heading", { name: /^History$/i })).not.toBeNull();
  });

  it("renders csv-upload-dialog", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("csv-upload-dialog")).not.toBeNull();
  });

  it("renders bulk-operation-history", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("bulk-operation-history")).not.toBeNull();
  });

  it("shows one history row from data", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("history-row-op-111")).not.toBeNull();
  });

  it("no validation-results-table initially", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByTestId("validation-results-table")).toBeNull();
  });

  it("no import-summary-card initially", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByTestId("import-summary-card")).toBeNull();
  });

  it("no Validation Results heading initially", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByRole("heading", { name: /^Validation Results$/i })).toBeNull();
  });

  it("no Operation Summary heading initially", () => {
    setupAllMocks();
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.queryByRole("heading", { name: /^Operation Summary$/i })).toBeNull();
  });

  it("shows empty history message when no operations", () => {
    mockUseBulkOperationList.mockReturnValue({
      isLoading: false, isError: false, data: makeList([]),
    });
    mockUseValidateCsv.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null });
    mockUseImportCsv.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null });
    mockUseBulkArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    mockUseBulkAssign.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    mockUseBulkStatusUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("no-history")).not.toBeNull();
  });

  it("multiple history rows shown when multiple operations", () => {
    mockUseBulkOperationList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeList([makeOp({ id: "op-A" }), makeOp({ id: "op-B" })]),
    });
    mockUseValidateCsv.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null });
    mockUseImportCsv.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false, error: null });
    mockUseBulkArchive.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    mockUseBulkAssign.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    mockUseBulkStatusUpdate.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, isError: false });
    render(<BulkOperationsCenter workspaceId={WS_ID} requestedBy={USER_ID} />);
    expect(screen.getByTestId("history-row-op-A")).not.toBeNull();
    expect(screen.getByTestId("history-row-op-B")).not.toBeNull();
  });
});
