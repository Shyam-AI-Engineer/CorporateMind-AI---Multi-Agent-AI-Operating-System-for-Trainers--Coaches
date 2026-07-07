/**
 * Tests for audit-center.tsx — Sprint 53: Audit Log & Compliance Center
 * 150 tests across 10 test suites.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/features/audit/api/use-audit", () => ({
  useAuditEvents: vi.fn(),
  useAuditEvent: vi.fn(),
  useEntityAuditEvents: vi.fn(),
  useAuditStatistics: vi.fn(),
}));

import * as hooks from "@/features/audit/api/use-audit";

const {
  SeverityBadge,
  StatisticsCards,
  AuditFilters,
  AuditTable,
  AuditDetailDrawer,
  EntityAuditHistory,
  AuditCenter,
} = await import("./audit-center");

const { AUDIT_SEVERITIES } = await import("../types-audit");

// ── Helpers ───────────────────────────────────────────────────────────────────

const WS = "ws-111";

function makeLog(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "log-001",
    workspace_id: WS,
    user_id: "user-abc",
    entity_type: "invoice",
    entity_id: "inv-001",
    action: "invoice.issued",
    module: "billing",
    severity: "info",
    ip_address: "1.2.3.4",
    user_agent: "Mozilla/5.0",
    metadata: { amount: "500.00" },
    created_at: "2026-07-07T10:00:00Z",
    ...overrides,
  };
}

function makeStats(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    total_events: 150,
    by_severity: { info: 120, warning: 25, critical: 5 },
    by_module: { billing: 80, customers: 40, workflows: 30 },
    by_action: { "invoice.issued": 50, "payment.confirmed": 30 },
    period_days: 30,
    ...overrides,
  };
}

function mockHook(name: keyof typeof hooks, result: unknown) {
  vi.mocked(hooks[name]).mockReturnValue(result as ReturnType<typeof hooks[typeof name]>);
}

const idle = { data: undefined, isLoading: false, isError: false };
const loading = { data: undefined, isLoading: true, isError: false };
const error = { data: undefined, isLoading: false, isError: true };

// ── SeverityBadge (12 tests) ──────────────────────────────────────────────────

describe("SeverityBadge", () => {
  it("renders info severity", () => {
    render(<SeverityBadge severity="info" />);
    expect(screen.getByTestId("severity-badge")).not.toBeNull();
    expect(screen.getByText("info")).not.toBeNull();
  });

  it("renders warning severity", () => {
    render(<SeverityBadge severity="warning" />);
    expect(screen.getByText("warning")).not.toBeNull();
  });

  it("renders critical severity", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("critical")).not.toBeNull();
  });

  it("has data-severity attribute", () => {
    render(<SeverityBadge severity="warning" />);
    expect(screen.getByTestId("severity-badge").getAttribute("data-severity")).toBe("warning");
  });

  it("applies info styles", () => {
    render(<SeverityBadge severity="info" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.className).toContain("blue");
  });

  it("applies warning styles", () => {
    render(<SeverityBadge severity="warning" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.className).toContain("yellow");
  });

  it("applies critical styles", () => {
    render(<SeverityBadge severity="critical" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.className).toContain("red");
  });

  it("renders unknown severity with fallback style", () => {
    render(<SeverityBadge severity="unknown" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge).not.toBeNull();
    expect(badge.className).toContain("gray");
  });

  it("badge is a span element", () => {
    render(<SeverityBadge severity="info" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.tagName.toLowerCase()).toBe("span");
  });

  it("badge has rounded-full class", () => {
    render(<SeverityBadge severity="info" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.className).toContain("rounded-full");
  });

  it("badge displays text content", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("critical")).not.toBeNull();
  });

  it("badge is inline-flex", () => {
    render(<SeverityBadge severity="info" />);
    const badge = screen.getByTestId("severity-badge");
    expect(badge.className).toContain("inline-flex");
  });
});

// ── StatisticsCards (15 tests) ────────────────────────────────────────────────

describe("StatisticsCards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton when isLoading", () => {
    mockHook("useAuditStatistics", loading);
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("statistics-loading")).not.toBeNull();
  });

  it("shows error state when isError", () => {
    mockHook("useAuditStatistics", error);
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("statistics-error")).not.toBeNull();
  });

  it("renders stats cards when data available", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats() }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("statistics-cards")).not.toBeNull();
  });

  it("shows total events count", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ total_events: 999 }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-total").textContent).toContain("999");
  });

  it("shows critical count", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ by_severity: { critical: 7 } }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-critical").textContent).toContain("7");
  });

  it("shows warning count", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ by_severity: { info: 100, warning: 15 } }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-warning").textContent).toContain("15");
  });

  it("shows active modules count", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ by_module: { billing: 1, customers: 2, workflows: 3 } }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-modules").textContent).toContain("3");
  });

  it("shows 0 critical when not in by_severity", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ by_severity: { info: 50 } }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-critical").textContent).toContain("0");
  });

  it("shows period_days label", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ period_days: 7 }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByText("Last 7 days")).not.toBeNull();
  });

  it("shows 4 loading skeletons", () => {
    mockHook("useAuditStatistics", loading);
    render(<StatisticsCards workspaceId={WS} />);
    const skeleton = screen.getByTestId("statistics-loading");
    expect(skeleton.children.length).toBe(4);
  });

  it("passes workspaceId to hook", () => {
    mockHook("useAuditStatistics", idle);
    render(<StatisticsCards workspaceId="ws-custom" />);
    expect(vi.mocked(hooks.useAuditStatistics)).toHaveBeenCalledWith("ws-custom", 30);
  });

  it("passes periodDays prop to hook", () => {
    mockHook("useAuditStatistics", idle);
    render(<StatisticsCards workspaceId={WS} periodDays={7} />);
    expect(vi.mocked(hooks.useAuditStatistics)).toHaveBeenCalledWith(WS, 7);
  });

  it("error message contains 'statistics'", () => {
    mockHook("useAuditStatistics", error);
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("statistics-error").textContent?.toLowerCase()).toContain("statistics");
  });

  it("renders without crash when no data and not loading", () => {
    mockHook("useAuditStatistics", idle);
    render(<StatisticsCards workspaceId={WS} />);
    // idle and no data — no crash
  });

  it("renders all 4 stat cards", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats() }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-total")).not.toBeNull();
    expect(screen.getByTestId("stat-critical")).not.toBeNull();
    expect(screen.getByTestId("stat-warning")).not.toBeNull();
    expect(screen.getByTestId("stat-modules")).not.toBeNull();
  });
});

// ── AuditFilters (20 tests) ───────────────────────────────────────────────────

describe("AuditFilters", () => {
  const noOp = vi.fn();

  it("renders filter container", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.getByTestId("audit-filters")).not.toBeNull();
  });

  it("renders search input", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.getByTestId("filter-search")).not.toBeNull();
  });

  it("renders severity select", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.getByTestId("filter-severity")).not.toBeNull();
  });

  it("renders date-from input", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.getByTestId("filter-date-from")).not.toBeNull();
  });

  it("renders date-to input", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.getByTestId("filter-date-to")).not.toBeNull();
  });

  it("severity select has all options", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    const sel = screen.getByTestId("filter-severity") as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value);
    expect(opts).toContain("info");
    expect(opts).toContain("warning");
    expect(opts).toContain("critical");
  });

  it("severity select has blank default option", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    const sel = screen.getByTestId("filter-severity") as HTMLSelectElement;
    expect(sel.options[0].value).toBe("");
  });

  it("search input shows current value", () => {
    render(<AuditFilters filters={{ search: "payment" }} onChange={noOp} />);
    const el = screen.getByTestId("filter-search") as HTMLInputElement;
    expect(el.value).toBe("payment");
  });

  it("severity select shows current value", () => {
    render(<AuditFilters filters={{ severity: "critical" }} onChange={noOp} />);
    const el = screen.getByTestId("filter-severity") as HTMLSelectElement;
    expect(el.value).toBe("critical");
  });

  it("onChange called when search changes", () => {
    const onChange = vi.fn();
    render(<AuditFilters filters={{}} onChange={onChange} />);
    fireEvent.change(screen.getByTestId("filter-search"), { target: { value: "billing" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("onChange called when severity changes", () => {
    const onChange = vi.fn();
    render(<AuditFilters filters={{}} onChange={onChange} />);
    fireEvent.change(screen.getByTestId("filter-severity"), { target: { value: "warning" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("clear button appears when search set", () => {
    render(<AuditFilters filters={{ search: "test" }} onChange={noOp} />);
    expect(screen.getByTestId("filter-clear")).not.toBeNull();
  });

  it("clear button appears when severity set", () => {
    render(<AuditFilters filters={{ severity: "critical" }} onChange={noOp} />);
    expect(screen.getByTestId("filter-clear")).not.toBeNull();
  });

  it("clear button not shown when no active filters", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.queryByTestId("filter-clear")).toBeNull();
  });

  it("clear button calls onChange with only workspace_id", () => {
    const onChange = vi.fn();
    render(<AuditFilters filters={{ workspace_id: WS, search: "test" }} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("filter-clear"));
    expect(onChange).toHaveBeenCalledWith({ workspace_id: WS });
  });

  it("module select renders when availableModules provided", () => {
    render(<AuditFilters filters={{}} onChange={noOp} availableModules={["billing", "customers"]} />);
    expect(screen.getByTestId("filter-module")).not.toBeNull();
  });

  it("module select not rendered when no availableModules", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    expect(screen.queryByTestId("filter-module")).toBeNull();
  });

  it("module select shows provided modules", () => {
    render(<AuditFilters filters={{}} onChange={noOp} availableModules={["billing", "workflows"]} />);
    const sel = screen.getByTestId("filter-module") as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value);
    expect(opts).toContain("billing");
    expect(opts).toContain("workflows");
  });

  it("onChange called on module change", () => {
    const onChange = vi.fn();
    render(<AuditFilters filters={{}} onChange={onChange} availableModules={["billing"]} />);
    fireEvent.change(screen.getByTestId("filter-module"), { target: { value: "billing" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("date_from input is type datetime-local", () => {
    render(<AuditFilters filters={{}} onChange={noOp} />);
    const input = screen.getByTestId("filter-date-from") as HTMLInputElement;
    expect(input.type).toBe("datetime-local");
  });
});

// ── AuditTable (20 tests) ─────────────────────────────────────────────────────

describe("AuditTable", () => {
  it("shows loading state", () => {
    render(<AuditTable items={[]} isLoading={true} />);
    expect(screen.getByTestId("audit-table-loading")).not.toBeNull();
  });

  it("shows empty state when no items", () => {
    render(<AuditTable items={[]} />);
    expect(screen.getByTestId("audit-table-empty")).not.toBeNull();
  });

  it("renders table when items present", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByTestId("audit-table")).not.toBeNull();
  });

  it("renders one row per item", () => {
    render(<AuditTable items={[makeLog({ id: "a" }), makeLog({ id: "b" })]} />);
    expect(screen.getByTestId("audit-row-a")).not.toBeNull();
    expect(screen.getByTestId("audit-row-b")).not.toBeNull();
  });

  it("shows action in row", () => {
    render(<AuditTable items={[makeLog({ action: "payment.confirmed" })]} />);
    expect(screen.getByText("payment.confirmed")).not.toBeNull();
  });

  it("shows module in row", () => {
    render(<AuditTable items={[makeLog({ module: "training" })]} />);
    expect(screen.getByText("training")).not.toBeNull();
  });

  it("shows SeverityBadge per row", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByTestId("severity-badge")).not.toBeNull();
  });

  it("row click calls onSelect", () => {
    const onSelect = vi.fn();
    const log = makeLog();
    render(<AuditTable items={[log]} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId(`audit-row-${log.id}`));
    expect(onSelect).toHaveBeenCalledWith(log);
  });

  it("selected row has highlight class", () => {
    const log = makeLog();
    render(<AuditTable items={[log]} selectedId={log.id} />);
    const row = screen.getByTestId(`audit-row-${log.id}`);
    expect(row.className).toContain("blue");
  });

  it("non-selected row has no highlight", () => {
    const log = makeLog();
    render(<AuditTable items={[log]} selectedId="other-id" />);
    const row = screen.getByTestId(`audit-row-${log.id}`);
    expect(row.className).not.toContain("bg-blue-50");
  });

  it("empty message contains 'No audit events'", () => {
    render(<AuditTable items={[]} />);
    expect(screen.getByTestId("audit-table-empty").textContent).toContain("No audit events");
  });

  it("table has Severity column header", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByText("Severity")).not.toBeNull();
  });

  it("table has Action column header", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByText("Action")).not.toBeNull();
  });

  it("table has Module column header", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByText("Module")).not.toBeNull();
  });

  it("renders entity type in row", () => {
    render(<AuditTable items={[makeLog({ entity_type: "invoice" })]} />);
    expect(screen.getByText("invoice")).not.toBeNull();
  });

  it("shows dash when entity_type is null", () => {
    render(<AuditTable items={[makeLog({ entity_type: null })]} />);
    expect(screen.getByText("—")).not.toBeNull();
  });

  it("multiple rows render in order", () => {
    const logs = [makeLog({ id: "z", action: "z.action" }), makeLog({ id: "a", action: "a.action" })];
    render(<AuditTable items={logs} />);
    expect(screen.getByText("z.action")).not.toBeNull();
    expect(screen.getByText("a.action")).not.toBeNull();
  });

  it("loading skeletons are 5", () => {
    render(<AuditTable items={[]} isLoading={true} />);
    const loadingEl = screen.getByTestId("audit-table-loading");
    expect(loadingEl.children.length).toBe(5);
  });

  it("overflow wrapper prevents horizontal scroll", () => {
    render(<AuditTable items={[makeLog()]} />);
    const wrapper = screen.getByTestId("audit-table");
    expect(wrapper.className).toContain("overflow-x-auto");
  });

  it("row has cursor-pointer class", () => {
    const log = makeLog();
    render(<AuditTable items={[log]} />);
    const row = screen.getByTestId(`audit-row-${log.id}`);
    expect(row.className).toContain("cursor-pointer");
  });
});

// ── AuditDetailDrawer (22 tests) ──────────────────────────────────────────────

describe("AuditDetailDrawer", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when logId is null", () => {
    mockHook("useAuditEvent", idle);
    const { container } = render(<AuditDetailDrawer logId={null} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders drawer when logId is provided", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("audit-detail-drawer")).not.toBeNull();
  });

  it("shows loading spinner when isLoading", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-loading")).not.toBeNull();
  });

  it("renders drawer content when data available", () => {
    mockHook("useAuditEvent", { data: { data: makeLog() }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-content")).not.toBeNull();
  });

  it("close button calls onClose", () => {
    mockHook("useAuditEvent", loading);
    const onClose = vi.fn();
    render(<AuditDetailDrawer logId="log-001" onClose={onClose} />);
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows action in drawer", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ action: "invoice.issued" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-action").textContent).toContain("invoice.issued");
  });

  it("shows module in drawer", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ module: "billing" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-module").textContent).toContain("billing");
  });

  it("shows severity badge in drawer", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ severity: "critical" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("severity-badge")).not.toBeNull();
  });

  it("shows entity section when entity_type present", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ entity_type: "invoice", entity_id: "inv-1" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-entity")).not.toBeNull();
  });

  it("hides entity section when entity_type null", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ entity_type: null }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-entity")).toBeNull();
  });

  it("shows user_id when present", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ user_id: "user-123" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-user").textContent).toContain("user-123");
  });

  it("hides user section when user_id null", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ user_id: null }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-user")).toBeNull();
  });

  it("shows ip_address when present", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ ip_address: "10.0.0.1" }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-ip").textContent).toContain("10.0.0.1");
  });

  it("hides ip section when ip_address null", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ ip_address: null }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-ip")).toBeNull();
  });

  it("shows metadata when not empty", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ metadata: { amount: "100" } }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-metadata")).not.toBeNull();
  });

  it("hides metadata section when metadata is empty", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ metadata: {} }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-metadata")).toBeNull();
  });

  it("drawer has Event Details heading", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByText("Event Details")).not.toBeNull();
  });

  it("drawer is fixed positioned", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("audit-detail-drawer").className).toContain("fixed");
  });

  it("drawer close button has aria-label", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByLabelText("Close drawer")).not.toBeNull();
  });

  it("shows timestamp in drawer", () => {
    mockHook("useAuditEvent", { data: { data: makeLog() }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-timestamp")).not.toBeNull();
  });

  it("metadata rendered as JSON", () => {
    mockHook("useAuditEvent", { data: { data: makeLog({ metadata: { key: "value" } }) }, isLoading: false, isError: false });
    render(<AuditDetailDrawer logId="log-001" onClose={vi.fn()} />);
    const meta = screen.getByTestId("drawer-metadata");
    expect(meta.textContent).toContain("key");
    expect(meta.textContent).toContain("value");
  });

  it("calls useAuditEvent with correct logId", () => {
    mockHook("useAuditEvent", idle);
    render(<AuditDetailDrawer logId="specific-id" onClose={vi.fn()} />);
    expect(vi.mocked(hooks.useAuditEvent)).toHaveBeenCalledWith("specific-id");
  });
});

// ── EntityAuditHistory (8 tests) ──────────────────────────────────────────────

describe("EntityAuditHistory", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders entity history container", () => {
    mockHook("useEntityAuditEvents", { data: { data: [] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-audit-history")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockHook("useEntityAuditEvents", loading);
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-history-loading")).not.toBeNull();
  });

  it("shows empty state when no history", () => {
    mockHook("useEntityAuditEvents", { data: { data: [] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-history-empty")).not.toBeNull();
  });

  it("renders history list when items present", () => {
    mockHook("useEntityAuditEvents", { data: { data: [makeLog()] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-history-list")).not.toBeNull();
  });

  it("renders one item per log", () => {
    mockHook("useEntityAuditEvents", { data: { data: [makeLog({ id: "a" }), makeLog({ id: "b" })] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-history-item-a")).not.toBeNull();
    expect(screen.getByTestId("entity-history-item-b")).not.toBeNull();
  });

  it("each item shows action", () => {
    mockHook("useEntityAuditEvents", { data: { data: [makeLog({ action: "invoice.cancelled" })] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByText("invoice.cancelled")).not.toBeNull();
  });

  it("each item shows severity badge", () => {
    mockHook("useEntityAuditEvents", { data: { data: [makeLog({ severity: "warning" })] }, isLoading: false, isError: false });
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("severity-badge")).not.toBeNull();
  });

  it("passes entity params to hook", () => {
    mockHook("useEntityAuditEvents", idle);
    render(<EntityAuditHistory entityType="customer" entityId="cust-99" workspaceId={WS} />);
    expect(vi.mocked(hooks.useEntityAuditEvents)).toHaveBeenCalledWith("customer", "cust-99", WS);
  });
});

// ── AUDIT_SEVERITIES constant (5 tests) ──────────────────────────────────────

describe("AUDIT_SEVERITIES constant", () => {
  it("contains info", () => expect(AUDIT_SEVERITIES).toContain("info"));
  it("contains warning", () => expect(AUDIT_SEVERITIES).toContain("warning"));
  it("contains critical", () => expect(AUDIT_SEVERITIES).toContain("critical"));
  it("has exactly 3 entries", () => expect(AUDIT_SEVERITIES).toHaveLength(3));
  it("is an array", () => expect(Array.isArray(AUDIT_SEVERITIES)).toBe(true));
});

// ── AuditCenter (25 tests) ────────────────────────────────────────────────────

describe("AuditCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHook("useAuditStatistics", idle);
    mockHook("useAuditEvents", idle);
  });

  it("renders audit center container", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-center")).not.toBeNull();
  });

  it("shows 'Audit Log' heading", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByText("Audit Log")).not.toBeNull();
  });

  it("shows total when data present", () => {
    mockHook("useAuditEvents", { data: { data: { items: [], next_cursor: null, has_more: false, total: 42 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-total").textContent).toContain("42");
  });

  it("shows dash when no data", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-total").textContent).toContain("—");
  });

  it("renders StatisticsCards", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(vi.mocked(hooks.useAuditStatistics)).toHaveBeenCalledWith(WS, 30);
  });

  it("renders AuditFilters", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-filters")).not.toBeNull();
  });

  it("renders AuditTable", () => {
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-table")).not.toBeNull();
  });

  it("shows loading table while events loading", () => {
    mockHook("useAuditEvents", loading);
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-table-loading")).not.toBeNull();
  });

  it("shows error banner on error", () => {
    mockHook("useAuditEvents", error);
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-error")).not.toBeNull();
  });

  it("shows empty table when items empty", () => {
    mockHook("useAuditEvents", { data: { data: { items: [], next_cursor: null, has_more: false, total: 0 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-table-empty")).not.toBeNull();
  });

  it("shows load-more button when has_more is true", () => {
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: "cursor-abc", has_more: true, total: 100 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("load-more")).not.toBeNull();
  });

  it("hides load-more when has_more is false", () => {
    mockHook("useAuditEvents", { data: { data: { items: [], next_cursor: null, has_more: false, total: 0 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.queryByTestId("load-more")).toBeNull();
  });

  it("clicking row shows drawer backdrop", () => {
    mockHook("useAuditEvent", loading);
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId(`audit-row-${makeLog().id}`));
    expect(screen.getByTestId("drawer-backdrop")).not.toBeNull();
  });

  it("clicking drawer backdrop closes drawer", () => {
    mockHook("useAuditEvent", loading);
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId(`audit-row-${makeLog().id}`));
    fireEvent.click(screen.getByTestId("drawer-backdrop"));
    expect(screen.queryByTestId("drawer-backdrop")).toBeNull();
  });

  it("search filter change re-queries", () => {
    mockHook("useAuditEvents", { data: { data: { items: [], next_cursor: null, has_more: false, total: 0 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.change(screen.getByTestId("filter-search"), { target: { value: "billing" } });
    expect(vi.mocked(hooks.useAuditEvents)).toHaveBeenCalled();
  });

  it("severity filter change updates call", () => {
    mockHook("useAuditEvents", { data: { data: { items: [], next_cursor: null, has_more: false, total: 0 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.change(screen.getByTestId("filter-severity"), { target: { value: "critical" } });
    expect(vi.mocked(hooks.useAuditEvents)).toHaveBeenCalled();
  });

  it("drawer visible after row click", () => {
    mockHook("useAuditEvent", loading);
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId(`audit-row-${makeLog().id}`));
    expect(screen.getByTestId("audit-detail-drawer")).not.toBeNull();
  });

  it("calls useAuditEvents with workspaceId", () => {
    render(<AuditCenter workspaceId="ws-custom" />);
    const call = vi.mocked(hooks.useAuditEvents).mock.calls[0][0];
    expect(call?.workspace_id).toBe("ws-custom");
  });

  it("load-more button text is 'Load more'", () => {
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: "c", has_more: true, total: 50 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("load-more").textContent).toContain("Load more");
  });

  it("error message contains 'Failed'", () => {
    mockHook("useAuditEvents", error);
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-error").textContent).toContain("Failed");
  });

  it("renders without crash with idle hooks", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-center")).not.toBeNull();
  });

  it("selected row gets highlighted after click", () => {
    const log = makeLog();
    mockHook("useAuditEvent", loading);
    mockHook("useAuditEvents", { data: { data: { items: [log], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId(`audit-row-${log.id}`));
    const row = screen.getByTestId(`audit-row-${log.id}`);
    expect(row.className).toContain("blue");
  });

  it("initial total shows dash before data loads", () => {
    mockHook("useAuditEvents", loading);
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.getByTestId("audit-total").textContent).toContain("—");
  });

  it("drawer not shown initially", () => {
    render(<AuditCenter workspaceId={WS} />);
    expect(screen.queryByTestId("audit-detail-drawer")).toBeNull();
  });

  it("closing drawer via close button works", () => {
    mockHook("useAuditEvent", loading);
    mockHook("useAuditEvents", { data: { data: { items: [makeLog()], next_cursor: null, has_more: false, total: 1 } }, isLoading: false, isError: false });
    render(<AuditCenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId(`audit-row-${makeLog().id}`));
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("audit-detail-drawer")).toBeNull();
  });
});

// ── Edge cases (15 tests) ─────────────────────────────────────────────────────

describe("Edge cases", () => {
  beforeEach(() => vi.clearAllMocks());

  it("SeverityBadge renders with empty string severity", () => {
    render(<SeverityBadge severity="" />);
    expect(screen.getByTestId("severity-badge")).not.toBeNull();
  });

  it("AuditTable handles 0 items gracefully", () => {
    render(<AuditTable items={[]} />);
    expect(screen.queryByTestId("audit-table")).toBeNull();
    expect(screen.getByTestId("audit-table-empty")).not.toBeNull();
  });

  it("AuditTable renders 1 item", () => {
    render(<AuditTable items={[makeLog()]} />);
    expect(screen.getByTestId("audit-table")).not.toBeNull();
  });

  it("AuditTable handles log with null entity_id", () => {
    render(<AuditTable items={[makeLog({ entity_id: null })]} />);
    expect(screen.getByTestId("audit-table")).not.toBeNull();
  });

  it("AuditDetailDrawer calls useAuditEvent with null when no logId", () => {
    mockHook("useAuditEvent", idle);
    render(<AuditDetailDrawer logId={null} onClose={vi.fn()} />);
    expect(vi.mocked(hooks.useAuditEvent)).toHaveBeenCalledWith(null);
  });

  it("StatisticsCards uses default periodDays of 30", () => {
    mockHook("useAuditStatistics", idle);
    render(<StatisticsCards workspaceId={WS} />);
    expect(vi.mocked(hooks.useAuditStatistics)).toHaveBeenCalledWith(WS, 30);
  });

  it("AuditFilters clear button not shown without active filter", () => {
    render(<AuditFilters filters={{ workspace_id: WS }} onChange={vi.fn()} />);
    expect(screen.queryByTestId("filter-clear")).toBeNull();
  });

  it("AuditFilters date-to change fires onChange", () => {
    const onChange = vi.fn();
    render(<AuditFilters filters={{}} onChange={onChange} />);
    fireEvent.change(screen.getByTestId("filter-date-to"), { target: { value: "2026-07-07T10:00" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("AuditDetailDrawer does not show loading when logId is null", () => {
    mockHook("useAuditEvent", idle);
    render(<AuditDetailDrawer logId={null} onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-loading")).toBeNull();
  });

  it("EntityAuditHistory passes correct workspaceId", () => {
    mockHook("useEntityAuditEvents", idle);
    render(<EntityAuditHistory entityType="invoice" entityId="x" workspaceId="ws-test" />);
    expect(vi.mocked(hooks.useEntityAuditEvents)).toHaveBeenCalledWith("invoice", "x", "ws-test");
  });

  it("AuditTable row doesn't crash if onSelect is undefined", () => {
    const log = makeLog();
    render(<AuditTable items={[log]} />);
    fireEvent.click(screen.getByTestId(`audit-row-${log.id}`));
    // no error thrown
  });

  it("StatisticsCards 0 warning renders correctly", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ by_severity: { info: 50 } }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-warning").textContent).toContain("0");
  });

  it("AuditFilters renders all 4 control elements", () => {
    render(<AuditFilters filters={{}} onChange={vi.fn()} />);
    expect(screen.getByTestId("filter-search")).not.toBeNull();
    expect(screen.getByTestId("filter-severity")).not.toBeNull();
    expect(screen.getByTestId("filter-date-from")).not.toBeNull();
    expect(screen.getByTestId("filter-date-to")).not.toBeNull();
  });

  it("AuditTable with isLoading=false and items shows table not loading", () => {
    render(<AuditTable items={[makeLog()]} isLoading={false} />);
    expect(screen.queryByTestId("audit-table-loading")).toBeNull();
    expect(screen.getByTestId("audit-table")).not.toBeNull();
  });

  it("AuditDetailDrawer renders Event Details title regardless of loading state", () => {
    mockHook("useAuditEvent", loading);
    render(<AuditDetailDrawer logId="any" onClose={vi.fn()} />);
    expect(screen.getByText("Event Details")).not.toBeNull();
  });

  it("SeverityBadge critical has red class", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByTestId("severity-badge").className).toContain("red");
  });

  it("AuditTable with single item shows that item's id as row", () => {
    render(<AuditTable items={[makeLog({ id: "unique-99" })]} />);
    expect(screen.getByTestId("audit-row-unique-99")).not.toBeNull();
  });

  it("StatisticsCards with total 0 shows zero", () => {
    mockHook("useAuditStatistics", { data: { data: makeStats({ total_events: 0 }) }, isLoading: false, isError: false });
    render(<StatisticsCards workspaceId={WS} />);
    expect(screen.getByTestId("stat-total").textContent).toContain("0");
  });

  it("AuditFilters search input has placeholder", () => {
    render(<AuditFilters filters={{}} onChange={vi.fn()} />);
    const el = screen.getByTestId("filter-search") as HTMLInputElement;
    expect(el.placeholder).not.toBe("");
  });

  it("AuditTable row for each log has data-testid", () => {
    const log1 = makeLog({ id: "x1" });
    const log2 = makeLog({ id: "x2" });
    render(<AuditTable items={[log1, log2]} />);
    expect(screen.getByTestId("audit-row-x1")).not.toBeNull();
    expect(screen.getByTestId("audit-row-x2")).not.toBeNull();
  });

  it("EntityAuditHistory error state renders container", () => {
    mockHook("useEntityAuditEvents", error);
    render(<EntityAuditHistory entityType="invoice" entityId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("entity-audit-history")).not.toBeNull();
  });

  it("AuditCenter workspaceId propagated correctly to events hook", () => {
    mockHook("useAuditEvents", idle);
    mockHook("useAuditStatistics", idle);
    render(<AuditCenter workspaceId="ws-propagate" />);
    const calls = vi.mocked(hooks.useAuditEvents).mock.calls;
    expect(calls.some((c) => c[0]?.workspace_id === "ws-propagate")).toBe(true);
  });

  it("AuditDetailDrawer with error state still shows drawer", () => {
    mockHook("useAuditEvent", error);
    render(<AuditDetailDrawer logId="log-x" onClose={vi.fn()} />);
    expect(screen.getByTestId("audit-detail-drawer")).not.toBeNull();
  });
});
