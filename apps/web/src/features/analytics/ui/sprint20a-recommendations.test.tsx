import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { RecommendationsOut } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecommendations: vi.fn(),
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
  useWorkspace: () => ({ workspaceId: "ws-sprint20a" }),
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
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { useRecommendations } from "@/features/analytics/api/use-analytics";
const mockRecs = vi.mocked(useRecommendations);

const WS = "ws-sprint20a";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeItem(
  type: string,
  overrides: Partial<RecommendationsOut["recommendations"][0]> = {},
): RecommendationsOut["recommendations"][0] {
  return {
    type,
    title: `Test ${type} recommendation`,
    rationale: `${type} rationale text.`,
    action: `${type} action text.`,
    supporting_data: { industry: "IT Services", win_rate: 0.42, delta_pp: 14 },
    confidence_score: 74,
    confidence_level: "high",
    evidence_strength: "strong",
    sample_size: 12,
    low_confidence: false,
    generated_at: "2026-06-23T01:00:00Z",
    ...overrides,
  };
}

function makeOut(
  recs: RecommendationsOut["recommendations"] = [],
  suppressed = 0,
): RecommendationsOut {
  return {
    workspace_id: WS,
    generated_at: "2026-06-23T01:00:00Z",
    period_days: 90,
    recommendations: recs,
    suppressed_count: suppressed,
    total: recs.length,
  };
}

// ── RecommendationCard ────────────────────────────────────────────────────────

const { RecommendationCard } = await import("./recommendation-card");

describe("RecommendationCard", () => {
  it("renders title", () => {
    render(<RecommendationCard item={makeItem("industry")} />);
    expect(screen.getByText("Test industry recommendation")).not.toBeNull();
  });

  it("renders rationale text", () => {
    render(<RecommendationCard item={makeItem("topic", { rationale: "Leadership wins more." })} />);
    expect(screen.getByText("Leadership wins more.")).not.toBeNull();
  });

  it("renders action text", () => {
    render(<RecommendationCard item={makeItem("campaign", { action: "Replicate Campaign X." })} />);
    expect(screen.getByText("Replicate Campaign X.")).not.toBeNull();
  });

  it("shows HIGH badge for high confidence", () => {
    render(<RecommendationCard item={makeItem("industry", { confidence_level: "high", confidence_score: 74 })} />);
    expect(screen.getByText(/HIGH.*74/)).not.toBeNull();
  });

  it("shows MED badge for medium confidence", () => {
    render(<RecommendationCard item={makeItem("topic", { confidence_level: "medium", confidence_score: 55 })} />);
    expect(screen.getByText(/MED.*55/)).not.toBeNull();
  });

  it("shows LOW badge for low confidence level", () => {
    render(<RecommendationCard item={makeItem("channel", { confidence_level: "low", confidence_score: 28 })} />);
    expect(screen.getByText(/LOW.*28/)).not.toBeNull();
  });

  it("shows evidence strength label", () => {
    render(<RecommendationCard item={makeItem("industry", { evidence_strength: "strong" })} />);
    expect(screen.getByText(/strong/i)).not.toBeNull();
  });

  it("shows sample size", () => {
    render(<RecommendationCard item={makeItem("industry", { sample_size: 12 })} />);
    expect(screen.getByText(/12/)).not.toBeNull();
  });

  it("shows low confidence caution when low_confidence=true", () => {
    render(<RecommendationCard item={makeItem("pricing", { low_confidence: true })} />);
    expect(screen.getByText(/limited data/i)).not.toBeNull();
  });

  it("does not show caution when low_confidence=false", () => {
    render(<RecommendationCard item={makeItem("industry", { low_confidence: false })} />);
    expect(screen.queryByText(/limited data/i)).toBeNull();
  });

  it("renders type chip", () => {
    render(<RecommendationCard item={makeItem("campaign")} />);
    expect(screen.getByText(/campaign/i)).not.toBeNull();
  });
});

// ── RecommendationsPanel ──────────────────────────────────────────────────────

const { RecommendationsPanel } = await import("./recommendations-panel");

describe("RecommendationsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows skeleton while loading", () => {
    mockRecs.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useRecommendations>);
    const { container } = render(<RecommendationsPanel workspaceId={WS} />);
    expect(container.querySelector(".h-36")).not.toBeNull();
  });

  it("shows error state when fetch fails", () => {
    mockRecs.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByText(/failed to load recommendations/i)).not.toBeNull();
  });

  it("shows empty state when no recommendations", () => {
    mockRecs.mockReturnValue({ data: makeOut([], 0), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByText(/no recommendations yet/i)).not.toBeNull();
  });

  it("renders recommendation cards when data present", () => {
    mockRecs.mockReturnValue({ data: makeOut([makeItem("industry"), makeItem("topic")]), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByTestId("recommendation-card-industry")).not.toBeNull();
    expect(screen.getByTestId("recommendation-card-topic")).not.toBeNull();
  });

  it("shows suppressed count hint when suppressed > 0", () => {
    mockRecs.mockReturnValue({ data: makeOut([makeItem("industry")], 3), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByText(/3 recommendation.*unlock/i)).not.toBeNull();
  });

  it("does not show suppressed hint when suppressed = 0", () => {
    mockRecs.mockReturnValue({ data: makeOut([makeItem("industry")], 0), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.queryByText(/unlock/i)).toBeNull();
  });

  it("shows active count in header", () => {
    mockRecs.mockReturnValue({ data: makeOut([makeItem("industry"), makeItem("channel"), makeItem("pricing")]), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByText(/3 active/i)).not.toBeNull();
  });

  it("shows unlock hints listing specific data requirements", () => {
    mockRecs.mockReturnValue({ data: makeOut([], 5), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    expect(screen.getByText(/5 recommendation.*unlock/i)).not.toBeNull();
    expect(screen.getByText(/industries.*5.*proposals/i)).not.toBeNull();
  });

  it("renders all 5 recommendation types when all present", () => {
    const types = ["industry", "topic", "pricing", "campaign", "channel"];
    mockRecs.mockReturnValue({ data: makeOut(types.map(makeItem)), isLoading: false, isError: false } as ReturnType<typeof useRecommendations>);
    render(<RecommendationsPanel workspaceId={WS} />);
    types.forEach((t) => {
      expect(screen.getByTestId(`recommendation-card-${t}`)).not.toBeNull();
    });
  });
});

// ── AnalyticsPanel — 4th tab ──────────────────────────────────────────────────

const { AnalyticsPanel } = await import("./analytics-panel");

describe("AnalyticsPanel — Sprint 20A Recommendations tab", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders four tabs including Recommendations", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByRole("tab", { name: /overview/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /campaign roi/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /intelligence/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /recommendations/i })).not.toBeNull();
  });

  it("shows RecommendationsPanel when Recommendations tab is clicked", () => {
    const { getByRole } = render(<AnalyticsPanel />);
    getByRole("tab", { name: /recommendations/i }).click();
    expect(screen.getByTestId("recommendations-panel")).not.toBeNull();
  });

  it("does not break Intelligence tab", () => {
    const { getByRole } = render(<AnalyticsPanel />);
    getByRole("tab", { name: /intelligence/i }).click();
    expect(screen.getByTestId("pricing-calibration-card")).not.toBeNull();
  });

  it("does not break Campaign ROI tab", () => {
    const { getByRole } = render(<AnalyticsPanel />);
    getByRole("tab", { name: /campaign roi/i }).click();
    expect(screen.getByTestId("campaign-roi-panel")).not.toBeNull();
  });
});
