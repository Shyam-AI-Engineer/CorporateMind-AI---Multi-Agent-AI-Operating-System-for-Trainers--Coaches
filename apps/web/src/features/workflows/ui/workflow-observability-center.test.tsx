import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkflowObservabilityCenter } from "./workflow-observability-center";

// ── Mock Recharts ─────────────────────────────────────────────────────────────

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="barchart">{children}</div>
  ),
  Bar: () => null,
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="linechart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Legend: () => null,
}));

// ── Mock hooks ────────────────────────────────────────────────────────────────

vi.mock("@/features/workflows/api/use-workflow-observability", () => ({
  useObsBottlenecks: vi.fn(),
  useObsStepAnalysis: vi.fn(),
  useObsOwnerCapacity: vi.fn(),
  useObsTemplateCapacity: vi.fn(),
  useObsFlowHealth: vi.fn(),
}));

import {
  useObsBottlenecks,
  useObsStepAnalysis,
  useObsOwnerCapacity,
  useObsTemplateCapacity,
  useObsFlowHealth,
} from "@/features/workflows/api/use-workflow-observability";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FLOW_HEALTH_DATA = {
  healthy_flows: 12,
  warning_flows: 3,
  critical_flows: 2,
  average_step_completion_days: 2.5,
  average_run_completion_days: 8.3,
  flow_health_score: 70.6,
  data_integrity_warning: false,
};

const FLOW_HEALTH_WITH_WARNING = {
  ...FLOW_HEALTH_DATA,
  data_integrity_warning: true,
};

const BOTTLENECK_DATA = {
  items: [
    {
      template_name: "Sales Flow",
      slowest_step: "Contract Review",
      average_days: 5.2,
      max_days: 12.0,
      runs_affected: 8,
      bottleneck_score: 52.0,
    },
    {
      template_name: "Onboarding",
      slowest_step: "Background Check",
      average_days: 3.1,
      max_days: 7.5,
      runs_affected: 4,
      bottleneck_score: 31.0,
    },
  ],
};

const STEP_DATA = {
  items: [
    {
      step_name: "Contract Review",
      completed_count: 15,
      average_completion_days: 5.2,
      median_completion_days: 4.8,
      blocked_count: 2,
      skip_rate: 0.1,
      completion_rate: 0.75,
    },
    {
      step_name: "Background Check",
      completed_count: 8,
      average_completion_days: 3.1,
      median_completion_days: 2.9,
      blocked_count: 1,
      skip_rate: 0.0,
      completion_rate: 0.89,
    },
  ],
};

const OWNER_DATA = {
  items: [
    {
      owner_role: "admin",
      assigned_steps: 20,
      completed_steps: 18,
      blocked_steps: 1,
      average_completion_days: 3.2,
      capacity_score: 90.0,
    },
    {
      owner_role: "member",
      assigned_steps: 35,
      completed_steps: 22,
      blocked_steps: 4,
      average_completion_days: 5.1,
      capacity_score: 62.9,
    },
  ],
};

const TEMPLATE_CAPACITY_DATA = {
  items: [
    {
      template_name: "Enterprise Sales",
      active_runs: 5,
      completed_runs: 12,
      average_parallel_runs: 4.2,
      average_completion_days: 14.5,
      capacity_rating: "medium",
    },
    {
      template_name: "Quick Onboarding",
      active_runs: 1,
      completed_runs: 8,
      average_parallel_runs: 1.1,
      average_completion_days: 3.2,
      capacity_rating: "low",
    },
  ],
};

// ── Mock helpers ──────────────────────────────────────────────────────────────

function setupDefaultMocks() {
  vi.mocked(useObsFlowHealth).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsBottlenecks).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsStepAnalysis).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsOwnerCapacity).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsTemplateCapacity).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
}

function setupDataMocks() {
  vi.mocked(useObsFlowHealth).mockReturnValue({
    data: { data: FLOW_HEALTH_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsBottlenecks).mockReturnValue({
    data: { data: BOTTLENECK_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsStepAnalysis).mockReturnValue({
    data: { data: STEP_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsOwnerCapacity).mockReturnValue({
    data: { data: OWNER_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useObsTemplateCapacity).mockReturnValue({
    data: { data: TEMPLATE_CAPACITY_DATA },
    isLoading: false,
    error: null,
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupDefaultMocks();
});

// ── Root component ────────────────────────────────────────────────────────────

describe("WorkflowObservabilityCenter root", () => {
  it("renders the container testid", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("workflow-observability-center")).not.toBeNull();
  });

  it("renders the page heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Workflow Observability")).not.toBeNull();
  });

  it("renders description text", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText(/Where workflows spend the most time/)).not.toBeNull();
  });

  it("passes workspaceId to all hooks", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-42" />);
    expect(vi.mocked(useObsFlowHealth)).toHaveBeenCalledWith("ws-42");
    expect(vi.mocked(useObsBottlenecks)).toHaveBeenCalledWith("ws-42");
    expect(vi.mocked(useObsStepAnalysis)).toHaveBeenCalledWith("ws-42");
    expect(vi.mocked(useObsOwnerCapacity)).toHaveBeenCalledWith("ws-42");
    expect(vi.mocked(useObsTemplateCapacity)).toHaveBeenCalledWith("ws-42");
  });
});

// ── Section headings ──────────────────────────────────────────────────────────

describe("Section headings", () => {
  it("renders Flow Health Overview heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Flow Health Overview")).not.toBeNull();
  });

  it("renders Bottleneck Rankings heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Bottleneck Rankings")).not.toBeNull();
  });

  it("renders Step Analysis heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Step Analysis")).not.toBeNull();
  });

  it("renders Owner Capacity heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Owner Capacity")).not.toBeNull();
  });

  it("renders Template Capacity heading", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Template Capacity")).not.toBeNull();
  });
});

// ── Overview section ──────────────────────────────────────────────────────────

describe("OverviewSection", () => {
  it("renders overview section testid", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("overview-section")).not.toBeNull();
  });

  it("shows placeholder when no data", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-healthy-flows").textContent).toBe("—");
  });

  it("renders healthy_flows stat card", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-healthy-flows").textContent).toBe("12");
  });

  it("renders warning_flows stat card", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-warning-flows").textContent).toBe("3");
  });

  it("renders critical_flows stat card", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-critical-flows").textContent).toBe("2");
  });

  it("renders avg_step_days formatted with d suffix", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-avg-step-days").textContent).toBe("2.5d");
  });

  it("renders avg_run_days formatted with d suffix", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-avg-run-days").textContent).toBe("8.3d");
  });

  it("renders health score", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-health-score").textContent).toBe("70.6");
  });

  it("shows loading state", () => {
    vi.mocked(useObsFlowHealth).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("overview-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useObsFlowHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("overview-error")).not.toBeNull();
  });
});

// ── Bottleneck section ────────────────────────────────────────────────────────

describe("BottleneckSection", () => {
  it("shows empty state when no data", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("bottleneck-empty")).not.toBeNull();
  });

  it("renders bottleneck table when data present", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("bottleneck-table")).not.toBeNull();
  });

  it("renders correct number of rows", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("bottleneck-row-0")).not.toBeNull();
    expect(screen.getByTestId("bottleneck-row-1")).not.toBeNull();
  });

  it("renders template name in first row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Sales Flow")).not.toBeNull();
  });

  it("renders slowest step name", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("Contract Review").length).toBeGreaterThan(0);
  });

  it("renders average_days formatted with d suffix", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("5.2d").length).toBeGreaterThan(0);
  });

  it("renders max_days in row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("12.0d")).not.toBeNull();
  });

  it("renders runs_affected count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("8").length).toBeGreaterThan(0);
  });

  it("shows loading state", () => {
    vi.mocked(useObsBottlenecks).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("bottleneck-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useObsBottlenecks).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("bottleneck-error")).not.toBeNull();
  });

  it("renders bar chart", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByTestId("barchart").length).toBeGreaterThan(0);
  });
});

// ── Step analysis section ─────────────────────────────────────────────────────

describe("StepAnalysisSection", () => {
  it("shows empty state when no data", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-analysis-empty")).not.toBeNull();
  });

  it("renders step analysis table when data present", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-analysis-table")).not.toBeNull();
  });

  it("renders step rows", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-row-0")).not.toBeNull();
    expect(screen.getByTestId("step-row-1")).not.toBeNull();
  });

  it("renders step name", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("Background Check").length).toBeGreaterThan(0);
  });

  it("renders completed_count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("15")).not.toBeNull();
  });

  it("renders blocked_count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("renders skip_rate as percentage", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("10.0%")).not.toBeNull();
  });

  it("renders completion_rate as percentage", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("75.0%")).not.toBeNull();
  });

  it("shows loading state", () => {
    vi.mocked(useObsStepAnalysis).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-analysis-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useObsStepAnalysis).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-analysis-error")).not.toBeNull();
  });
});

// ── Owner capacity section ────────────────────────────────────────────────────

describe("OwnerCapacitySection", () => {
  it("shows empty state when no data", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-capacity-empty")).not.toBeNull();
  });

  it("renders owner capacity table when data present", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-capacity-table")).not.toBeNull();
  });

  it("renders owner rows", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-row-0")).not.toBeNull();
    expect(screen.getByTestId("owner-row-1")).not.toBeNull();
  });

  it("renders owner role", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("admin")).not.toBeNull();
    expect(screen.getByText("member")).not.toBeNull();
  });

  it("renders capacity score badge for first row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-capacity-score-0")).not.toBeNull();
  });

  it("renders capacity score value", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("90.0")).not.toBeNull();
  });

  it("shows loading state", () => {
    vi.mocked(useObsOwnerCapacity).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-capacity-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useObsOwnerCapacity).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("owner-capacity-error")).not.toBeNull();
  });
});

// ── Template capacity section ─────────────────────────────────────────────────

describe("TemplateCapacitySection", () => {
  it("shows empty state when no data", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-capacity-empty")).not.toBeNull();
  });

  it("renders template capacity table when data present", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-capacity-table")).not.toBeNull();
  });

  it("renders template capacity rows", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-capacity-row-0")).not.toBeNull();
    expect(screen.getByTestId("template-capacity-row-1")).not.toBeNull();
  });

  it("renders template name", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("Enterprise Sales")).not.toBeNull();
  });

  it("renders capacity rating badge", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-rating-0")).not.toBeNull();
  });

  it("renders rating text", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("medium")).not.toBeNull();
    expect(screen.getByText("low")).not.toBeNull();
  });

  it("renders active_runs count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("5")).not.toBeNull();
  });

  it("renders line chart for template capacity", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByTestId("linechart").length).toBeGreaterThan(0);
  });

  it("shows loading state", () => {
    vi.mocked(useObsTemplateCapacity).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-capacity-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    vi.mocked(useObsTemplateCapacity).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-capacity-error")).not.toBeNull();
  });
});

// ── Integrity warning section ─────────────────────────────────────────────────

describe("IntegritySection", () => {
  it("does not render when no data integrity warning", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("integrity-section")).toBeNull();
  });

  it("renders integrity section when warning is true", () => {
    vi.mocked(useObsFlowHealth).mockReturnValue({
      data: { data: FLOW_HEALTH_WITH_WARNING },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("integrity-section")).not.toBeNull();
  });

  it("renders integrity banner when warning is true", () => {
    vi.mocked(useObsFlowHealth).mockReturnValue({
      data: { data: FLOW_HEALTH_WITH_WARNING },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("integrity-banner")).not.toBeNull();
  });

  it("banner contains expected warning text", () => {
    vi.mocked(useObsFlowHealth).mockReturnValue({
      data: { data: FLOW_HEALTH_WITH_WARNING },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText(/Data integrity warning/)).not.toBeNull();
  });

  it("does not render when data is undefined", () => {
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("integrity-banner")).toBeNull();
  });
});

// ── workspaceId propagation ───────────────────────────────────────────────────

describe("workspaceId propagation", () => {
  it("passes workspaceId to useObsFlowHealth", () => {
    render(<WorkflowObservabilityCenter workspaceId="test-ws" />);
    expect(vi.mocked(useObsFlowHealth)).toHaveBeenCalledWith("test-ws");
  });

  it("passes workspaceId to useObsBottlenecks", () => {
    render(<WorkflowObservabilityCenter workspaceId="test-ws" />);
    expect(vi.mocked(useObsBottlenecks)).toHaveBeenCalledWith("test-ws");
  });

  it("passes workspaceId to useObsStepAnalysis", () => {
    render(<WorkflowObservabilityCenter workspaceId="test-ws" />);
    expect(vi.mocked(useObsStepAnalysis)).toHaveBeenCalledWith("test-ws");
  });

  it("passes workspaceId to useObsOwnerCapacity", () => {
    render(<WorkflowObservabilityCenter workspaceId="test-ws" />);
    expect(vi.mocked(useObsOwnerCapacity)).toHaveBeenCalledWith("test-ws");
  });

  it("passes workspaceId to useObsTemplateCapacity", () => {
    render(<WorkflowObservabilityCenter workspaceId="test-ws" />);
    expect(vi.mocked(useObsTemplateCapacity)).toHaveBeenCalledWith("test-ws");
  });
});

// ── Row detail assertions ─────────────────────────────────────────────────────

describe("Bottleneck row details", () => {
  it("renders bottleneck score in second row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("31.0")).not.toBeNull();
  });

  it("renders max_days for second row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("7.5d")).not.toBeNull();
  });

  it("renders runs_affected for second row", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
  });
});

describe("Step row details", () => {
  it("renders median_completion_days with d suffix", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("4.8d")).not.toBeNull();
  });

  it("renders 0.0% for zero skip rate", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("0.0%")).not.toBeNull();
  });

  it("renders completion rate for second step", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("89.0%")).not.toBeNull();
  });
});

describe("Owner row details", () => {
  it("renders assigned steps count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("20")).not.toBeNull();
  });

  it("renders blocked steps count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });

  it("renders second row capacity score", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("62.9")).not.toBeNull();
  });

  it("renders second row assigned_steps count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("35")).not.toBeNull();
  });

  it("renders second row completed_steps count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("22")).not.toBeNull();
  });
});

describe("Template capacity row details", () => {
  it("renders completed_runs count", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getAllByText("12").length).toBeGreaterThan(0);
  });

  it("renders average_parallel_runs with 2 decimal places", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("4.20")).not.toBeNull();
  });

  it("renders average_completion_days for first template", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("14.5d")).not.toBeNull();
  });

  it("renders average_parallel_runs for second template", () => {
    setupDataMocks();
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByText("1.10")).not.toBeNull();
  });
});

// ── Section isolation (loading one section doesn't block others) ──────────────

describe("Section isolation", () => {
  it("bottleneck loading does not affect overview", () => {
    setupDataMocks();
    vi.mocked(useObsBottlenecks).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-healthy-flows").textContent).toBe("12");
    expect(screen.getByTestId("bottleneck-loading")).not.toBeNull();
  });

  it("step analysis error does not affect template capacity", () => {
    setupDataMocks();
    vi.mocked(useObsStepAnalysis).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as never);
    render(<WorkflowObservabilityCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("step-analysis-error")).not.toBeNull();
    expect(screen.getByTestId("template-capacity-table")).not.toBeNull();
  });
});
