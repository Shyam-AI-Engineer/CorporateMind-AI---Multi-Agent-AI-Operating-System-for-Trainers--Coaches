import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { LeadPipelineAnalyticsCenter } from "./lead-pipeline-analytics-center";

// ── Mock Recharts ─────────────────────────────────────────────────────────────

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="barchart">{children}</div>
  ),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

// ── Mock hooks ────────────────────────────────────────────────────────────────

vi.mock("@/features/crm/api/use-lead-pipeline-analytics", () => ({
  usePipelineSummary: vi.fn(),
  usePipelineStages: vi.fn(),
  usePipelineSources: vi.fn(),
  usePipelineIndustries: vi.fn(),
  usePipelineConversion: vi.fn(),
}));

import {
  usePipelineSummary,
  usePipelineStages,
  usePipelineSources,
  usePipelineIndustries,
  usePipelineConversion,
} from "@/features/crm/api/use-lead-pipeline-analytics";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SUMMARY = {
  total_leads: 120,
  active_leads: 85,
  qualified_leads: 20,
  proposal_leads: 10,
  won_leads: 15,
  lost_leads: 20,
  overall_conversion_rate: 12.5,
  pipeline_health_score: 75.0,
  data_integrity_warning: false,
};

const SUMMARY_WITH_WARNING = { ...SUMMARY, data_integrity_warning: true };
const SUMMARY_UNHEALTHY = { ...SUMMARY, pipeline_health_score: 35.0 };
const SUMMARY_WARNING_RANGE = { ...SUMMARY, pipeline_health_score: 55.0 };
const SUMMARY_ZERO = {
  ...SUMMARY,
  total_leads: 0,
  overall_conversion_rate: 0.0,
  pipeline_health_score: 0.0,
};

const STAGES = {
  items: [
    { stage: "discovered",        count: 40, average_days: 2.0, conversion_rate: 80.0, drop_off_rate: 20.0 },
    { stage: "engaged",           count: 32, average_days: 3.5, conversion_rate: 75.0, drop_off_rate: 25.0 },
    { stage: "meeting_scheduled", count: 20, average_days: 1.5, conversion_rate: 90.0, drop_off_rate: 10.0 },
    { stage: "meeting_completed", count: 18, average_days: 0.5, conversion_rate: 83.3, drop_off_rate: 16.7 },
    { stage: "booked",            count: 15, average_days: 0.0, conversion_rate: 0.0,  drop_off_rate: 0.0  },
    { stage: "lost",              count: 20, average_days: 0.0, conversion_rate: 0.0,  drop_off_rate: 100.0 },
  ],
};

const SOURCES = {
  items: [
    { source: "webinar",    lead_count: 50, qualified: 20, won: 10, conversion_rate: 20.0 },
    { source: "referral",   lead_count: 30, qualified: 15, won: 8,  conversion_rate: 26.7 },
    { source: "cold_email", lead_count: 40, qualified: 5,  won: 1,  conversion_rate: 2.5  },
  ],
};

const INDUSTRIES = {
  items: [
    { industry: "SaaS",         lead_count: 60, won: 10, conversion_rate: 16.7, average_pipeline_days: 14.5 },
    { industry: "Finance",      lead_count: 30, won: 5,  conversion_rate: 16.7, average_pipeline_days: 21.3 },
    { industry: "Healthcare",   lead_count: 30, won: 0,  conversion_rate: 0.0,  average_pipeline_days: 8.0  },
  ],
};

const CONVERSION = {
  qualified_to_proposal: 50.0,
  proposal_to_win: 40.0,
  overall_win_rate: 20.0,
  average_days_to_win: 14.3,
};

// ── Reset defaults ────────────────────────────────────────────────────────────

function mockAll(opts: {
  summary?: object | null;
  stages?: object | null;
  sources?: object | null;
  industries?: object | null;
  conversion?: object | null;
  loading?: boolean;
} = {}) {
  const { loading = false } = opts;
  const summaryData = opts.summary !== undefined ? opts.summary : SUMMARY;
  const stagesData = opts.stages !== undefined ? opts.stages : STAGES;
  const sourcesData = opts.sources !== undefined ? opts.sources : SOURCES;
  const industriesData = opts.industries !== undefined ? opts.industries : INDUSTRIES;
  const conversionData = opts.conversion !== undefined ? opts.conversion : CONVERSION;

  vi.mocked(usePipelineSummary).mockReturnValue({
    data: summaryData ? { data: summaryData } : undefined,
    isLoading: loading,
  } as ReturnType<typeof usePipelineSummary>);

  vi.mocked(usePipelineStages).mockReturnValue({
    data: stagesData ? { data: stagesData } : undefined,
    isLoading: loading,
  } as ReturnType<typeof usePipelineStages>);

  vi.mocked(usePipelineSources).mockReturnValue({
    data: sourcesData ? { data: sourcesData } : undefined,
    isLoading: loading,
  } as ReturnType<typeof usePipelineSources>);

  vi.mocked(usePipelineIndustries).mockReturnValue({
    data: industriesData ? { data: industriesData } : undefined,
    isLoading: loading,
  } as ReturnType<typeof usePipelineIndustries>);

  vi.mocked(usePipelineConversion).mockReturnValue({
    data: conversionData ? { data: conversionData } : undefined,
    isLoading: loading,
  } as ReturnType<typeof usePipelineConversion>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

const WS = "ws-123";

describe("LeadPipelineAnalyticsCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAll();
  });

  // Root render
  it("renders root container", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("lead-pipeline-analytics-center")).toBeDefined();
  });

  it("renders overview section", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("overview-section")).toBeDefined();
  });

  it("renders stage funnel section", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-funnel-section")).toBeDefined();
  });

  it("renders source performance section", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("source-performance-section")).toBeDefined();
  });

  it("renders industry performance section", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("industry-performance-section")).toBeDefined();
  });

  it("renders conversion metrics section", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("conversion-metrics-section")).toBeDefined();
  });

  // Summary stats
  it("renders total leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("total-leads").textContent).toBe("120");
  });

  it("renders active leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("active-leads").textContent).toBe("85");
  });

  it("renders qualified leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("qualified-leads").textContent).toBe("20");
  });

  it("renders won leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("won-leads").textContent).toBe("15");
  });

  it("renders lost leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("lost-leads").textContent).toBe("20");
  });

  it("renders proposal leads", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("proposal-leads").textContent).toBe("10");
  });

  it("renders overall conversion rate", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("conversion-rate").textContent).toBe("12.5%");
  });

  it("renders pipeline health score", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("health-score").textContent).toBe("75");
  });

  // Health label
  it("shows healthy label for high score", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("health-label").textContent).toBe("Healthy pipeline");
  });

  it("shows at risk label for low score", () => {
    mockAll({ summary: SUMMARY_UNHEALTHY });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("health-label").textContent).toBe("Pipeline at risk");
  });

  it("shows needs attention label for mid score", () => {
    mockAll({ summary: SUMMARY_WARNING_RANGE });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("health-label").textContent).toBe("Pipeline needs attention");
  });

  // Integrity warning
  it("hides integrity warning when false", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.queryByTestId("integrity-warning")).toBeNull();
  });

  it("shows integrity warning when true", () => {
    mockAll({ summary: SUMMARY_WITH_WARNING });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("integrity-warning")).toBeDefined();
  });

  // Stage table
  it("renders stage table", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-table")).toBeDefined();
  });

  it("renders discovered stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-discovered").textContent).toBe("40");
  });

  it("renders engaged stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-engaged").textContent).toBe("32");
  });

  it("renders booked stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-booked").textContent).toBe("15");
  });

  it("renders lost stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-lost").textContent).toBe("20");
  });

  it("renders bar chart for stages", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getAllByTestId("barchart").length).toBeGreaterThanOrEqual(1);
  });

  // Source table
  it("renders source table", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("source-table")).toBeDefined();
  });

  it("renders webinar source row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("source-name-webinar").textContent).toBe("webinar");
  });

  it("renders referral source row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("source-name-referral").textContent).toBe("referral");
  });

  it("renders cold_email source row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("source-name-cold_email").textContent).toBe("cold_email");
  });

  it("shows empty state for no sources", () => {
    mockAll({ sources: { items: [] } });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.queryByTestId("source-table")).toBeNull();
    expect(
      screen.getAllByText("No source data available.").length,
    ).toBeGreaterThanOrEqual(1);
  });

  // Industry table
  it("renders industry table", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("industry-table")).toBeDefined();
  });

  it("renders SaaS industry row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("industry-name-SaaS").textContent).toBe("SaaS");
  });

  it("renders Finance industry row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("industry-name-Finance").textContent).toBe("Finance");
  });

  it("renders Healthcare industry row", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("industry-name-Healthcare").textContent).toBe("Healthcare");
  });

  it("shows empty state for no industries", () => {
    mockAll({ industries: { items: [] } });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.queryByTestId("industry-table")).toBeNull();
    expect(
      screen.getAllByText("No industry data available.").length,
    ).toBeGreaterThanOrEqual(1);
  });

  // Conversion metrics
  it("renders qualified-to-proposal rate", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("qualified-to-proposal").textContent).toBe("50.0%");
  });

  it("renders proposal-to-win rate", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("proposal-to-win").textContent).toBe("40.0%");
  });

  it("renders overall win rate", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("overall-win-rate").textContent).toBe("20.0%");
  });

  it("renders average days to win", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("avg-days-to-win").textContent).toBe("14.3");
  });

  // Loading states
  it("shows loading state for all sections", () => {
    mockAll({ loading: true });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    // Summary section won't show stat cards during loading
    expect(screen.queryByTestId("total-leads")).toBeNull();
  });

  it("hides stage table when loading", () => {
    mockAll({ loading: true });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.queryByTestId("stage-table")).toBeNull();
  });

  // Null / undefined data guards
  it("renders without crashing when summary is null", () => {
    mockAll({ summary: null });
    expect(() =>
      render(<LeadPipelineAnalyticsCenter workspaceId={WS} />),
    ).not.toThrow();
  });

  it("renders without crashing when conversion is null", () => {
    mockAll({ conversion: null });
    expect(() =>
      render(<LeadPipelineAnalyticsCenter workspaceId={WS} />),
    ).not.toThrow();
  });

  it("renders responsive container for chart", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getAllByTestId("responsive-container").length).toBeGreaterThanOrEqual(1);
  });

  // Stage count - meeting_completed
  it("renders meeting_completed stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-meeting_completed").textContent).toBe("18");
  });

  // Stage count - meeting_scheduled
  it("renders meeting_scheduled stage count", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("stage-count-meeting_scheduled").textContent).toBe("20");
  });

  // Summary zero state
  it("renders zero total leads correctly", () => {
    mockAll({ summary: SUMMARY_ZERO });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("total-leads").textContent).toBe("0");
  });

  it("renders zero conversion rate correctly", () => {
    mockAll({ summary: SUMMARY_ZERO });
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getByTestId("conversion-rate").textContent).toBe("0.0%");
  });

  // Section header text
  it("renders Pipeline Overview header", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(
      screen.getAllByText("Pipeline Overview").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders Stage Funnel header", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(screen.getAllByText("Stage Funnel").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Source Performance header", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(
      screen.getAllByText("Source Performance").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders Industry Performance header", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(
      screen.getAllByText("Industry Performance").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders Conversion Metrics header", () => {
    render(<LeadPipelineAnalyticsCenter workspaceId={WS} />);
    expect(
      screen.getAllByText("Conversion Metrics").length,
    ).toBeGreaterThanOrEqual(1);
  });
});
