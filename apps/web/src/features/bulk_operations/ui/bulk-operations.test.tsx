/**
 * Frontend unit tests — Sprint 59: Bulk Operations Center (part 1).
 * Covers: types/constants, bulkOperationKeys, BulkStatusBadge,
 * ImportSummaryCard, ValidationResultsTable, BulkOperationHistory.
 * NO jest-dom matchers.
 */

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  ENTITY_TYPE_LABELS,
  OPERATION_TYPE_LABELS,
  OPERATION_STATUS_LABELS,
  SUPPORTED_ENTITY_TYPES,
} from "@/features/bulk_operations/types";
import type {
  BulkOperationOut,
  CsvValidationOut,
  OperationStatus,
} from "@/features/bulk_operations/types";
import { BulkStatusBadge } from "@/features/bulk_operations/ui/BulkStatusBadge";
import { ImportSummaryCard } from "@/features/bulk_operations/ui/ImportSummaryCard";
import { ValidationResultsTable } from "@/features/bulk_operations/ui/ValidationResultsTable";
import { BulkOperationHistory } from "@/features/bulk_operations/ui/BulkOperationHistory";
import { bulkOperationKeys } from "@/features/bulk_operations/api/use-bulk-operations";

const NOW = "2026-07-09T10:00:00Z";

function makeOp(overrides: Partial<BulkOperationOut> = {}): BulkOperationOut {
  return {
    id: "op-111",
    workspace_id: "ws-222",
    operation_type: "csv_import",
    entity_type: "customers",
    status: "completed",
    requested_by: "user-333",
    total_records: 10,
    processed_records: 10,
    successful_records: 9,
    failed_records: 1,
    started_at: NOW,
    completed_at: NOW,
    error_summary: null,
    created_at: NOW,
    ...overrides,
  };
}

function makeValidation(overrides: Partial<CsvValidationOut> = {}): CsvValidationOut {
  return {
    entity_type: "customers",
    total_rows: 3,
    valid_rows: 2,
    invalid_rows: 1,
    dry_run: false,
    results: [
      { row: 1, valid: true, data: { company_name: "A" }, errors: [] },
      { row: 2, valid: true, data: { company_name: "B" }, errors: [] },
      {
        row: 3,
        valid: false,
        data: {},
        errors: [{ row: 3, field: "display_name", message: "display_name is required" }],
      },
    ],
    ...overrides,
  };
}

// ── ENTITY_TYPE_LABELS ─────────────────────────────────────────────────────

describe("ENTITY_TYPE_LABELS", () => {
  it("customers label is readable", () => {
    expect(ENTITY_TYPE_LABELS.customers).toBe("Customers");
  });
  it("training_engagements label is readable", () => {
    expect(ENTITY_TYPE_LABELS.training_engagements).toBe("Training Engagements");
  });
  it("business_tasks label is readable", () => {
    expect(ENTITY_TYPE_LABELS.business_tasks).toBe("Business Tasks");
  });
  it("workflow_templates label is readable", () => {
    expect(ENTITY_TYPE_LABELS.workflow_templates).toBe("Workflow Templates");
  });
});

// ── OPERATION_TYPE_LABELS ──────────────────────────────────────────────────

describe("OPERATION_TYPE_LABELS", () => {
  it("csv_import", () => { expect(OPERATION_TYPE_LABELS.csv_import).toBe("CSV Import"); });
  it("csv_validate", () => { expect(OPERATION_TYPE_LABELS.csv_validate).toBe("CSV Validation"); });
  it("bulk_archive", () => { expect(OPERATION_TYPE_LABELS.bulk_archive).toBe("Bulk Archive"); });
  it("bulk_status_update", () => { expect(OPERATION_TYPE_LABELS.bulk_status_update).toBe("Bulk Status Update"); });
  it("bulk_assignment", () => { expect(OPERATION_TYPE_LABELS.bulk_assignment).toBe("Bulk Assignment"); });
  it("dry_run", () => { expect(OPERATION_TYPE_LABELS.dry_run).toBe("Dry Run"); });
});

// ── OPERATION_STATUS_LABELS ────────────────────────────────────────────────

describe("OPERATION_STATUS_LABELS", () => {
  const statuses: OperationStatus[] = ["pending", "running", "completed", "failed", "cancelled"];
  statuses.forEach((s) => {
    it(`${s} has a label`, () => {
      expect(OPERATION_STATUS_LABELS[s].length).toBeGreaterThan(0);
    });
  });
});

// ── SUPPORTED_ENTITY_TYPES ─────────────────────────────────────────────────

describe("SUPPORTED_ENTITY_TYPES", () => {
  it("contains 4 types", () => { expect(SUPPORTED_ENTITY_TYPES).toHaveLength(4); });
  it("contains customers", () => { expect(SUPPORTED_ENTITY_TYPES).toContain("customers"); });
  it("contains training_engagements", () => { expect(SUPPORTED_ENTITY_TYPES).toContain("training_engagements"); });
  it("contains business_tasks", () => { expect(SUPPORTED_ENTITY_TYPES).toContain("business_tasks"); });
  it("contains workflow_templates", () => { expect(SUPPORTED_ENTITY_TYPES).toContain("workflow_templates"); });
});

// ── bulkOperationKeys ──────────────────────────────────────────────────────

describe("bulkOperationKeys", () => {
  it("all is stable", () => {
    expect(bulkOperationKeys.all).toEqual(["bulk-operations"]);
  });
  it("list includes workspace id", () => {
    expect(bulkOperationKeys.list("ws-1")).toContain("ws-1");
  });
  it("detail includes operation id", () => {
    expect(bulkOperationKeys.detail("op-1")).toContain("op-1");
  });
  it("list with filters is distinct from without", () => {
    const a = JSON.stringify(bulkOperationKeys.list("ws-1"));
    const b = JSON.stringify(bulkOperationKeys.list("ws-1", "customers"));
    expect(a).not.toBe(b);
  });
  it("list with status filter is distinct", () => {
    const a = JSON.stringify(bulkOperationKeys.list("ws-1", undefined, "completed"));
    const b = JSON.stringify(bulkOperationKeys.list("ws-1", undefined, "failed"));
    expect(a).not.toBe(b);
  });
});

// ── BulkStatusBadge ────────────────────────────────────────────────────────

describe("BulkStatusBadge", () => {
  const statuses: OperationStatus[] = ["pending", "running", "completed", "failed", "cancelled"];

  statuses.forEach((s) => {
    it(`renders badge for ${s}`, () => {
      render(<BulkStatusBadge status={s} />);
      expect(screen.getByTestId(`status-badge-${s}`)).not.toBeNull();
    });

    it(`${s} shows label text`, () => {
      render(<BulkStatusBadge status={s} />);
      const badge = screen.getByTestId(`status-badge-${s}`);
      expect(badge.textContent).toBe(OPERATION_STATUS_LABELS[s]);
    });
  });
});

// ── ImportSummaryCard ──────────────────────────────────────────────────────

describe("ImportSummaryCard", () => {
  it("renders the card", () => {
    render(<ImportSummaryCard operation={makeOp()} />);
    expect(screen.getByTestId("import-summary-card")).not.toBeNull();
  });

  it("shows operation type label", () => {
    render(<ImportSummaryCard operation={makeOp()} />);
    expect(screen.getByTestId("summary-operation-type").textContent).toBe("CSV Import");
  });

  it("shows entity type label", () => {
    render(<ImportSummaryCard operation={makeOp()} />);
    expect(screen.getByTestId("summary-entity-type").textContent).toBe("Customers");
  });

  it("shows total records", () => {
    render(<ImportSummaryCard operation={makeOp({ total_records: 42 })} />);
    expect(screen.getByTestId("summary-total").textContent).toContain("42");
  });

  it("shows processed records", () => {
    render(<ImportSummaryCard operation={makeOp({ processed_records: 8 })} />);
    expect(screen.getByTestId("summary-processed").textContent).toContain("8");
  });

  it("shows successful records", () => {
    render(<ImportSummaryCard operation={makeOp({ successful_records: 7 })} />);
    expect(screen.getByTestId("summary-successful").textContent).toContain("7");
  });

  it("shows failed records", () => {
    render(<ImportSummaryCard operation={makeOp({ failed_records: 3 })} />);
    expect(screen.getByTestId("summary-failed").textContent).toContain("3");
  });

  it("shows success rate", () => {
    render(<ImportSummaryCard operation={makeOp({ total_records: 10, successful_records: 9 })} />);
    expect(screen.getByTestId("summary-success-rate").textContent).toContain("90%");
  });

  it("100% success rate shows 100%", () => {
    render(<ImportSummaryCard operation={makeOp({ total_records: 5, successful_records: 5, failed_records: 0 })} />);
    expect(screen.getByTestId("summary-success-rate").textContent).toContain("100%");
  });

  it("0% success rate when all failed", () => {
    render(<ImportSummaryCard operation={makeOp({ total_records: 5, successful_records: 0, failed_records: 5 })} />);
    expect(screen.getByTestId("summary-success-rate").textContent).toContain("0%");
  });

  it("shows error section when error_summary is set", () => {
    render(<ImportSummaryCard operation={makeOp({ error_summary: "Row 1: field x is required" })} />);
    expect(screen.getByTestId("summary-error-section")).not.toBeNull();
  });

  it("shows error text content", () => {
    render(<ImportSummaryCard operation={makeOp({ error_summary: "Row 3: missing field" })} />);
    expect(screen.getByTestId("summary-error-text").textContent).toContain("Row 3");
  });

  it("no error section when error_summary is null", () => {
    render(<ImportSummaryCard operation={makeOp({ error_summary: null })} />);
    expect(screen.queryByTestId("summary-error-section")).toBeNull();
  });

  it("shows status badge", () => {
    render(<ImportSummaryCard operation={makeOp({ status: "failed" })} />);
    expect(screen.getByTestId("status-badge-failed")).not.toBeNull();
  });

  it("shows progress bar", () => {
    render(<ImportSummaryCard operation={makeOp()} />);
    expect(screen.getByTestId("summary-progress-bar")).not.toBeNull();
  });

  it("progress bar has correct width style", () => {
    render(<ImportSummaryCard operation={makeOp({ total_records: 10, successful_records: 6 })} />);
    const bar = screen.getByTestId("summary-progress-bar") as HTMLElement;
    expect(bar.style.width).toBe("60%");
  });
});

// ── ValidationResultsTable ─────────────────────────────────────────────────

describe("ValidationResultsTable", () => {
  it("renders the container", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("validation-results-table")).not.toBeNull();
  });

  it("shows total rows", () => {
    render(<ValidationResultsTable validation={makeValidation({ total_rows: 5 })} />);
    expect(screen.getByTestId("validation-total").textContent).toContain("5");
  });

  it("shows valid rows count", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("validation-valid-count").textContent).toContain("2");
  });

  it("shows invalid rows count", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("validation-invalid-count").textContent).toContain("1");
  });

  it("shows dry run badge when dry_run is true", () => {
    render(<ValidationResultsTable validation={makeValidation({ dry_run: true })} />);
    expect(screen.getByTestId("dry-run-badge")).not.toBeNull();
  });

  it("no dry run badge when dry_run is false", () => {
    render(<ValidationResultsTable validation={makeValidation({ dry_run: false })} />);
    expect(screen.queryByTestId("dry-run-badge")).toBeNull();
  });

  it("shows all-valid message when no invalid rows", () => {
    const val = makeValidation({ invalid_rows: 0, results: [
      { row: 1, valid: true, data: {}, errors: [] },
    ]});
    render(<ValidationResultsTable validation={val} />);
    expect(screen.getByTestId("all-valid-message")).not.toBeNull();
  });

  it("no all-valid message when there are invalid rows", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.queryByTestId("all-valid-message")).toBeNull();
  });

  it("shows error table for invalid rows", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("error-table")).not.toBeNull();
  });

  it("shows error row for invalid result", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("error-row-3")).not.toBeNull();
  });

  it("no error table when all valid", () => {
    const val = makeValidation({ invalid_rows: 0, results: [
      { row: 1, valid: true, data: {}, errors: [] },
    ]});
    render(<ValidationResultsTable validation={val} />);
    expect(screen.queryByTestId("error-table")).toBeNull();
  });

  it("shows invalid icon for invalid row", () => {
    render(<ValidationResultsTable validation={makeValidation()} />);
    expect(screen.getByTestId("row-invalid-icon")).not.toBeNull();
  });
});

// ── BulkOperationHistory ───────────────────────────────────────────────────

describe("BulkOperationHistory", () => {
  it("renders the container", () => {
    render(<BulkOperationHistory operations={[]} total={0} />);
    expect(screen.getByTestId("bulk-operation-history")).not.toBeNull();
  });

  it("shows no-history message when empty", () => {
    render(<BulkOperationHistory operations={[]} total={0} />);
    expect(screen.getByTestId("no-history")).not.toBeNull();
  });

  it("no-history message is descriptive", () => {
    render(<BulkOperationHistory operations={[]} total={0} />);
    expect(screen.getByTestId("no-history").textContent?.length).toBeGreaterThan(0);
  });

  it("shows history count badge when operations exist", () => {
    render(<BulkOperationHistory operations={[makeOp()]} total={1} />);
    expect(screen.getByTestId("history-count")).not.toBeNull();
  });

  it("count badge shows correct count", () => {
    render(<BulkOperationHistory operations={[makeOp(), makeOp({ id: "op-999" })]} total={2} />);
    expect(screen.getByTestId("history-count").textContent).toContain("2");
  });

  it("singular 'operation' when total = 1", () => {
    render(<BulkOperationHistory operations={[makeOp()]} total={1} />);
    expect(screen.getByTestId("history-count").textContent).toContain("1 operation");
  });

  it("plural 'operations' when total > 1", () => {
    render(<BulkOperationHistory operations={[makeOp(), makeOp({ id: "op-2" })]} total={2} />);
    expect(screen.getByTestId("history-count").textContent).toContain("operations");
  });

  it("renders a row per operation", () => {
    const ops = [makeOp({ id: "op-a" }), makeOp({ id: "op-b" })];
    render(<BulkOperationHistory operations={ops} total={2} />);
    expect(screen.getByTestId("history-row-op-a")).not.toBeNull();
    expect(screen.getByTestId("history-row-op-b")).not.toBeNull();
  });

  it("shows operation type label for row", () => {
    render(<BulkOperationHistory operations={[makeOp()]} total={1} />);
    expect(screen.getByTestId("history-op-type-op-111").textContent).toBe("CSV Import");
  });

  it("shows entity type label for row", () => {
    render(<BulkOperationHistory operations={[makeOp()]} total={1} />);
    expect(screen.getByTestId("history-entity-type-op-111").textContent).toBe("Customers");
  });

  it("shows records fraction", () => {
    render(<BulkOperationHistory operations={[makeOp()]} total={1} />);
    expect(screen.getByTestId("history-records-op-111").textContent).toContain("9/10");
  });

  it("shows failed count when > 0", () => {
    render(<BulkOperationHistory operations={[makeOp({ failed_records: 3 })]} total={1} />);
    expect(screen.getByTestId("history-failed-op-111")).not.toBeNull();
  });

  it("no failed element when failed_records = 0", () => {
    render(<BulkOperationHistory operations={[makeOp({ failed_records: 0 })]} total={1} />);
    expect(screen.queryByTestId("history-failed-op-111")).toBeNull();
  });

  it("shows status badge", () => {
    render(<BulkOperationHistory operations={[makeOp({ status: "running" })]} total={1} />);
    expect(screen.getByTestId("status-badge-running")).not.toBeNull();
  });
});
