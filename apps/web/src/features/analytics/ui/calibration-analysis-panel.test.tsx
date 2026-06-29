import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { CalibrationReviewOut, StabilityOut } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useCalibrationReview: vi.fn(),
  useStability: vi.fn(),
}));

import {
  useCalibrationReview,
  useStability,
} from "@/features/analytics/api/use-analytics";
import { CalibrationAnalysisPanel } from "./calibration-analysis-panel";

const mockUseCalibrationReview = vi.mocked(useCalibrationReview);
const mockUseStability = vi.mocked(useStability);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BASE_CALIBRATION: CalibrationReviewOut = {
  generated_at: "2026-06-24T00:00:00Z",
  overall: {
    high_confidence_success_rate: 82.5,
    medium_confidence_success_rate: 65.0,
    low_confidence_success_rate: 40.0,
  },
  confidence_distribution: { high: 15, medium: 8, low: 4 },
  accuracy: {
    well_calibrated_count: 2,
    overconfident_count: 1,
    underconfident_count: 1,
  },
  recommendation_types: [
    {
      recommendation_type: "industry",
      predicted_confidence: 70.0,
      observed_success_rate: 72.0,
      calibration_delta: 2.0,
      calibration_severity: "calibrated",
    },
    {
      recommendation_type: "channel",
      predicted_confidence: 80.0,
      observed_success_rate: 65.0,
      calibration_delta: -15.0,
      calibration_severity: "warning",
    },
  ],
  insufficient_data: false,
};

const BASE_STABILITY: StabilityOut = {
  generated_at: "2026-06-24T00:00:00Z",
  quality_score_stability: {
    average: 74.2,
    std_dev: 3.8,
    stability_rating: "stable",
  },
  recommendation_types: [
    {
      recommendation_type: "channel",
      average_quality_score: 68.0,
      std_dev: 8.5,
      stability_rating: "volatile",
    },
    {
      recommendation_type: "industry",
      average_quality_score: 80.5,
      std_dev: 2.1,
      stability_rating: "stable",
    },
  ],
  insufficient_data: false,
};

function mockBothLoaded(
  calOverrides: Partial<CalibrationReviewOut> = {},
  stabOverrides: Partial<StabilityOut> = {},
) {
  mockUseCalibrationReview.mockReturnValue({
    data: { ...BASE_CALIBRATION, ...calOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useCalibrationReview>);

  mockUseStability.mockReturnValue({
    data: { ...BASE_STABILITY, ...stabOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useStability>);
}

function mockBothLoading() {
  mockUseCalibrationReview.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  } as ReturnType<typeof useCalibrationReview>);

  mockUseStability.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  } as ReturnType<typeof useStability>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("CalibrationAnalysisPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Root panel ──────────────────────────────────────────────────────────────

  it("renders root panel testid when data is loaded", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-analysis-panel")).not.toBeNull();
  });

  // ── Loading states ──────────────────────────────────────────────────────────

  it("renders skeleton elements while both sections loading", () => {
    mockBothLoading();
    const { container } = render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    const skeletons = container.querySelectorAll("[data-testid='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("does not show confidence distribution while calibration loading", () => {
    mockBothLoading();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.queryByTestId("card-conf-high")).toBeNull();
  });

  // ── Error states ─────────────────────────────────────────────────────────────

  it("shows calibration error when calibration query fails", () => {
    mockUseCalibrationReview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useCalibrationReview>);
    mockUseStability.mockReturnValue({
      data: BASE_STABILITY,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useStability>);

    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-error")).not.toBeNull();
    expect(screen.getByText(/failed to load calibration review/i)).not.toBeNull();
  });

  it("shows stability error when stability query fails", () => {
    mockUseCalibrationReview.mockReturnValue({
      data: BASE_CALIBRATION,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalibrationReview>);
    mockUseStability.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useStability>);

    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("stability-error")).not.toBeNull();
    expect(screen.getByText(/failed to load stability data/i)).not.toBeNull();
  });

  // ── Insufficient data ────────────────────────────────────────────────────────

  it("shows calibration insufficient notice when flag is true", () => {
    mockBothLoaded({ insufficient_data: true });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-insufficient")).not.toBeNull();
    expect(
      screen.getByText(/need at least 5 successful outcomes/i),
    ).not.toBeNull();
  });

  it("hides confidence distribution cards when calibration insufficient", () => {
    mockBothLoaded({ insufficient_data: true });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.queryByTestId("card-conf-high")).toBeNull();
  });

  it("shows stability insufficient notice when flag is true", () => {
    mockBothLoaded({}, { insufficient_data: true });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("stability-insufficient")).not.toBeNull();
    expect(
      screen.getByText(/not enough quality history to measure stability/i),
    ).not.toBeNull();
  });

  it("hides stability cards when stability insufficient", () => {
    mockBothLoaded({}, { insufficient_data: true });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.queryByTestId("card-stability-avg")).toBeNull();
  });

  // ── Section 1: Confidence Distribution ──────────────────────────────────────

  it("renders high confidence distribution card with correct count", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-conf-high")).not.toBeNull();
    expect(screen.getByTestId("card-conf-high").textContent).toContain("15");
  });

  it("renders medium confidence distribution card with correct count", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-conf-medium")).not.toBeNull();
    expect(screen.getByTestId("card-conf-medium").textContent).toContain("8");
  });

  it("renders low confidence distribution card with correct count", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-conf-low")).not.toBeNull();
    expect(screen.getByTestId("card-conf-low").textContent).toContain("4");
  });

  // ── Section 2: Calibration Accuracy ─────────────────────────────────────────

  it("renders well-calibrated count card", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-acc-well-calibrated")).not.toBeNull();
    expect(screen.getByTestId("card-acc-well-calibrated").textContent).toContain("2");
  });

  it("renders overconfident count card", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-acc-overconfident")).not.toBeNull();
    expect(screen.getByTestId("card-acc-overconfident").textContent).toContain("1");
  });

  it("renders underconfident count card", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-acc-underconfident")).not.toBeNull();
    expect(screen.getByTestId("card-acc-underconfident").textContent).toContain("1");
  });

  // ── Section 3: Confidence Performance ────────────────────────────────────────

  it("renders confidence performance table when overall rates are non-null", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("confidence-performance-table")).not.toBeNull();
  });

  it("renders per-level rows in confidence performance table", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("confidence-perf-row-high")).not.toBeNull();
    expect(screen.getByTestId("confidence-perf-row-medium")).not.toBeNull();
    expect(screen.getByTestId("confidence-perf-row-low")).not.toBeNull();
  });

  it("shows empty message when all success rates are null", () => {
    mockBothLoaded({
      overall: {
        high_confidence_success_rate: null,
        medium_confidence_success_rate: null,
        low_confidence_success_rate: null,
      },
    });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("confidence-performance-empty")).not.toBeNull();
  });

  it("shows dash for null success rate in performance table row", () => {
    mockBothLoaded({
      overall: {
        high_confidence_success_rate: 80.0,
        medium_confidence_success_rate: null,
        low_confidence_success_rate: null,
      },
    });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    const medRow = screen.getByTestId("confidence-perf-row-medium");
    expect(medRow.textContent).toContain("—");
  });

  // ── Section 4: Quality Score Stability ───────────────────────────────────────

  it("renders average quality score card", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-stability-avg")).not.toBeNull();
    expect(screen.getByTestId("card-stability-avg").textContent).toContain("74.2");
  });

  it("renders standard deviation card", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-stability-std")).not.toBeNull();
    expect(screen.getByTestId("card-stability-std").textContent).toContain("3.8");
  });

  it("renders stability rating badge", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("card-stability-rating")).not.toBeNull();
    expect(screen.getByTestId("card-stability-rating").textContent).toMatch(/stable/i);
  });

  // ── Section 5: Recommendation Stability Table ─────────────────────────────────

  it("renders stability table when types are present", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("stability-table")).not.toBeNull();
  });

  it("renders a row per stability type with correct testid", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("stability-row-channel")).not.toBeNull();
    expect(screen.getByTestId("stability-row-industry")).not.toBeNull();
  });

  it("shows average score and std dev in stability row", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    const channelRow = screen.getByTestId("stability-row-channel");
    expect(channelRow.textContent).toMatch(/68\.0/);
    expect(channelRow.textContent).toMatch(/8\.5/);
  });

  it("shows stability rating badge in stability row", () => {
    mockBothLoaded();
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    const channelRow = screen.getByTestId("stability-row-channel");
    expect(channelRow.textContent).toMatch(/volatile/i);
  });

  it("shows empty message when recommendation_types is empty", () => {
    mockBothLoaded({}, { recommendation_types: [] });
    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("stability-table-empty")).not.toBeNull();
    expect(
      screen.getByText(/not enough quality history to measure stability/i),
    ).not.toBeNull();
  });

  // ── Error + data independence ─────────────────────────────────────────────────

  it("still renders stability section when calibration fails independently", () => {
    mockUseCalibrationReview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useCalibrationReview>);
    mockUseStability.mockReturnValue({
      data: BASE_STABILITY,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useStability>);

    render(<CalibrationAnalysisPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("calibration-error")).not.toBeNull();
    // stability section still renders independently
    expect(screen.getByTestId("card-stability-avg")).not.toBeNull();
  });
});
