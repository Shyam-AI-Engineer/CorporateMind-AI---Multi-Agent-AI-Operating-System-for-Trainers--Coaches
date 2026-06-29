import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { RecReviewOut } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecReview: vi.fn(),
}));

vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="review-trend-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import { useRecReview } from "@/features/analytics/api/use-analytics";
import { RecommendationReviewPanel } from "./recommendation-review-panel";

const mockUseRecReview = vi.mocked(useRecReview);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BASE_DATA: RecReviewOut = {
  generated_at: "2026-06-24T00:00:00Z",
  best_performing_type: { recommendation_type: "industry", quality_score: 90 },
  worst_performing_type: { recommendation_type: "channel", quality_score: 45 },
  most_ignored_type: { recommendation_type: "pricing", ignored_rate: 0.72 },
  most_adopted_type: { recommendation_type: "topic", adoption_rate: 0.68 },
  most_successful_type: { recommendation_type: "campaign", success_rate: 0.55 },
  calibration_summary: {
    well_calibrated: [
      { recommendation_type: "topic", calibration_delta: 2.1 },
    ],
    overconfident: [
      { recommendation_type: "channel", calibration_delta: -8.5 },
    ],
    underconfident: [
      { recommendation_type: "pricing", calibration_delta: 7.0 },
    ],
  },
  quality_trend: [
    { date: "2026-06-10", quality_score: 72.5 },
    { date: "2026-06-17", quality_score: 78.0 },
  ],
  insufficient_data: false,
};

const EMPTY_DATA: RecReviewOut = {
  generated_at: "2026-06-24T00:00:00Z",
  best_performing_type: null,
  worst_performing_type: null,
  most_ignored_type: null,
  most_adopted_type: null,
  most_successful_type: null,
  calibration_summary: {
    well_calibrated: [],
    overconfident: [],
    underconfident: [],
  },
  quality_trend: [],
  insufficient_data: false,
};

function mockLoaded(overrides: Partial<RecReviewOut> = {}) {
  mockUseRecReview.mockReturnValue({
    data: { ...BASE_DATA, ...overrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useRecReview>);
}

function mockLoading() {
  mockUseRecReview.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  } as ReturnType<typeof useRecReview>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading state ───────────────────────────────────────────────────────────

  it("shows skeleton elements while loading", () => {
    mockLoading();
    const { container } = render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const skeletons = container.querySelectorAll("[data-testid='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("does not show the root panel div while loading (no data yet)", () => {
    mockLoading();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    // rec-review-panel should not render when we have no data
    expect(screen.queryByTestId("rec-review-panel")).toBeNull();
  });

  // ── Error state ─────────────────────────────────────────────────────────────

  it("shows error message when query fails", () => {
    mockUseRecReview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useRecReview>);

    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("review-error")).not.toBeNull();
    expect(screen.getByText(/failed to load recommendation review/i)).not.toBeNull();
  });

  // ── Insufficient data ───────────────────────────────────────────────────────

  it("shows insufficient data notice when flag is true", () => {
    mockLoaded({ insufficient_data: true });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("review-insufficient")).not.toBeNull();
    expect(screen.getByText(/no recommendation history available/i)).not.toBeNull();
  });

  it("does not show rec-review-panel when insufficient_data is true", () => {
    mockLoaded({ insufficient_data: true });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.queryByTestId("rec-review-panel")).toBeNull();
  });

  // ── Root panel ──────────────────────────────────────────────────────────────

  it("renders root panel testid when data is available", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("rec-review-panel")).not.toBeNull();
  });

  // ── Top Performers ──────────────────────────────────────────────────────────

  it("renders best performing type card", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-best-type")).not.toBeNull();
    expect(screen.getByTestId("card-best-type").textContent).toMatch(/industry/i);
  });

  it("shows quality score for best type", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByText(/quality score: 90/i)).not.toBeNull();
  });

  it("renders most successful type card", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-most-successful")).not.toBeNull();
    expect(screen.getByTestId("card-most-successful").textContent).toMatch(/campaign/i);
  });

  it("shows success rate percentage for most successful type", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByText(/success rate: 55\.0%/i)).not.toBeNull();
  });

  it("renders most adopted type card", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-most-adopted")).not.toBeNull();
    expect(screen.getByTestId("card-most-adopted").textContent).toMatch(/topic/i);
  });

  it("shows adoption rate percentage for most adopted type", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByText(/adoption rate: 68\.0%/i)).not.toBeNull();
  });

  it("shows empty performer card when best_performing_type is null", () => {
    mockLoaded({ best_performing_type: null });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBeGreaterThan(0);
  });

  it("shows empty performer card when most_successful_type is null", () => {
    mockLoaded({ most_successful_type: null });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBeGreaterThan(0);
  });

  it("shows empty performer card when most_adopted_type is null", () => {
    mockLoaded({ most_adopted_type: null });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBeGreaterThan(0);
  });

  // ── Improvement Opportunities ───────────────────────────────────────────────

  it("renders worst performing type card", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-worst-type")).not.toBeNull();
    expect(screen.getByTestId("card-worst-type").textContent).toMatch(/channel/i);
  });

  it("shows quality score for worst type", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByText(/quality score: 45/i)).not.toBeNull();
  });

  it("renders most ignored type card", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-most-ignored")).not.toBeNull();
    expect(screen.getByTestId("card-most-ignored").textContent).toMatch(/pricing/i);
  });

  it("shows ignored rate percentage", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByText(/ignored rate: 72\.0%/i)).not.toBeNull();
  });

  it("shows empty card when worst_performing_type is null", () => {
    mockLoaded({ worst_performing_type: null });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBeGreaterThan(0);
  });

  it("shows empty card when most_ignored_type is null", () => {
    mockLoaded({ most_ignored_type: null });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBeGreaterThan(0);
  });

  // ── Calibration Review ──────────────────────────────────────────────────────

  it("renders calibration groups container when data is present", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-review-groups")).not.toBeNull();
  });

  it("renders well-calibrated group with badge", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("group-well-calibrated")).not.toBeNull();
    expect(screen.getByTestId("cal-badge-topic")).not.toBeNull();
  });

  it("renders overconfident group with badge and negative delta", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("group-overconfident")).not.toBeNull();
    const badge = screen.getByTestId("cal-badge-channel");
    expect(badge.textContent).toMatch(/-8\.5/);
  });

  it("renders underconfident group with badge and positive delta", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("group-underconfident")).not.toBeNull();
    const badge = screen.getByTestId("cal-badge-pricing");
    expect(badge.textContent).toMatch(/\+7\.0/);
  });

  it("shows calibration empty message when all groups are empty", () => {
    mockLoaded({
      calibration_summary: {
        well_calibrated: [],
        overconfident: [],
        underconfident: [],
      },
    });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-review-empty")).not.toBeNull();
  });

  it("shows group-level empty messages when a specific group is empty", () => {
    mockLoaded({
      calibration_summary: {
        well_calibrated: [{ recommendation_type: "topic", calibration_delta: 1 }],
        overconfident: [],
        underconfident: [],
      },
    });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    // both empty groups show their individual -empty testids
    expect(screen.getByTestId("group-overconfident-empty")).not.toBeNull();
    expect(screen.getByTestId("group-underconfident-empty")).not.toBeNull();
  });

  // ── Quality Trend ───────────────────────────────────────────────────────────

  it("renders quality trend chart when trend data exists", () => {
    mockLoaded();
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("review-trend-chart")).not.toBeNull();
  });

  it("shows empty trend message when quality_trend is empty", () => {
    mockLoaded({ quality_trend: [] });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("review-trend-empty")).not.toBeNull();
    expect(screen.getByText(/quality scores will appear here/i)).not.toBeNull();
  });

  // ── All null performers ─────────────────────────────────────────────────────

  it("shows all performer-empty cards when all performers are null", () => {
    mockLoaded({
      best_performing_type: null,
      worst_performing_type: null,
      most_ignored_type: null,
      most_adopted_type: null,
      most_successful_type: null,
    });
    render(<RecommendationReviewPanel workspaceId="ws-1" />);
    const emptyCards = screen.getAllByTestId("performer-empty");
    expect(emptyCards.length).toBe(5);
  });
});
