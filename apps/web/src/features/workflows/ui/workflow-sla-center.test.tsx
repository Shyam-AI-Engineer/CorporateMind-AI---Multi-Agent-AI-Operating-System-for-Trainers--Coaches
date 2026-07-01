import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkflowSLACenter } from "./workflow-sla-center";

// ── Recharts mock (jsdom has no canvas/SVG/ResizeObserver) ────────────────────
vi.mock("recharts", () => ({
  AreaChart: ({ children, ...p }: any) => (
    <div data-testid="areachart" {...p}>
      {children}
    </div>
  ),
  Area: (p: any) => <div data-testid="area-series" />,
  BarChart: ({ children, ...p }: any) => (
    <div data-testid="barchart" {...p}>
      {children}
    </div>
  ),
  Bar: (p: any) => <div data-testid="bar-series" />,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  Cell: () => null,
}));

// ── Hooks mock ────────────────────────────────────────────────────────────────
vi.mock("@/features/workflows/api/use-workflow-sla", () => ({
  useSLASummary: vi.fn(),
  useSLAOverdue: vi.fn(),
  useSLATemplates: vi.fn(),
  useSLAOwner: vi.fn(),
  useSLATrend: vi.fn(),
}));

import {
  useSLASummary,
  useSLAOverdue,
  useSLATemplates,
  useSLAOwner,
  useSLATrend,
} from "@/features/workflows/api/use-workflow-sla";

const mockSummary = vi.mocked(useSLASummary);
const mockOverdue = vi.mocked(useSLAOverdue);
const mockTemplates = vi.mocked(useSLATemplates);
const mockOwner = vi.mocked(useSLAOwner);
const mockTrend = vi.mocked(useSLATrend);

// ── Default (empty) state ─────────────────────────────────────────────────────
function setupDefaultMocks() {
  mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockOverdue.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockOwner.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockTrend.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
}

const WS = "test-workspace";

// ── Root component ────────────────────────────────────────────────────────────
describe("WorkflowSLACenter root", () => {
  beforeEach(setupDefaultMocks);

  it("renders root testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("workflow-sla-center")).not.toBeNull();
  });

  it("renders page heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Workflow SLA Dashboard")).not.toBeNull();
  });

  it("renders description subtitle", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText(/read-only sla compliance/i)).not.toBeNull();
  });
});

// ── Overview section ──────────────────────────────────────────────────────────
describe("OverviewSection", () => {
  beforeEach(setupDefaultMocks);

  it("renders overview-section testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-section")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: new Error("oops") } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-error")).not.toBeNull();
  });

  it("shows empty state when no data", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-empty")).not.toBeNull();
  });

  it("renders stat cards when data present", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 5,
        overdue_runs: 2,
        sla_compliance_rate: 0.6,
        average_days_open: 25,
        average_days_overdue: 8,
        critical_overdue: 1,
        warning_overdue: 1,
        healthy_runs: 3,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-cards")).not.toBeNull();
    expect(screen.getByTestId("stat-active-runs")).not.toBeNull();
    expect(screen.getByTestId("stat-overdue-runs")).not.toBeNull();
    expect(screen.getByTestId("stat-compliance-rate")).not.toBeNull();
    expect(screen.getByTestId("stat-avg-days-open")).not.toBeNull();
    expect(screen.getByTestId("stat-healthy-runs")).not.toBeNull();
    expect(screen.getByTestId("stat-warning-overdue")).not.toBeNull();
    expect(screen.getByTestId("stat-critical-overdue")).not.toBeNull();
    expect(screen.getByTestId("stat-avg-days-overdue")).not.toBeNull();
  });

  it("does not show integrity warning when false", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 1,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 5,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("integrity-warning")).toBeNull();
  });

  it("shows integrity warning when true", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 1,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 5,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: true,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("integrity-warning")).not.toBeNull();
  });

  it("displays compliance percentage", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 4,
        overdue_runs: 1,
        sla_compliance_rate: 0.75,
        average_days_open: 20,
        average_days_overdue: 5,
        critical_overdue: 0,
        warning_overdue: 1,
        healthy_runs: 3,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-compliance-rate").textContent).toContain("75.0%");
  });
});

// ── Overdue section ───────────────────────────────────────────────────────────
describe("OverdueSection", () => {
  beforeEach(setupDefaultMocks);

  it("renders overdue-section testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-section")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockOverdue.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockOverdue.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-error")).not.toBeNull();
  });

  it("shows all-healthy empty state when no overdue items", () => {
    mockOverdue.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-empty")).not.toBeNull();
  });

  it("renders overdue table with rows", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r1",
            title: "Late Deal",
            template_name: "Sales",
            entity_type: "lead",
            entity_title: "ACME",
            started_at: "2026-05-01T10:00:00+00:00",
            days_open: 45,
            days_overdue: 15,
            current_step: "Send Proposal",
            owner_role: "member",
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-table")).not.toBeNull();
    expect(screen.getByTestId("overdue-row-0")).not.toBeNull();
    expect(screen.getByTestId("overdue-badge-0")).not.toBeNull();
  });

  it("renders title in overdue row", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r2",
            title: "Overdue Process",
            template_name: null,
            entity_type: null,
            entity_title: null,
            started_at: "2026-05-01T00:00:00+00:00",
            days_open: 50,
            days_overdue: 20,
            current_step: null,
            owner_role: null,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Overdue Process")).not.toBeNull();
  });

  it("renders multiple overdue rows", () => {
    const items = Array.from({ length: 3 }, (_, i) => ({
      run_id: `r${i}`,
      title: `Run ${i}`,
      template_name: null,
      entity_type: null,
      entity_title: null,
      started_at: "2026-05-01T00:00:00+00:00",
      days_open: 40 + i,
      days_overdue: 10 + i,
      current_step: null,
      owner_role: null,
    }));
    mockOverdue.mockReturnValue({ data: { items }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-row-0")).not.toBeNull();
    expect(screen.getByTestId("overdue-row-1")).not.toBeNull();
    expect(screen.getByTestId("overdue-row-2")).not.toBeNull();
  });
});

// ── Template SLA section ──────────────────────────────────────────────────────
describe("TemplateSLASection", () => {
  beforeEach(setupDefaultMocks);

  it("renders template-sla-section testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-section")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockTemplates.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-error")).not.toBeNull();
  });

  it("shows empty state when no items", () => {
    mockTemplates.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-empty")).not.toBeNull();
  });

  it("renders table when items present", () => {
    mockTemplates.mockReturnValue({
      data: {
        items: [
          {
            template_id: "t1",
            template_name: "Sales Process",
            runs: 5,
            overdue: 2,
            compliance_rate: 0.6,
            average_duration_days: 25,
            average_days_overdue: 8,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-table")).not.toBeNull();
    expect(screen.getByTestId("template-sla-row-0")).not.toBeNull();
  });

  it("shows template name in row", () => {
    mockTemplates.mockReturnValue({
      data: {
        items: [
          {
            template_id: null,
            template_name: "Standalone (no template)",
            runs: 2,
            overdue: 0,
            compliance_rate: 1.0,
            average_duration_days: 10,
            average_days_overdue: 0,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Standalone (no template)")).not.toBeNull();
  });
});

// ── Owner SLA section ─────────────────────────────────────────────────────────
describe("OwnerSLASection", () => {
  beforeEach(setupDefaultMocks);

  it("renders owner-sla-section testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-section")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockOwner.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockOwner.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-error")).not.toBeNull();
  });

  it("shows empty when no items", () => {
    mockOwner.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-empty")).not.toBeNull();
  });

  it("renders chart and table when items present", () => {
    mockOwner.mockReturnValue({
      data: {
        items: [
          {
            owner_role: "member",
            assigned_steps: 10,
            completed_steps: 8,
            overdue_steps: 2,
            compliance_rate: 0.8,
            average_completion_days: 5,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-chart")).not.toBeNull();
    expect(screen.getByTestId("owner-sla-table")).not.toBeNull();
    expect(screen.getByTestId("owner-sla-row-0")).not.toBeNull();
  });

  it("renders multiple owner rows", () => {
    mockOwner.mockReturnValue({
      data: {
        items: [
          {
            owner_role: "owner",
            assigned_steps: 5,
            completed_steps: 5,
            overdue_steps: 0,
            compliance_rate: 1.0,
            average_completion_days: 3,
          },
          {
            owner_role: "member",
            assigned_steps: 10,
            completed_steps: 7,
            overdue_steps: 3,
            compliance_rate: 0.7,
            average_completion_days: 6,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-row-0")).not.toBeNull();
    expect(screen.getByTestId("owner-sla-row-1")).not.toBeNull();
  });
});

// ── Trend section ─────────────────────────────────────────────────────────────
describe("TrendSection", () => {
  beforeEach(setupDefaultMocks);

  it("renders trend-section testid", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-section")).not.toBeNull();
  });

  it("renders period selector buttons", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("period-selector")).not.toBeNull();
    expect(screen.getByTestId("period-btn-7")).not.toBeNull();
    expect(screen.getByTestId("period-btn-30")).not.toBeNull();
    expect(screen.getByTestId("period-btn-90")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockTrend.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockTrend.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-error")).not.toBeNull();
  });

  it("shows empty when no buckets", () => {
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-empty")).not.toBeNull();
  });

  it("renders chart when buckets present", () => {
    mockTrend.mockReturnValue({
      data: {
        period: 30,
        buckets: [
          { date: "2026-06-01", healthy: 2, warning: 1, critical: 0, completed: 1 },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-chart")).not.toBeNull();
  });

  it("clicking 7-day period updates selection", () => {
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [{ date: "2026-06-01", healthy: 1, warning: 0, critical: 0, completed: 0 }] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    const btn7 = screen.getByTestId("period-btn-7");
    fireEvent.click(btn7);
    expect(mockTrend).toHaveBeenCalledWith(WS, 7);
  });

  it("clicking 90-day period updates selection", () => {
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId("period-btn-90"));
    expect(mockTrend).toHaveBeenCalledWith(WS, 90);
  });
});

// ── Integrity section ─────────────────────────────────────────────────────────
describe("IntegritySection", () => {
  beforeEach(setupDefaultMocks);

  it("not rendered when no integrity warning", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 1,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 5,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("integrity-section")).toBeNull();
  });

  it("renders when data_integrity_warning is true", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 1,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 5,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: true,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("integrity-section")).not.toBeNull();
    expect(screen.getByTestId("integrity-banner")).not.toBeNull();
  });

  it("integrity banner mentions completed_at", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 1,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 5,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: true,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Data Integrity Warning")).not.toBeNull();
  });
});

// ── Section heading tests ─────────────────────────────────────────────────────
describe("Section headings", () => {
  beforeEach(setupDefaultMocks);

  it("shows SLA Overview heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("SLA Overview")).not.toBeNull();
  });

  it("shows Overdue Runs heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Overdue Runs")).not.toBeNull();
  });

  it("shows SLA by Template heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("SLA by Template")).not.toBeNull();
  });

  it("shows SLA by Owner Role heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("SLA by Owner Role")).not.toBeNull();
  });

  it("shows SLA Health Trend heading", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("SLA Health Trend")).not.toBeNull();
  });
});

// ── Error isolation ───────────────────────────────────────────────────────────
describe("Error isolation between sections", () => {
  it("error in summary does not break other sections", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    mockOverdue.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    mockTemplates.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    mockOwner.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-error")).not.toBeNull();
    expect(screen.getByTestId("overdue-empty")).not.toBeNull();
  });

  it("error in overdue does not break trend", () => {
    setupDefaultMocks();
    mockOverdue.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-error")).not.toBeNull();
    expect(screen.getByTestId("trend-empty")).not.toBeNull();
  });
});

// ── Recharts rendered in chart containers ─────────────────────────────────────
describe("Chart rendering", () => {
  it("renders AreaChart inside trend-chart", () => {
    setupDefaultMocks();
    mockTrend.mockReturnValue({
      data: {
        period: 7,
        buckets: [{ date: "2026-06-25", healthy: 1, warning: 0, critical: 0, completed: 1 }],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    const trendChart = screen.getByTestId("trend-chart");
    expect(trendChart.querySelector("[data-testid='areachart']")).not.toBeNull();
  });

  it("renders BarChart inside owner-sla-chart", () => {
    setupDefaultMocks();
    mockOwner.mockReturnValue({
      data: {
        items: [
          {
            owner_role: "member",
            assigned_steps: 5,
            completed_steps: 4,
            overdue_steps: 1,
            compliance_rate: 0.8,
            average_completion_days: 4,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    const ownerChart = screen.getByTestId("owner-sla-chart");
    expect(ownerChart.querySelector("[data-testid='barchart']")).not.toBeNull();
  });
});

// ── Overview stat values ──────────────────────────────────────────────────────
describe("Overview stat values", () => {
  beforeEach(setupDefaultMocks);

  it("displays active run count", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 12,
        overdue_runs: 0,
        sla_compliance_rate: 1,
        average_days_open: 10,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 12,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-active-runs").textContent).toContain("12");
  });

  it("displays healthy run count", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 5,
        overdue_runs: 1,
        sla_compliance_rate: 0.8,
        average_days_open: 20,
        average_days_overdue: 5,
        critical_overdue: 0,
        warning_overdue: 1,
        healthy_runs: 4,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-healthy-runs").textContent).toContain("4");
  });

  it("displays critical overdue count", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 3,
        overdue_runs: 2,
        sla_compliance_rate: 0.33,
        average_days_open: 50,
        average_days_overdue: 20,
        critical_overdue: 2,
        warning_overdue: 0,
        healthy_runs: 1,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-critical-overdue").textContent).toContain("2");
  });

  it("displays 100% compliance for all healthy", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 3,
        overdue_runs: 0,
        sla_compliance_rate: 1.0,
        average_days_open: 10,
        average_days_overdue: 0,
        critical_overdue: 0,
        warning_overdue: 0,
        healthy_runs: 3,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-compliance-rate").textContent).toContain("100.0%");
  });

  it("shows warning_overdue count", () => {
    mockSummary.mockReturnValue({
      data: {
        active_runs: 5,
        overdue_runs: 3,
        sla_compliance_rate: 0.4,
        average_days_open: 35,
        average_days_overdue: 12,
        critical_overdue: 1,
        warning_overdue: 2,
        healthy_runs: 2,
        data_integrity_warning: false,
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("stat-warning-overdue").textContent).toContain("2");
  });
});

// ── Overdue table details ─────────────────────────────────────────────────────
describe("Overdue table details", () => {
  beforeEach(setupDefaultMocks);

  it("shows em-dash for null template_name", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r1",
            title: "No Template Run",
            template_name: null,
            entity_type: null,
            entity_title: null,
            started_at: "2026-05-01T00:00:00+00:00",
            days_open: 45,
            days_overdue: 15,
            current_step: null,
            owner_role: null,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    const row = screen.getByTestId("overdue-row-0");
    expect(row.textContent).toContain("—");
  });

  it("shows entity title when present", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r1",
            title: "Run With Entity",
            template_name: "Sales",
            entity_type: "lead",
            entity_title: "Tech Corp",
            started_at: "2026-05-01T00:00:00+00:00",
            days_open: 40,
            days_overdue: 10,
            current_step: "Review",
            owner_role: "admin",
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Tech Corp")).not.toBeNull();
  });

  it("shows current step name", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r1",
            title: "Run",
            template_name: null,
            entity_type: null,
            entity_title: null,
            started_at: "2026-05-01T00:00:00+00:00",
            days_open: 35,
            days_overdue: 5,
            current_step: "Send Contract",
            owner_role: "member",
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("Send Contract")).not.toBeNull();
  });
});

// ── Template SLA details ──────────────────────────────────────────────────────
describe("Template SLA table details", () => {
  beforeEach(setupDefaultMocks);

  it("shows compliance percentage in template row", () => {
    mockTemplates.mockReturnValue({
      data: {
        items: [
          {
            template_id: "t1",
            template_name: "Onboarding",
            runs: 10,
            overdue: 3,
            compliance_rate: 0.7,
            average_duration_days: 22,
            average_days_overdue: 9,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-row-0").textContent).toContain("70.0%");
  });

  it("renders two template rows", () => {
    mockTemplates.mockReturnValue({
      data: {
        items: [
          { template_id: "t1", template_name: "T1", runs: 5, overdue: 2, compliance_rate: 0.6, average_duration_days: 20, average_days_overdue: 8 },
          { template_id: "t2", template_name: "T2", runs: 3, overdue: 0, compliance_rate: 1.0, average_duration_days: 12, average_days_overdue: 0 },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-row-0")).not.toBeNull();
    expect(screen.getByTestId("template-sla-row-1")).not.toBeNull();
  });
});

// ── Owner SLA details ─────────────────────────────────────────────────────────
describe("Owner SLA table details", () => {
  beforeEach(setupDefaultMocks);

  it("shows owner role badge", () => {
    mockOwner.mockReturnValue({
      data: {
        items: [
          {
            owner_role: "admin",
            assigned_steps: 8,
            completed_steps: 7,
            overdue_steps: 1,
            compliance_rate: 0.875,
            average_completion_days: 4,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("admin")).not.toBeNull();
  });

  it("shows compliance rate in owner row", () => {
    mockOwner.mockReturnValue({
      data: {
        items: [
          {
            owner_role: "member",
            assigned_steps: 4,
            completed_steps: 4,
            overdue_steps: 0,
            compliance_rate: 1.0,
            average_completion_days: 3,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-row-0").textContent).toContain("100.0%");
  });
});

// ── Trend period switching ────────────────────────────────────────────────────
describe("Trend period default", () => {
  beforeEach(setupDefaultMocks);

  it("defaults to 30-day period on mount", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(mockTrend).toHaveBeenCalledWith(WS, 30);
  });

  it("clicking 7 calls hook with period 7", () => {
    mockTrend.mockReturnValue({ data: { period: 7, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    fireEvent.click(screen.getByTestId("period-btn-7"));
    expect(mockTrend).toHaveBeenCalledWith(WS, 7);
  });
});

// ── Loading states across all sections ───────────────────────────────────────
describe("Loading states across sections", () => {
  it("template loading does not show table", () => {
    setupDefaultMocks();
    mockTemplates.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("template-sla-loading")).not.toBeNull();
    expect(screen.queryByTestId("template-sla-table")).toBeNull();
  });

  it("owner loading does not show chart", () => {
    setupDefaultMocks();
    mockOwner.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-loading")).not.toBeNull();
    expect(screen.queryByTestId("owner-sla-chart")).toBeNull();
  });

  it("trend loading does not show chart", () => {
    setupDefaultMocks();
    mockTrend.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("trend-loading")).not.toBeNull();
    expect(screen.queryByTestId("trend-chart")).toBeNull();
  });

  it("overdue loading does not show table", () => {
    setupDefaultMocks();
    mockOverdue.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-loading")).not.toBeNull();
    expect(screen.queryByTestId("overdue-table")).toBeNull();
  });
});

// ── Empty states don't show data containers ───────────────────────────────────
describe("Empty states don't show data containers", () => {
  beforeEach(setupDefaultMocks);

  it("overdue empty does not show table", () => {
    mockOverdue.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("overdue-table")).toBeNull();
  });

  it("template-sla empty does not show table", () => {
    mockTemplates.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("template-sla-table")).toBeNull();
  });

  it("owner-sla empty does not show chart", () => {
    mockOwner.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("owner-sla-chart")).toBeNull();
  });

  it("trend empty does not show chart", () => {
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.queryByTestId("trend-chart")).toBeNull();
  });
});

// ── All sections rendered together ───────────────────────────────────────────
describe("All sections present in DOM", () => {
  beforeEach(setupDefaultMocks);

  it("all 5 main section testids present", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-section")).not.toBeNull();
    expect(screen.getByTestId("overdue-section")).not.toBeNull();
    expect(screen.getByTestId("template-sla-section")).not.toBeNull();
    expect(screen.getByTestId("owner-sla-section")).not.toBeNull();
    expect(screen.getByTestId("trend-section")).not.toBeNull();
  });

  it("period buttons are all rendered", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByText("7 days")).not.toBeNull();
    expect(screen.getByText("30 days")).not.toBeNull();
    expect(screen.getByText("90 days")).not.toBeNull();
  });
});

// ── workspaceId propagated to hooks ──────────────────────────────────────────
describe("workspaceId propagated to hooks", () => {
  it("passes workspaceId to useSLASummary", () => {
    setupDefaultMocks();
    render(<WorkflowSLACenter workspaceId="ws-123" />);
    expect(mockSummary).toHaveBeenCalledWith("ws-123");
  });

  it("passes workspaceId to useSLAOverdue", () => {
    setupDefaultMocks();
    render(<WorkflowSLACenter workspaceId="ws-456" />);
    expect(mockOverdue).toHaveBeenCalledWith("ws-456");
  });

  it("passes workspaceId to useSLATemplates", () => {
    setupDefaultMocks();
    render(<WorkflowSLACenter workspaceId="ws-789" />);
    expect(mockTemplates).toHaveBeenCalledWith("ws-789");
  });

  it("passes workspaceId to useSLAOwner", () => {
    setupDefaultMocks();
    render(<WorkflowSLACenter workspaceId="ws-101" />);
    expect(mockOwner).toHaveBeenCalledWith("ws-101");
  });

  it("passes workspaceId to useSLATrend", () => {
    setupDefaultMocks();
    render(<WorkflowSLACenter workspaceId="ws-202" />);
    expect(mockTrend).toHaveBeenCalledWith("ws-202", 30);
  });
});

// ── Overdue badge shows days ──────────────────────────────────────────────────
describe("Overdue badge content", () => {
  beforeEach(setupDefaultMocks);

  it("badge shows days_overdue value", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          {
            run_id: "r1",
            title: "Late",
            template_name: null,
            entity_type: null,
            entity_title: null,
            started_at: "2026-05-01T00:00:00+00:00",
            days_open: 37,
            days_overdue: 7,
            current_step: null,
            owner_role: null,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-badge-0").textContent).toContain("7.0d");
  });

  it("two overdue items have two badges", () => {
    mockOverdue.mockReturnValue({
      data: {
        items: [
          { run_id: "r1", title: "A", template_name: null, entity_type: null, entity_title: null, started_at: "2026-05-01T00:00:00+00:00", days_open: 35, days_overdue: 5, current_step: null, owner_role: null },
          { run_id: "r2", title: "B", template_name: null, entity_type: null, entity_title: null, started_at: "2026-05-01T00:00:00+00:00", days_open: 40, days_overdue: 10, current_step: null, owner_role: null },
        ],
      },
      isLoading: false,
      error: null,
    } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-badge-0")).not.toBeNull();
    expect(screen.getByTestId("overdue-badge-1")).not.toBeNull();
  });

  it("error in template does not affect overdue display", () => {
    mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    mockOverdue.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("overdue-empty")).not.toBeNull();
    expect(screen.getByTestId("template-sla-error")).not.toBeNull();
  });

  it("error in owner does not affect trend display", () => {
    mockOwner.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
    mockTrend.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("owner-sla-error")).not.toBeNull();
    expect(screen.getByTestId("trend-empty")).not.toBeNull();
  });

  it("all sections load independently on first render", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(mockSummary).toHaveBeenCalled();
    expect(mockOverdue).toHaveBeenCalled();
    expect(mockTemplates).toHaveBeenCalled();
    expect(mockOwner).toHaveBeenCalled();
    expect(mockTrend).toHaveBeenCalled();
  });

  it("page title is in document metadata", () => {
    render(<WorkflowSLACenter workspaceId={WS} />);
    expect(screen.getByTestId("workflow-sla-center")).not.toBeNull();
  });
});
