import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Recharts mock ─────────────────────────────────────────────────────────────
// Recharts requires canvas/SVG and ResizeObserver which aren't in jsdom.
// Mock the entire module so component renders without errors.
vi.mock("recharts", () => ({
  BarChart: ({ children, ...p }: any) => <div data-testid="barchart" {...p}>{children}</div>,
  LineChart: ({ children, ...p }: any) => <div data-testid="linechart" {...p}>{children}</div>,
  Bar: (p: any) => <div data-testid="bar-series" />,
  Line: (p: any) => <div data-testid="line-series" />,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  Cell: () => null,
}));

// ── Hook mocks ────────────────────────────────────────────────────────────────
vi.mock("@/features/workflows/api/use-workflow-analytics", () => ({
  useAnalyticsSummary: vi.fn(),
  useAnalyticsTemplates: vi.fn(),
  useAnalyticsBottlenecks: vi.fn(),
  useAnalyticsTrends: vi.fn(),
  useAnalyticsWorkload: vi.fn(),
}));

import {
  useAnalyticsSummary,
  useAnalyticsTemplates,
  useAnalyticsBottlenecks,
  useAnalyticsTrends,
  useAnalyticsWorkload,
} from "@/features/workflows/api/use-workflow-analytics";
import type {
  AnalyticsSummaryOut,
  TemplateAnalyticsOut,
  BottleneckAnalyticsOut,
  TrendAnalyticsOut,
  WorkloadAnalyticsOut,
} from "@/features/workflows/types";

const mockSummary = vi.mocked(useAnalyticsSummary);
const mockTemplates = vi.mocked(useAnalyticsTemplates);
const mockBottlenecks = vi.mocked(useAnalyticsBottlenecks);
const mockTrends = vi.mocked(useAnalyticsTrends);
const mockWorkload = vi.mocked(useAnalyticsWorkload);

const { WorkflowAnalyticsCenter } = await import("./workflow-analytics-center");

// ── Fixture factories ─────────────────────────────────────────────────────────

const WS_ID = "ws-analytics-1";

function makeSummary(overrides: Partial<AnalyticsSummaryOut> = {}): AnalyticsSummaryOut {
  return {
    total_runs: 10,
    active_runs: 2,
    completed_runs: 7,
    cancelled_runs: 1,
    completion_rate: 0.875,
    average_completion_days: 3.5,
    average_step_completion_days: 1.2,
    average_required_steps: 4.0,
    average_optional_steps: 1.5,
    data_integrity_warning: false,
    ...overrides,
  };
}

function makeTemplate(
  id: string,
  name: string,
  completed = 3,
): TemplateAnalyticsOut["items"][0] {
  return {
    template_id: id,
    template_name: name,
    runs: completed + 1,
    completed,
    cancelled: 0,
    completion_rate: completed / (completed + 1),
    average_completion_days: 2.0,
    average_steps: 3.0,
    average_required_steps: 2.0,
    average_optional_steps: 1.0,
  };
}

function makeBottleneck(name: string, avgDays = 2.5): BottleneckAnalyticsOut["items"][0] {
  return {
    step_name: name,
    template_name: "Template A",
    times_executed: 5,
    average_days: avgDays,
    completion_rate: 0.8,
    blocked_count: 1,
    skip_count: 0,
  };
}

function makeTrendBucket(date: string): TrendAnalyticsOut["buckets"][0] {
  return {
    date,
    runs_started: 2,
    runs_completed: 1,
    runs_cancelled: 0,
    completion_rate: 1.0,
  };
}

function makeWorkloadItem(owner: string): WorkloadAnalyticsOut["items"][0] {
  return {
    owner,
    pending_steps: 3,
    completed_steps: 7,
    blocked_steps: 1,
    completion_rate: 0.636,
    average_completion_days: 1.8,
  };
}

// Default: all sections return loading=false, error=null, empty data
function setupDefaultMocks() {
  mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockBottlenecks.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockTrends.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
  mockWorkload.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("WorkflowAnalyticsCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // ── Container rendering ───────────────────────────────────────────────────

  describe("container", () => {
    it("renders the outer wrapper", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workflow-analytics-center")).not.toBeNull();
    });

    it("renders the page title", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Workflow Analytics")).not.toBeNull();
    });

    it("renders the read-only subtitle", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText(/Read-only performance intelligence/i)).not.toBeNull();
    });
  });

  // ── Overview section ──────────────────────────────────────────────────────

  describe("OverviewSection", () => {
    it("renders the section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-section")).not.toBeNull();
    });

    it("shows loading skeleton when isLoading", () => {
      mockSummary.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-loading")).not.toBeNull();
    });

    it("shows error state", () => {
      mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: new Error("fail") } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-error")).not.toBeNull();
    });

    it("shows empty state when no data", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-empty")).not.toBeNull();
    });

    it("renders KPI cards when data available", () => {
      mockSummary.mockReturnValue({ data: makeSummary(), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-cards")).not.toBeNull();
    });

    it("shows total_runs stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ total_runs: 42 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-total-runs")).not.toBeNull();
      expect(screen.getByTestId("stat-total-runs").textContent).toContain("42");
    });

    it("shows active_runs stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ active_runs: 5 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-active-runs").textContent).toContain("5");
    });

    it("shows completed_runs stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ completed_runs: 30 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-completed-runs").textContent).toContain("30");
    });

    it("shows cancelled_runs stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ cancelled_runs: 3 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-cancelled-runs").textContent).toContain("3");
    });

    it("shows completion_rate as percentage", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ completion_rate: 0.875 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const el = screen.getByTestId("stat-completion-rate");
      expect(el.textContent).toMatch(/87\.5%/);
    });

    it("shows avg_completion_days stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ average_completion_days: 4.2 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-avg-completion-days")).not.toBeNull();
    });

    it("shows avg_step_completion_days stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary(), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-avg-step-days")).not.toBeNull();
    });
  });

  // ── Data integrity warning ────────────────────────────────────────────────

  describe("DataIntegrityWarning", () => {
    it("does NOT show warning when data_integrity_warning=false", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ data_integrity_warning: false }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.queryByTestId("integrity-warning")).toBeNull();
    });

    it("shows warning banner when data_integrity_warning=true", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ data_integrity_warning: true }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("integrity-warning")).not.toBeNull();
    });

    it("warning banner contains descriptive text", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ data_integrity_warning: true }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("integrity-warning").textContent).toMatch(/required steps/i);
    });
  });

  // ── Template Performance section ──────────────────────────────────────────

  describe("TemplateSection", () => {
    it("renders template section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-section")).not.toBeNull();
    });

    it("shows template loading skeleton", () => {
      mockTemplates.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-loading")).not.toBeNull();
    });

    it("shows template error", () => {
      mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: new Error("x") } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-error")).not.toBeNull();
    });

    it("shows template empty state", () => {
      mockTemplates.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-empty")).not.toBeNull();
    });

    it("renders chart when items present", () => {
      const data: TemplateAnalyticsOut = { items: [makeTemplate("t1", "Template A")] };
      mockTemplates.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-chart")).not.toBeNull();
    });

    it("renders table when items present", () => {
      const data: TemplateAnalyticsOut = { items: [makeTemplate("t1", "Template A")] };
      mockTemplates.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-table")).not.toBeNull();
    });

    it("renders a row per template item", () => {
      const data: TemplateAnalyticsOut = {
        items: [makeTemplate("t1", "Template A"), makeTemplate("t2", "Template B")],
      };
      mockTemplates.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-row-t1")).not.toBeNull();
      expect(screen.getByTestId("template-row-t2")).not.toBeNull();
    });

    it("renders template name in row", () => {
      const data: TemplateAnalyticsOut = { items: [makeTemplate("t1", "Enterprise Sales")] };
      mockTemplates.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Enterprise Sales")).not.toBeNull();
    });
  });

  // ── Bottleneck section ────────────────────────────────────────────────────

  describe("BottleneckSection", () => {
    it("renders bottleneck section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-section")).not.toBeNull();
    });

    it("shows bottleneck loading", () => {
      mockBottlenecks.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-loading")).not.toBeNull();
    });

    it("shows bottleneck error", () => {
      mockBottlenecks.mockReturnValue({ data: undefined, isLoading: false, error: new Error("x") } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-error")).not.toBeNull();
    });

    it("shows bottleneck empty state", () => {
      mockBottlenecks.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-empty")).not.toBeNull();
    });

    it("renders bottleneck table", () => {
      const data: BottleneckAnalyticsOut = { items: [makeBottleneck("Contract Review")] };
      mockBottlenecks.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-table")).not.toBeNull();
    });

    it("renders a row per bottleneck", () => {
      const data: BottleneckAnalyticsOut = {
        items: [makeBottleneck("Review"), makeBottleneck("Approval")],
      };
      mockBottlenecks.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-row-0")).not.toBeNull();
      expect(screen.getByTestId("bottleneck-row-1")).not.toBeNull();
    });

    it("displays step name in bottleneck row", () => {
      const data: BottleneckAnalyticsOut = { items: [makeBottleneck("Executive Sign-off")] };
      mockBottlenecks.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Executive Sign-off")).not.toBeNull();
    });

    it("shows 'slowest first' description text", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText(/slowest first/i)).not.toBeNull();
    });
  });

  // ── Trend section ─────────────────────────────────────────────────────────

  describe("TrendSection", () => {
    it("renders trend section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("trend-section")).not.toBeNull();
    });

    it("renders period selector", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("period-selector")).not.toBeNull();
    });

    it("renders 7-day button", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("period-btn-7")).not.toBeNull();
    });

    it("renders 30-day button", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("period-btn-30")).not.toBeNull();
    });

    it("renders 90-day button", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("period-btn-90")).not.toBeNull();
    });

    it("default period is 30", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      // 30-day hook should be called with period=30
      expect(mockTrends).toHaveBeenCalledWith(WS_ID, 30);
    });

    it("clicking 7 changes period to 7", async () => {
      const user = userEvent.setup();
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      await user.click(screen.getByTestId("period-btn-7"));
      expect(mockTrends).toHaveBeenCalledWith(WS_ID, 7);
    });

    it("clicking 90 changes period to 90", async () => {
      const user = userEvent.setup();
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      await user.click(screen.getByTestId("period-btn-90"));
      expect(mockTrends).toHaveBeenCalledWith(WS_ID, 90);
    });

    it("shows trend loading state", () => {
      mockTrends.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("trend-loading")).not.toBeNull();
    });

    it("shows trend error", () => {
      mockTrends.mockReturnValue({ data: undefined, isLoading: false, error: new Error("x") } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("trend-error")).not.toBeNull();
    });

    it("shows trend empty state", () => {
      mockTrends.mockReturnValue({ data: { period: 30, buckets: [] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("trend-empty")).not.toBeNull();
    });

    it("renders trend chart when buckets present", () => {
      const data: TrendAnalyticsOut = {
        period: 7,
        buckets: [makeTrendBucket("2026-06-30")],
      };
      mockTrends.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("trend-chart")).not.toBeNull();
    });
  });

  // ── Workload section ──────────────────────────────────────────────────────

  describe("WorkloadSection", () => {
    it("renders workload section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-section")).not.toBeNull();
    });

    it("shows workload loading", () => {
      mockWorkload.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-loading")).not.toBeNull();
    });

    it("shows workload error", () => {
      mockWorkload.mockReturnValue({ data: undefined, isLoading: false, error: new Error("x") } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-error")).not.toBeNull();
    });

    it("shows workload empty state", () => {
      mockWorkload.mockReturnValue({ data: { items: [] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-empty")).not.toBeNull();
    });

    it("renders workload chart when items present", () => {
      const data: WorkloadAnalyticsOut = { items: [makeWorkloadItem("owner")] };
      mockWorkload.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-chart")).not.toBeNull();
    });

    it("renders workload table when items present", () => {
      const data: WorkloadAnalyticsOut = { items: [makeWorkloadItem("owner")] };
      mockWorkload.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-table")).not.toBeNull();
    });

    it("renders one row per workload item", () => {
      const data: WorkloadAnalyticsOut = {
        items: [makeWorkloadItem("admin"), makeWorkloadItem("member")],
      };
      mockWorkload.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("workload-row-admin")).not.toBeNull();
      expect(screen.getByTestId("workload-row-member")).not.toBeNull();
    });

    it("shows pending, completed, blocked counts in row", () => {
      const item = { ...makeWorkloadItem("owner"), pending_steps: 3, completed_steps: 7, blocked_steps: 2 };
      const data: WorkloadAnalyticsOut = { items: [item] };
      mockWorkload.mockReturnValue({ data, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("workload-row-owner");
      expect(row.textContent).toContain("3");
      expect(row.textContent).toContain("7");
    });
  });

  // ── Hook call verification ────────────────────────────────────────────────

  describe("hook invocations", () => {
    it("calls useAnalyticsSummary with workspaceId", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(mockSummary).toHaveBeenCalledWith(WS_ID);
    });

    it("calls useAnalyticsTemplates with workspaceId", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(mockTemplates).toHaveBeenCalledWith(WS_ID);
    });

    it("calls useAnalyticsBottlenecks with workspaceId", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(mockBottlenecks).toHaveBeenCalledWith(WS_ID);
    });

    it("calls useAnalyticsTrends with workspaceId and default period", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(mockTrends).toHaveBeenCalledWith(WS_ID, 30);
    });

    it("calls useAnalyticsWorkload with workspaceId", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(mockWorkload).toHaveBeenCalledWith(WS_ID);
    });
  });

  // ── Multi-section: all loaded ─────────────────────────────────────────────

  describe("all sections loaded", () => {
    beforeEach(() => {
      mockSummary.mockReturnValue({ data: makeSummary(), isLoading: false, error: null } as any);
      mockTemplates.mockReturnValue({
        data: { items: [makeTemplate("t1", "Template A")] }, isLoading: false, error: null,
      } as any);
      mockBottlenecks.mockReturnValue({
        data: { items: [makeBottleneck("Review Step")] }, isLoading: false, error: null,
      } as any);
      mockTrends.mockReturnValue({
        data: { period: 30, buckets: [makeTrendBucket("2026-06-30")] }, isLoading: false, error: null,
      } as any);
      mockWorkload.mockReturnValue({
        data: { items: [makeWorkloadItem("admin"), makeWorkloadItem("member")] }, isLoading: false, error: null,
      } as any);
    });

    it("renders all sections simultaneously", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-cards")).not.toBeNull();
      expect(screen.getByTestId("template-table")).not.toBeNull();
      expect(screen.getByTestId("bottleneck-table")).not.toBeNull();
      expect(screen.getByTestId("trend-chart")).not.toBeNull();
      expect(screen.getByTestId("workload-table")).not.toBeNull();
    });

    it("does not show loading for any section", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.queryByTestId("overview-loading")).toBeNull();
      expect(screen.queryByTestId("template-loading")).toBeNull();
      expect(screen.queryByTestId("bottleneck-loading")).toBeNull();
      expect(screen.queryByTestId("trend-loading")).toBeNull();
      expect(screen.queryByTestId("workload-loading")).toBeNull();
    });
  });

  // ── Stat display details ──────────────────────────────────────────────────

  describe("stat display", () => {
    it("shows average required steps stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ average_required_steps: 4.0 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-avg-required-steps")).not.toBeNull();
    });

    it("shows average optional steps stat", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ average_optional_steps: 1.5 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-avg-optional-steps")).not.toBeNull();
    });

    it("formats completion rate as percentage string", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ completion_rate: 0.5 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-completion-rate").textContent).toMatch(/50\.0%/);
    });

    it("shows zero total_runs correctly", () => {
      mockSummary.mockReturnValue({ data: makeSummary({ total_runs: 0, active_runs: 0, completed_runs: 0, cancelled_runs: 0 }), isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("stat-total-runs").textContent).toContain("0");
    });
  });

  // ── Template section details ──────────────────────────────────────────────

  describe("template section details", () => {
    it("does not show template empty when data is undefined (no error, no loading)", () => {
      // undefined data = no data yet (not the same as empty list)
      mockTemplates.mockReturnValue({ data: undefined, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      // No error, no data, not loading → empty state uses undefined check
      expect(screen.queryByTestId("template-chart")).toBeNull();
    });

    it("shows completion rate in template row", () => {
      const item = { ...makeTemplate("t1", "Alpha"), completion_rate: 0.75 };
      mockTemplates.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("template-row-t1");
      expect(row.textContent).toMatch(/75\.0%/);
    });

    it("shows average completion days in template row", () => {
      const item = { ...makeTemplate("t1", "Beta"), average_completion_days: 5.0 };
      mockTemplates.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("template-row-t1");
      expect(row.textContent).toContain("5.0");
    });

    it("renders null template_id as none in row testid", () => {
      const item = { ...makeTemplate("t1", "Standalone"), template_id: null };
      mockTemplates.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("template-row-none")).not.toBeNull();
    });
  });

  // ── Bottleneck section details ────────────────────────────────────────────

  describe("bottleneck section details", () => {
    it("shows blocked_count badge when > 0", () => {
      const item = { ...makeBottleneck("Gate"), blocked_count: 3 };
      mockBottlenecks.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("bottleneck-row-0");
      expect(row.textContent).toContain("3");
    });

    it("shows zero skip count without badge", () => {
      const item = { ...makeBottleneck("Step"), skip_count: 0 };
      mockBottlenecks.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("bottleneck-row-0")).not.toBeNull();
    });

    it("shows template name in row", () => {
      const item = { ...makeBottleneck("Review"), template_name: "Enterprise Flow" };
      mockBottlenecks.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Enterprise Flow")).not.toBeNull();
    });

    it("shows times_executed in row", () => {
      const item = { ...makeBottleneck("Audit"), times_executed: 12 };
      mockBottlenecks.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("bottleneck-row-0");
      expect(row.textContent).toContain("12");
    });
  });

  // ── Trend section details ─────────────────────────────────────────────────

  describe("trend section details", () => {
    it("period buttons have correct labels", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("period-btn-7").textContent).toContain("7");
      expect(screen.getByTestId("period-btn-30").textContent).toContain("30");
      expect(screen.getByTestId("period-btn-90").textContent).toContain("90");
    });

    it("clicking 30 re-calls hook with period 30", async () => {
      const user = userEvent.setup();
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      // First click 7
      await user.click(screen.getByTestId("period-btn-7"));
      // Then click back to 30
      await user.click(screen.getByTestId("period-btn-30"));
      expect(mockTrends).toHaveBeenCalledWith(WS_ID, 30);
    });

    it("trend chart not shown when no buckets", () => {
      mockTrends.mockReturnValue({ data: { period: 7, buckets: [] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.queryByTestId("trend-chart")).toBeNull();
    });
  });

  // ── Workload section details ──────────────────────────────────────────────

  describe("workload section details", () => {
    it("shows completion rate in workload row", () => {
      const item = { ...makeWorkloadItem("owner"), completion_rate: 0.8 };
      mockWorkload.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("workload-row-owner");
      expect(row.textContent).toMatch(/80\.0%/);
    });

    it("shows avg completion days in workload row", () => {
      const item = { ...makeWorkloadItem("admin"), average_completion_days: 3.7 };
      mockWorkload.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("workload-row-admin");
      expect(row.textContent).toContain("3.7");
    });

    it("blocked_steps badge shown when > 0", () => {
      const item = { ...makeWorkloadItem("member"), blocked_steps: 5 };
      mockWorkload.mockReturnValue({ data: { items: [item] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      const row = screen.getByTestId("workload-row-member");
      expect(row.textContent).toContain("5");
    });

    it("workload section heading text", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Owner Workload")).not.toBeNull();
    });
  });

  // ── Error isolation ───────────────────────────────────────────────────────

  describe("error isolation", () => {
    it("error in one section does not affect other sections", () => {
      // Summary errors, rest succeed
      mockSummary.mockReturnValue({ data: undefined, isLoading: false, error: new Error("x") } as any);
      mockTemplates.mockReturnValue({ data: { items: [makeTemplate("t1", "T")] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-error")).not.toBeNull();
      expect(screen.getByTestId("template-table")).not.toBeNull();
    });

    it("loading in one section does not block others", () => {
      mockSummary.mockReturnValue({ data: undefined, isLoading: true, error: null } as any);
      mockTemplates.mockReturnValue({ data: { items: [makeTemplate("t1", "T")] }, isLoading: false, error: null } as any);
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByTestId("overview-loading")).not.toBeNull();
      expect(screen.getByTestId("template-table")).not.toBeNull();
    });
  });

  // ── Section headings ──────────────────────────────────────────────────────

  describe("section headings", () => {
    it("shows Overview heading", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Overview")).not.toBeNull();
    });

    it("shows Template Performance heading", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Template Performance")).not.toBeNull();
    });

    it("shows Bottlenecks heading", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Bottlenecks")).not.toBeNull();
    });

    it("shows Trend heading", () => {
      render(<WorkflowAnalyticsCenter workspaceId={WS_ID} />);
      expect(screen.getByText("Trend")).not.toBeNull();
    });
  });
});
