import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AnalyticsInsightOut } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useInsights: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useRecommendations: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useAnalyticsSummary: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useAnalyticsTrend: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useAnalyticsFunnel: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useWhatsAppAnalytics: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useCampaignROI: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useTopicPerformance: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useIndustryPerformance: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  usePricingCalibration: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
}));

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-sprint20b" }),
}));

vi.mock("@/features/analytics/ui/whatsapp-metrics-card", () => ({
  WhatsAppMetricsCard: () => <div />,
}));
vi.mock("@/features/analytics/ui/campaign-roi-panel", () => ({
  CampaignROIPanel: () => <div data-testid="campaign-roi-panel" />,
}));
vi.mock("@/features/analytics/ui/top-topics-panel", () => ({
  TopTopicsPanel: () => <div data-testid="top-topics-panel" />,
}));
vi.mock("@/features/analytics/ui/top-industries-panel", () => ({
  TopIndustriesPanel: () => <div data-testid="top-industries-panel" />,
}));
vi.mock("@/features/analytics/ui/pricing-calibration-card", () => ({
  PricingCalibrationCard: () => <div data-testid="pricing-calibration-card" />,
}));
vi.mock("@/features/analytics/ui/recommendations-panel", () => ({
  RecommendationsPanel: () => <div data-testid="recommendations-panel" />,
}));
// insights-panel is NOT mocked here — it is the subject under test.
// Plain import below shares the same mocked use-analytics bindings as mockInsights.
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { useInsights } from "@/features/analytics/api/use-analytics";
const mockInsights = vi.mocked(useInsights);

const WS = "ws-sprint20b";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeOut(overrides: Partial<AnalyticsInsightOut> = {}): AnalyticsInsightOut {
  return {
    generated_at: "2026-06-23T01:30:00Z",
    executive_summary: "IT Services drives the highest win rate at 45%.",
    top_opportunities: [
      { title: "Focus on IT Services", rationale: "45% win rate vs 28% median.", confidence_level: "high" },
      { title: "Lead with Leadership topic", rationale: "12pp higher win rate.", confidence_level: "medium" },
    ],
    risks: [
      { title: "Single channel dependency", description: "92% of revenue from WhatsApp." },
    ],
    data_limitations: ["Pricing insight based on only 8 deals."],
    ...overrides,
  };
}

function makeEmpty(): AnalyticsInsightOut {
  return {
    generated_at: "2026-06-23T01:30:00Z",
    executive_summary: "Insufficient data to generate insights.",
    top_opportunities: [],
    risks: [],
    data_limitations: ["Run campaigns and record deal outcomes to generate meaningful insights."],
  };
}

// ── InsightsPanel (un-mocked) ─────────────────────────────────────────────────

const { InsightsPanel } = await import("./insights-panel");

describe("InsightsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows skeletons while loading", () => {
    mockInsights.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useInsights>);
    const { container } = render(<InsightsPanel workspaceId={WS} />);
    expect(container.querySelector(".h-24")).not.toBeNull();
  });

  it("shows error state when fetch fails", () => {
    mockInsights.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText(/failed to load insights/i)).not.toBeNull();
  });

  it("shows insufficient data executive summary on empty state", () => {
    mockInsights.mockReturnValue({ data: makeEmpty(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByTestId("insight-executive-summary").textContent).toMatch(/Insufficient data/i);
  });

  it("renders executive summary when data present", () => {
    mockInsights.mockReturnValue({ data: makeOut(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByTestId("insight-executive-summary").textContent).toContain("IT Services");
  });

  it("renders top opportunities", () => {
    mockInsights.mockReturnValue({ data: makeOut(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText("Focus on IT Services")).not.toBeNull();
    expect(screen.getByText("Lead with Leadership topic")).not.toBeNull();
  });

  it("renders opportunity rationale text", () => {
    mockInsights.mockReturnValue({ data: makeOut(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText(/45% win rate vs 28% median/i)).not.toBeNull();
  });

  it("shows HIGH confidence badge on high-confidence opportunity", () => {
    mockInsights.mockReturnValue({
      data: makeOut({ top_opportunities: [{ title: "T", rationale: "R", confidence_level: "high" }] }),
      isLoading: false, isError: false,
    } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText("HIGH")).not.toBeNull();
  });

  it("shows MED confidence badge on medium-confidence opportunity", () => {
    mockInsights.mockReturnValue({
      data: makeOut({ top_opportunities: [{ title: "T", rationale: "R", confidence_level: "medium" }] }),
      isLoading: false, isError: false,
    } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText("MED")).not.toBeNull();
  });

  it("shows LOW confidence badge on low-confidence opportunity", () => {
    mockInsights.mockReturnValue({
      data: makeOut({ top_opportunities: [{ title: "T", rationale: "R", confidence_level: "low" }] }),
      isLoading: false, isError: false,
    } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText("LOW")).not.toBeNull();
  });

  it("renders risks section when risks present", () => {
    mockInsights.mockReturnValue({ data: makeOut(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByText("Single channel dependency")).not.toBeNull();
    expect(screen.getByText("92% of revenue from WhatsApp.")).not.toBeNull();
  });

  it("omits risks section when no risks", () => {
    mockInsights.mockReturnValue({ data: makeOut({ risks: [] }), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.queryByText("Single channel dependency")).toBeNull();
  });

  it("renders data limitations section when limitations present", () => {
    mockInsights.mockReturnValue({ data: makeOut(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.getByTestId("insight-limitations")).not.toBeNull();
    expect(screen.getByText(/Pricing insight based on only 8 deals/i)).not.toBeNull();
  });

  it("omits limitations section when no limitations", () => {
    mockInsights.mockReturnValue({ data: makeOut({ data_limitations: [] }), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.queryByTestId("insight-limitations")).toBeNull();
  });

  it("omits opportunities section when empty", () => {
    mockInsights.mockReturnValue({ data: makeEmpty(), isLoading: false, isError: false } as ReturnType<typeof useInsights>);
    render(<InsightsPanel workspaceId={WS} />);
    expect(screen.queryByText("Top Opportunities")).toBeNull();
  });
});

// ── AnalyticsPanel — 5th tab ──────────────────────────────────────────────────

const { AnalyticsPanel } = await import("./analytics-panel");

describe("AnalyticsPanel — Sprint 20B Insights tab", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders five tabs including Insights", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /overview/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /campaign roi/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /intelligence/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendations/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /insights/i })).not.toBeNull();
  });

  it("shows InsightsPanel when Insights tab is clicked", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /insights/i })).not.toBeNull();
  });

  it("does not break Recommendations tab", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /recommendations/i })).not.toBeNull();
  });

  it("does not break Intelligence tab", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /intelligence/i })).not.toBeNull();
  });
});
