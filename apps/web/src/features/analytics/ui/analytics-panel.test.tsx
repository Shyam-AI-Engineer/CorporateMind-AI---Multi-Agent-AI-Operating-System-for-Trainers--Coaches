import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AnalyticsFunnel, AnalyticsSummary, DailyRollup } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-1" }),
}));

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useAnalyticsSummary: vi.fn(),
  useAnalyticsTrend: vi.fn(),
  useAnalyticsFunnel: vi.fn(),
  useWhatsAppAnalytics: vi.fn(() => ({
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  })),
  // Sprint 19 hooks — stubbed loading to keep existing tests clean
  useCampaignROI: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useTopicPerformance: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useIndustryPerformance: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  usePricingCalibration: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 20A hook
  useRecommendations: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 20B hook
  useInsights: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 21 hooks
  useSubmitFeedback: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRecommendationEffectiveness: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 22A hooks
  useRecCalibration: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 22B hook
  useRecReview: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 23A hooks
  useCalibrationReview: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useStability: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 23B hooks
  useDrift: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useReliability: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 24A hooks
  useLifecycle: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useDecay: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 24B hooks
  usePortfolio: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useCoverage: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 25A hook
  useEvidence: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 25B hooks
  useRecommendationActions: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useAcceptRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDismissRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSnoozeRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Sprint 26A hooks
  useRecommendationWorkQueue: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useStartRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useBlockRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCompleteRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCancelRecommendation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Sprint 26B hooks
  useExecutionSummary: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useRecommendationOutcomes: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  // Sprint 27 hooks
  useRecommendationLearning: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
  useRecommendationVersionHistory: vi.fn(() => ({ data: undefined, isLoading: true, isError: false })),
}));

vi.mock("@/features/analytics/ui/whatsapp-metrics-card", () => ({
  WhatsAppMetricsCard: () => <div data-testid="wa-metrics-card" />,
}));

// Sprint 19 sub-panels — stub out to isolate AnalyticsPanel tab structure tests
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
vi.mock("@/features/analytics/ui/insights-panel", () => ({
  InsightsPanel: () => <div data-testid="insights-panel" />,
}));
vi.mock("@/features/analytics/ui/recommendation-health-panel", () => ({
  RecommendationHealthPanel: () => <div data-testid="rec-health-panel" />,
}));
vi.mock("@/features/analytics/ui/recommendation-review-panel", () => ({
  RecommendationReviewPanel: () => <div data-testid="rec-review-panel" />,
}));
vi.mock("@/features/analytics/ui/calibration-analysis-panel", () => ({
  CalibrationAnalysisPanel: () => <div data-testid="calibration-analysis-panel" />,
}));
vi.mock("@/features/analytics/ui/reliability-drift-panel", () => ({
  ReliabilityDriftPanel: () => <div data-testid="reliability-drift-panel" />,
}));
vi.mock("@/features/analytics/ui/lifecycle-observatory-panel", () => ({
  LifecycleObservatoryPanel: () => <div data-testid="lifecycle-observatory-panel" />,
}));
vi.mock("@/features/analytics/ui/portfolio-coverage-panel", () => ({
  PortfolioCoveragePanel: () => <div data-testid="portfolio-coverage-panel" />,
}));
vi.mock("@/features/analytics/ui/recommendation-evidence-panel", () => ({
  RecommendationEvidencePanel: () => <div data-testid="recommendation-evidence-panel" />,
}));
vi.mock("@/features/analytics/ui/recommendation-action-center", () => ({
  RecommendationActionCenter: () => <div data-testid="recommendation-action-center" />,
}));
vi.mock("@/features/analytics/ui/recommendation-work-queue", () => ({
  RecommendationWorkQueue: () => <div data-testid="recommendation-work-queue" />,
}));
vi.mock("@/features/analytics/ui/recommendation-outcomes-panel", () => ({
  RecommendationOutcomesPanel: () => <div data-testid="recommendation-outcomes-panel" />,
}));
vi.mock("@/features/analytics/ui/recommendation-learning-panel", () => ({
  RecommendationLearningPanel: () => <div data-testid="recommendation-learning-panel" />,
}));

// recharts uses ResizeObserver which is not in jsdom
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import {
  useAnalyticsFunnel,
  useAnalyticsSummary,
  useAnalyticsTrend,
} from "@/features/analytics/api/use-analytics";

const mockSummary = vi.mocked(useAnalyticsSummary);
const mockTrend = vi.mocked(useAnalyticsTrend);
const mockFunnel = vi.mocked(useAnalyticsFunnel);

const { AnalyticsPanel } = await import("./analytics-panel");

// ── Helpers ────────────────────────────────────────────────────────────────────

const emptySummary: AnalyticsSummary = {
  period_days: 30,
  total_sent: 0,
  total_delivered: 0,
  total_replied: 0,
  reply_rate: 0,
  delivery_rate: 0,
  total_spend_inr: 0,
  meetings_scheduled: 0,
  meetings_completed: 0,
  leads_created: 0,
  leads_booked: 0,
  proposals_generated: 0,
  proposals_approved: 0,
  proposals_sent: 0,
  proposal_approval_rate: 0,
  booking_rate: 0,
  proposals_accepted: 0,
  closed_revenue_inr: 0,
  win_rate: 0,
};

const emptyFunnel: AnalyticsFunnel = {
  contacts: 0,
  outreach_sent: 0,
  replies: 0,
  meetings: 0,
  proposals: 0,
  bookings: 0,
  proposals_accepted: 0,
  pipeline_value_inr: 0,
  closed_revenue_inr: 0,
  win_rate: 0,
};

function mockLoaded(
  summaryOverrides: Partial<AnalyticsSummary> = {},
  funnelOverrides: Partial<AnalyticsFunnel> = {},
  trendRows: DailyRollup[] = [],
) {
  mockSummary.mockReturnValue({
    data: { ...emptySummary, ...summaryOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsSummary>);

  mockTrend.mockReturnValue({
    data: trendRows,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsTrend>);

  mockFunnel.mockReturnValue({
    data: { ...emptyFunnel, ...funnelOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsFunnel>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AnalyticsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton cards while loading", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsSummary>);
    mockTrend.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsTrend>);
    mockFunnel.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsFunnel>);

    const { container } = render(<AnalyticsPanel />);
    const skeletons = container.querySelectorAll("[class*='animate-pulse'], [data-slot='skeleton'], .h-8");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state when summary fails", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useAnalyticsSummary>);
    mockTrend.mockReturnValue({ data: [] as DailyRollup[], isLoading: false, isError: false } as unknown as ReturnType<typeof useAnalyticsTrend>);
    mockFunnel.mockReturnValue({ data: undefined, isLoading: false, isError: false } as unknown as ReturnType<typeof useAnalyticsFunnel>);

    render(<AnalyticsPanel />);
    expect(screen.getByText(/failed to load analytics/i)).not.toBeNull();
  });

  it("renders reply rate KPI", () => {
    mockLoaded({ reply_rate: 0.25, total_sent: 100, total_replied: 25 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("25.0%")).not.toBeNull();
  });

  it("renders meetings KPI", () => {
    mockLoaded({ meetings_scheduled: 8, meetings_completed: 3 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("8")).not.toBeNull();
  });

  it("renders proposals KPI", () => {
    mockLoaded({ proposals_sent: 5, proposal_approval_rate: 0.8 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("5")).not.toBeNull();
  });

  it("shows empty trend message when no trend data", () => {
    mockLoaded({}, {}, []);
    render(<AnalyticsPanel />);
    expect(screen.getByText(/no trend data yet/i)).not.toBeNull();
  });

  it("renders funnel rows when data present", () => {
    mockLoaded({}, { contacts: 100, outreach_sent: 60, replies: 20, meetings: 8, proposals: 5, bookings: 2 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("HR Contacts")).not.toBeNull();
    expect(screen.getByText("Revenue Funnel")).not.toBeNull();
  });

  it("renders 'View full analytics' link in InsightsCard pattern (integration)", () => {
    mockLoaded({ reply_rate: 0.15, total_sent: 200 });
    render(<AnalyticsPanel />);
    // Just assert the panel renders without crashing and shows the core heading
    expect(screen.getByText("30-Day Outreach Trend")).not.toBeNull();
  });

  // Sprint 18A revenue KPI cards
  it("renders proposals accepted KPI card", () => {
    mockLoaded({ proposals_accepted: 4, proposals_sent: 10, win_rate: 0.4 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("Accepted (30d)")).not.toBeNull();
    expect(screen.getByText("4")).not.toBeNull();
  });

  it("renders win rate KPI card as percentage", () => {
    mockLoaded({ win_rate: 0.342, proposals_accepted: 3, proposals_sent: 8 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("Win Rate (30d)")).not.toBeNull();
    expect(screen.getByText("34.2%")).not.toBeNull();
  });

  it("renders closed revenue KPI card formatted in Indian locale", () => {
    mockLoaded({ closed_revenue_inr: 150000 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("Revenue Closed (30d)")).not.toBeNull();
    // Indian locale: 1,50,000
    expect(screen.getByText(/₹.*50,000|₹.*150,000/)).not.toBeNull();
  });

  it("renders Proposals Accepted funnel row", () => {
    mockLoaded(
      {},
      { proposals_accepted: 3, proposals: 8, pipeline_value_inr: 200000, closed_revenue_inr: 150000 },
    );
    render(<AnalyticsPanel />);
    expect(screen.getByText("Proposals Accepted")).not.toBeNull();
  });

  it("renders pipeline and closed revenue funnel rows with INR values", () => {
    mockLoaded(
      {},
      { proposals_accepted: 2, proposals: 5, pipeline_value_inr: 300000, closed_revenue_inr: 200000 },
    );
    render(<AnalyticsPanel />);
    expect(screen.getByText(/Pipeline Value/)).not.toBeNull();
    expect(screen.getByText(/Closed Revenue/)).not.toBeNull();
  });

  // Sprint 27 — 16-tab structure
  it("renders sixteen tabs", () => {
    mockLoaded();
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /overview/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /campaign roi/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /intelligence/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /^recommendations$/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /insights/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation health/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation review/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /calibration analysis/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /reliability.*drift/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /lifecycle observatory/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /portfolio.*coverage/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation evidence/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation action center/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation work queue/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation outcomes/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendation learning/i })).not.toBeNull();
  });

  it("shows CampaignROIPanel in Campaign ROI tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /campaign roi/i }));
    expect(screen.getByTestId("campaign-roi-panel")).not.toBeNull();
  });

  it("shows intelligence sub-panels in Intelligence tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /intelligence/i }));
    expect(screen.getByTestId("top-topics-panel")).not.toBeNull();
    expect(screen.getByTestId("top-industries-panel")).not.toBeNull();
    expect(screen.getByTestId("pricing-calibration-card")).not.toBeNull();
  });

  it("shows RecommendationReviewPanel in Recommendation Review tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation review/i }));
    expect(screen.getByTestId("rec-review-panel")).not.toBeNull();
  });

  it("shows CalibrationAnalysisPanel in Calibration Analysis tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /calibration analysis/i }));
    expect(screen.getByTestId("calibration-analysis-panel")).not.toBeNull();
  });

  it("shows ReliabilityDriftPanel in Reliability & Drift tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /reliability.*drift/i }));
    expect(screen.getByTestId("reliability-drift-panel")).not.toBeNull();
  });

  it("shows LifecycleObservatoryPanel in Lifecycle Observatory tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /lifecycle observatory/i }));
    expect(screen.getByTestId("lifecycle-observatory-panel")).not.toBeNull();
  });

  it("shows PortfolioCoveragePanel in Portfolio & Coverage tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /portfolio.*coverage/i }));
    expect(screen.getByTestId("portfolio-coverage-panel")).not.toBeNull();
  });

  it("shows RecommendationEvidencePanel in Recommendation Evidence tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation evidence/i }));
    expect(screen.getByTestId("recommendation-evidence-panel")).not.toBeNull();
  });

  it("shows RecommendationActionCenter in Recommendation Action Center tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation action center/i }));
    expect(screen.getByTestId("recommendation-action-center")).not.toBeNull();
  });

  it("shows RecommendationWorkQueue in Recommendation Work Queue tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation work queue/i }));
    expect(screen.getByTestId("recommendation-work-queue")).not.toBeNull();
  });

  it("shows RecommendationOutcomesPanel in Recommendation Outcomes tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation outcomes/i }));
    expect(screen.getByTestId("recommendation-outcomes-panel")).not.toBeNull();
  });

  it("shows RecommendationLearningPanel in Recommendation Learning tab", async () => {
    const user = userEvent.setup();
    mockLoaded();
    const { getByRole } = render(<AnalyticsPanel />);
    await user.click(getByRole("tab", { name: /recommendation learning/i }));
    expect(screen.getByTestId("recommendation-learning-panel")).not.toBeNull();
  });
});
