import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkflowEffectivenessCenter } from "./workflow-effectiveness-center";

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
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="piechart">{children}</div>
  ),
  Pie: () => null,
  Cell: () => null,
  AreaChart: () => <div data-testid="areachart" />,
  Area: () => null,
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

vi.mock("@/features/workflows/api/use-workflow-effectiveness", () => ({
  useEffectivenessSummary: vi.fn(),
  useEffectivenessTemplates: vi.fn(),
  useEffectivenessEntities: vi.fn(),
  useEffectivenessDuration: vi.fn(),
  useEffectivenessCompletion: vi.fn(),
}));

import {
  useEffectivenessSummary,
  useEffectivenessTemplates,
  useEffectivenessEntities,
  useEffectivenessDuration,
  useEffectivenessCompletion,
} from "@/features/workflows/api/use-workflow-effectiveness";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SUMMARY_DATA = {
  total_completed: 42,
  average_completion_days: 8.5,
  average_step_completion_days: 3.2,
  entity_coverage: 0.75,
  fast_completion_rate: 0.45,
  slow_completion_rate: 0.12,
  overall_effectiveness_score: 78.3,
  data_integrity_warning: false,
};

const TEMPLATES_DATA = {
  items: [
    {
      template_id: "t1",
      template_name: "Sales Flow",
      runs: 10,
      completed: 8,
      completion_rate: 0.8,
      average_duration: 5.2,
      effectiveness_score: 80.0,
    },
    {
      template_id: "t2",
      template_name: "Onboarding",
      runs: 5,
      completed: 3,
      completion_rate: 0.6,
      average_duration: 12.1,
      effectiveness_score: 60.0,
    },
  ],
};

const ENTITIES_DATA = {
  items: [
    {
      entity_type: "lead",
      workflow_count: 20,
      completion_rate: 0.9,
      average_duration: 4.5,
      effectiveness_score: 90.0,
    },
    {
      entity_type: "proposal",
      workflow_count: 10,
      completion_rate: 0.7,
      average_duration: 7.3,
      effectiveness_score: 70.0,
    },
  ],
};

const DURATION_DATA = {
  buckets: [
    { label: "0–3 days", completed: 5, completion_rate: 0.83, average_steps: 3.0, effectiveness_score: 83.0 },
    { label: "4–7 days", completed: 12, completion_rate: 0.92, average_steps: 4.1, effectiveness_score: 92.0 },
    { label: "8–14 days", completed: 8, completion_rate: 0.73, average_steps: 5.2, effectiveness_score: 73.0 },
    { label: "15–30 days", completed: 3, completion_rate: 0.50, average_steps: 6.0, effectiveness_score: 50.0 },
    { label: "30+ days", completed: 1, completion_rate: 0.25, average_steps: 7.5, effectiveness_score: 25.0 },
  ],
};

const COMPLETION_DATA = {
  items: [
    { status: "completed", count: 42, average_duration: 8.5, effectiveness_score: 100.0 },
    { status: "cancelled", count: 8, average_duration: 0.0, effectiveness_score: 0.0 },
    { status: "active", count: 15, average_duration: 5.3, effectiveness_score: 50.0 },
  ],
};

function setupDefaultMocks() {
  vi.mocked(useEffectivenessSummary).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessTemplates).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessEntities).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessDuration).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessCompletion).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  } as never);
}

function setupDataMocks() {
  vi.mocked(useEffectivenessSummary).mockReturnValue({
    data: { data: SUMMARY_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessTemplates).mockReturnValue({
    data: { data: TEMPLATES_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessEntities).mockReturnValue({
    data: { data: ENTITIES_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessDuration).mockReturnValue({
    data: { data: DURATION_DATA },
    isLoading: false,
    error: null,
  } as never);
  vi.mocked(useEffectivenessCompletion).mockReturnValue({
    data: { data: COMPLETION_DATA },
    isLoading: false,
    error: null,
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupDefaultMocks();
});

// ── Root component ────────────────────────────────────────────────────────────

describe("WorkflowEffectivenessCenter root", () => {
  it("renders the container testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("workflow-effectiveness-center")).not.toBeNull();
  });

  it("renders the page heading", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("Workflow Effectiveness")).not.toBeNull();
  });

  it("renders all six section headings", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("Overview")).not.toBeNull();
    expect(screen.getByText("Template Rankings")).not.toBeNull();
    expect(screen.getByText("Entity Effectiveness")).not.toBeNull();
    expect(screen.getByText("Duration Analysis")).not.toBeNull();
    expect(screen.getByText("Completion Analysis")).not.toBeNull();
  });
});

// ── Overview section ──────────────────────────────────────────────────────────

describe("OverviewSection", () => {
  it("renders overview section testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("overview-section")).not.toBeNull();
  });

  it("shows placeholder when no data", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const el = screen.getByTestId("stat-total-completed");
    expect(el.textContent).toBe("—");
  });

  it("renders total_completed stat card", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-total-completed").textContent).toBe("42");
  });

  it("renders avg_completion_days stat card", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-avg-completion-days").textContent).toBe("8.5d");
  });

  it("renders avg_step_days stat card", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-avg-step-days").textContent).toBe("3.2d");
  });

  it("renders entity_coverage as percentage", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-entity-coverage").textContent).toBe("75.0%");
  });

  it("renders fast_completion_rate as percentage", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-fast-rate").textContent).toBe("45.0%");
  });

  it("renders slow_completion_rate as percentage", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-slow-rate").textContent).toBe("12.0%");
  });

  it("renders overall_effectiveness_score", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("stat-overall-score").textContent).toBe("78.3");
  });
});

// ── Template Rankings section ─────────────────────────────────────────────────

describe("TemplateRankingsSection", () => {
  it("renders section testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-rankings-section")).not.toBeNull();
  });

  it("shows empty state when no data", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("No template data available.")).not.toBeNull();
  });

  it("renders table when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-rankings-table")).not.toBeNull();
  });

  it("renders correct number of rows", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-row-0")).not.toBeNull();
    expect(screen.getByTestId("template-row-1")).not.toBeNull();
  });

  it("first row shows highest effectiveness template", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row0 = screen.getByTestId("template-row-0");
    expect(row0.textContent).toContain("Sales Flow");
  });

  it("renders BarChart when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    // Multiple BarCharts may exist — at least one
    const charts = screen.getAllByTestId("barchart");
    expect(charts.length).toBeGreaterThan(0);
  });
});

// ── Entity Effectiveness section ──────────────────────────────────────────────

describe("EntityEffectivenessSection", () => {
  it("renders section testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-effectiveness-section")).not.toBeNull();
  });

  it("shows empty state when no data", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("No entity data available.")).not.toBeNull();
  });

  it("renders entity chart when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-chart")).not.toBeNull();
  });

  it("renders entity table when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-table")).not.toBeNull();
  });

  it("renders correct number of entity rows", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-row-0")).not.toBeNull();
    expect(screen.getByTestId("entity-row-1")).not.toBeNull();
  });

  it("first entity row shows lead type", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("entity-row-0");
    expect(row.textContent?.toLowerCase()).toContain("lead");
  });
});

// ── Duration Analysis section ─────────────────────────────────────────────────

describe("DurationAnalysisSection", () => {
  it("renders section testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-analysis-section")).not.toBeNull();
  });

  it("shows empty state when no data", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("No duration data available.")).not.toBeNull();
  });

  it("renders duration chart when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-chart")).not.toBeNull();
  });

  it("renders duration line chart when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-line-chart")).not.toBeNull();
    const charts = screen.getAllByTestId("linechart");
    expect(charts.length).toBeGreaterThan(0);
  });

  it("renders duration table when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-table")).not.toBeNull();
  });

  it("renders all 5 bucket rows", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    for (let i = 0; i < 5; i++) {
      expect(screen.getByTestId(`duration-row-${i}`)).not.toBeNull();
    }
  });

  it("first bucket label is 0–3 days", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("duration-row-0");
    expect(row.textContent).toContain("0–3 days");
  });

  it("last bucket label is 30+ days", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("duration-row-4");
    expect(row.textContent).toContain("30+ days");
  });
});

// ── Completion Analysis section ───────────────────────────────────────────────

describe("CompletionAnalysisSection", () => {
  it("renders section testid", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-analysis-section")).not.toBeNull();
  });

  it("shows empty state when no data", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByText("No completion data available.")).not.toBeNull();
  });

  it("renders pie chart when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-chart")).not.toBeNull();
    const charts = screen.getAllByTestId("piechart");
    expect(charts.length).toBeGreaterThan(0);
  });

  it("renders completion table when data present", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-table")).not.toBeNull();
  });

  it("renders 3 completion rows", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-row-0")).not.toBeNull();
    expect(screen.getByTestId("completion-row-1")).not.toBeNull();
    expect(screen.getByTestId("completion-row-2")).not.toBeNull();
  });

  it("completed row shows count 42", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("completion-row-0");
    expect(row.textContent).toContain("42");
  });

  it("cancelled row shows count 8", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("completion-row-1");
    expect(row.textContent).toContain("8");
  });
});

// ── Integrity Warning section ─────────────────────────────────────────────────

describe("IntegritySection", () => {
  it("does not render when data_integrity_warning is false", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("integrity-section")).toBeNull();
  });

  it("renders when data_integrity_warning is true", () => {
    vi.mocked(useEffectivenessSummary).mockReturnValue({
      data: { data: { ...SUMMARY_DATA, data_integrity_warning: true } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("integrity-section")).not.toBeNull();
  });

  it("renders integrity banner when warning is true", () => {
    vi.mocked(useEffectivenessSummary).mockReturnValue({
      data: { data: { ...SUMMARY_DATA, data_integrity_warning: true } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("integrity-banner")).not.toBeNull();
  });

  it("integrity banner contains warning text", () => {
    vi.mocked(useEffectivenessSummary).mockReturnValue({
      data: { data: { ...SUMMARY_DATA, data_integrity_warning: true } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const banner = screen.getByTestId("integrity-banner");
    expect(banner.textContent).toContain("Data Integrity Warning");
  });

  it("does not render when summary data is undefined", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("integrity-section")).toBeNull();
  });
});

// ── Loading states ────────────────────────────────────────────────────────────

describe("Loading states", () => {
  it("overview section shows loading text", () => {
    vi.mocked(useEffectivenessSummary).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("overview-section");
    expect(section.textContent).toContain("Loading");
  });

  it("template rankings section shows loading text", () => {
    vi.mocked(useEffectivenessTemplates).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("template-rankings-section");
    expect(section.textContent).toContain("Loading");
  });

  it("entity section shows loading text", () => {
    vi.mocked(useEffectivenessEntities).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("entity-effectiveness-section");
    expect(section.textContent).toContain("Loading");
  });

  it("duration section shows loading text", () => {
    vi.mocked(useEffectivenessDuration).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("duration-analysis-section");
    expect(section.textContent).toContain("Loading");
  });
});

// ── Error states ──────────────────────────────────────────────────────────────

describe("Error isolation", () => {
  it("overview error does not crash other sections", () => {
    vi.mocked(useEffectivenessSummary).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Fetch failed"),
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("overview-section")).not.toBeNull();
    expect(screen.getByTestId("template-rankings-section")).not.toBeNull();
  });

  it("template error shows error text in its section", () => {
    vi.mocked(useEffectivenessTemplates).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("oops"),
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("template-rankings-section");
    expect(section.textContent).toContain("Failed to load template data.");
  });
});

// ── workspaceId propagation ───────────────────────────────────────────────────

describe("workspaceId propagation to hooks", () => {
  it("useEffectivenessSummary receives workspaceId", () => {
    render(<WorkflowEffectivenessCenter workspaceId="my-ws" />);
    expect(vi.mocked(useEffectivenessSummary)).toHaveBeenCalledWith("my-ws");
  });

  it("useEffectivenessTemplates receives workspaceId", () => {
    render(<WorkflowEffectivenessCenter workspaceId="my-ws" />);
    expect(vi.mocked(useEffectivenessTemplates)).toHaveBeenCalledWith("my-ws");
  });

  it("useEffectivenessEntities receives workspaceId", () => {
    render(<WorkflowEffectivenessCenter workspaceId="my-ws" />);
    expect(vi.mocked(useEffectivenessEntities)).toHaveBeenCalledWith("my-ws");
  });

  it("useEffectivenessDuration receives workspaceId", () => {
    render(<WorkflowEffectivenessCenter workspaceId="my-ws" />);
    expect(vi.mocked(useEffectivenessDuration)).toHaveBeenCalledWith("my-ws");
  });

  it("useEffectivenessCompletion receives workspaceId", () => {
    render(<WorkflowEffectivenessCenter workspaceId="my-ws" />);
    expect(vi.mocked(useEffectivenessCompletion)).toHaveBeenCalledWith("my-ws");
  });
});

// ── Template row details ──────────────────────────────────────────────────────

describe("Template row details", () => {
  it("row 0 shows runs count", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-row-0").textContent).toContain("10");
  });

  it("row 0 shows completion rate", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-row-0").textContent).toContain("80.0%");
  });

  it("row 0 shows average duration", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-row-0").textContent).toContain("5.2d");
  });

  it("row 1 shows Onboarding template name", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("template-row-1").textContent).toContain("Onboarding");
  });
});

// ── Entity row details ────────────────────────────────────────────────────────

describe("Entity row details", () => {
  it("entity row 0 shows workflow count 20", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-row-0").textContent).toContain("20");
  });

  it("entity row 0 shows completion rate 90.0%", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-row-0").textContent).toContain("90.0%");
  });

  it("entity row 1 shows proposal type", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("entity-row-1").textContent?.toLowerCase()).toContain("proposal");
  });
});

// ── Completion row details ────────────────────────────────────────────────────

describe("Completion row details", () => {
  it("completion row 0 shows score 100.0", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-row-0").textContent).toContain("100.0");
  });

  it("completion row 1 shows score 0.0", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-row-1").textContent).toContain("0.0");
  });

  it("completion row 2 shows score 50.0", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("completion-row-2").textContent).toContain("50.0");
  });
});

// ── Duration row details ──────────────────────────────────────────────────────

describe("Duration row details", () => {
  it("duration row 1 shows 4–7 days label", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-row-1").textContent).toContain("4–7 days");
  });

  it("duration row shows completed count", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const row = screen.getByTestId("duration-row-1");
    expect(row.textContent).toContain("12");
  });

  it("duration row 2 shows 8–14 days label", () => {
    setupDataMocks();
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.getByTestId("duration-row-2").textContent).toContain("8–14 days");
  });
});

// ── Section heading texts ──────────────────────────────────────────────────────

describe("Section heading texts", () => {
  it("overview section heading is 'Overview'", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("overview-section");
    expect(section.textContent).toContain("Overview");
  });

  it("template rankings section heading is 'Template Rankings'", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("template-rankings-section");
    expect(section.textContent).toContain("Template Rankings");
  });

  it("entity section heading is 'Entity Effectiveness'", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("entity-effectiveness-section");
    expect(section.textContent).toContain("Entity Effectiveness");
  });

  it("duration section heading is 'Duration Analysis'", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("duration-analysis-section");
    expect(section.textContent).toContain("Duration Analysis");
  });

  it("completion section heading is 'Completion Analysis'", () => {
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("completion-analysis-section");
    expect(section.textContent).toContain("Completion Analysis");
  });
});

// ── Additional error states ────────────────────────────────────────────────────

describe("Additional error states", () => {
  it("entity error shows failed message", () => {
    vi.mocked(useEffectivenessEntities).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("network error"),
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("entity-effectiveness-section");
    expect(section.textContent).toContain("Failed to load entity data.");
  });

  it("duration error shows failed message", () => {
    vi.mocked(useEffectivenessDuration).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("network error"),
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("duration-analysis-section");
    expect(section.textContent).toContain("Failed to load duration data.");
  });

  it("completion error shows failed message", () => {
    vi.mocked(useEffectivenessCompletion).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("network error"),
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    const section = screen.getByTestId("completion-analysis-section");
    expect(section.textContent).toContain("Failed to load completion data.");
  });
});

// ── Empty states don't render data containers ─────────────────────────────────

describe("Empty states", () => {
  it("no template table when items empty", () => {
    vi.mocked(useEffectivenessTemplates).mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("template-rankings-table")).toBeNull();
  });

  it("no entity table when items empty", () => {
    vi.mocked(useEffectivenessEntities).mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("entity-table")).toBeNull();
  });

  it("no completion table when items empty", () => {
    vi.mocked(useEffectivenessCompletion).mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("completion-table")).toBeNull();
  });

  it("no duration table when buckets empty", () => {
    vi.mocked(useEffectivenessDuration).mockReturnValue({
      data: { data: { buckets: [] } },
      isLoading: false,
      error: null,
    } as never);
    render(<WorkflowEffectivenessCenter workspaceId="ws-1" />);
    expect(screen.queryByTestId("duration-table")).toBeNull();
  });
});
