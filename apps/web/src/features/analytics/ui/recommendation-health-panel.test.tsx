import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type {
  RecCalibrationOut,
  RecEffectivenessOut,
} from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecommendationEffectiveness: vi.fn(),
  useRecCalibration: vi.fn(),
}));

// recharts components are not available in jsdom
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import {
  useRecommendationEffectiveness,
  useRecCalibration,
} from "@/features/analytics/api/use-analytics";
import { RecommendationHealthPanel } from "./recommendation-health-panel";

const mockEffectiveness = vi.mocked(useRecommendationEffectiveness);
const mockCalibration = vi.mocked(useRecCalibration);

const WS = "ws-test-123";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeEffectivenessData(overrides: Partial<RecEffectivenessOut> = {}): RecEffectivenessOut {
  return {
    generated_at: "2026-06-23T10:00:00Z",
    summary: {
      recommendations_generated: 20,
      recommendations_acted: 8,
      recommendations_successful: 5,
      adoption_rate: 0.4,
      success_rate: 0.625,
    },
    by_type: [
      {
        recommendation_type: "industry",
        generated: 10,
        acted: 4,
        successful: 3,
        adoption_rate: 0.4,
        success_rate: 0.75,
        quality_score: 80,
      },
      {
        recommendation_type: "channel",
        generated: 10,
        acted: 4,
        successful: 2,
        adoption_rate: 0.4,
        success_rate: 0.5,
        quality_score: null, // low confidence
      },
    ],
    quality_trend: [
      {
        score_date: "2026-06-10",
        rec_type: "industry",
        quality_score: 70,
        adoption_rate: 0.3,
        success_rate: 0.6,
      },
      {
        score_date: "2026-06-20",
        rec_type: "industry",
        quality_score: 80,
        adoption_rate: 0.4,
        success_rate: 0.75,
      },
    ],
    ...overrides,
  };
}

function makeCalibrationData(overrides: Partial<RecCalibrationOut> = {}): RecCalibrationOut {
  return {
    generated_at: "2026-06-23T10:00:00Z",
    overall: {
      high_confidence_success_rate: 82.0,
      medium_confidence_success_rate: 55.0,
      low_confidence_success_rate: null,
    },
    recommendation_types: [
      {
        recommendation_type: "industry",
        predicted_confidence: 75.0,
        observed_success_rate: 80.0,
        calibration_delta: 5.0,
      },
      {
        recommendation_type: "channel",
        predicted_confidence: 80.0,
        observed_success_rate: 60.0,
        calibration_delta: -20.0,
      },
    ],
    insufficient_data: false,
    minimum_acted_recommendations: 5,
    ...overrides,
  };
}

function loadingState() {
  return { data: undefined, isLoading: true, isError: false };
}

function errorState() {
  return { data: undefined, isLoading: false, isError: true };
}

function dataState<T>(data: T) {
  return { data, isLoading: false, isError: false };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationHealthPanel", () => {
  beforeEach(() => {
    mockEffectiveness.mockReturnValue(loadingState() as ReturnType<typeof useRecommendationEffectiveness>);
    mockCalibration.mockReturnValue(loadingState() as ReturnType<typeof useRecCalibration>);
  });

  // ── Panel root ──────────────────────────────────────────────────────────────

  it("renders the root panel container", () => {
    render(<RecommendationHealthPanel workspaceId={WS} />);
    expect(screen.getByTestId("rec-health-panel")).toBeInTheDocument();
  });

  // ── Loading states ──────────────────────────────────────────────────────────

  it("shows skeletons while effectiveness data is loading", () => {
    render(<RecommendationHealthPanel workspaceId={WS} />);
    const skeletons = screen.getAllByTestId("skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  // ── Effectiveness summary cards ─────────────────────────────────────────────

  describe("Effectiveness Summary", () => {
    beforeEach(() => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData()) as ReturnType<typeof useRecommendationEffectiveness>
      );
      mockCalibration.mockReturnValue(loadingState() as ReturnType<typeof useRecCalibration>);
    });

    it("shows Generated card with correct value", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("card-generated")).toHaveTextContent("20");
    });

    it("shows Adopted card with correct value", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("card-adopted")).toHaveTextContent("8");
    });

    it("shows Successful card with correct value", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("card-successful")).toHaveTextContent("5");
    });

    it("shows Adoption Rate as percentage", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("card-adoption-rate")).toHaveTextContent("40.0%");
    });

    it("shows Success Rate as percentage", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("card-success-rate")).toHaveTextContent("62.5%");
    });

    it("shows error state when effectiveness fails", () => {
      mockEffectiveness.mockReturnValue(errorState() as ReturnType<typeof useRecommendationEffectiveness>);
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("effectiveness-error")).toBeInTheDocument();
    });
  });

  // ── Type performance table ──────────────────────────────────────────────────

  describe("Type Performance Table", () => {
    beforeEach(() => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData()) as ReturnType<typeof useRecommendationEffectiveness>
      );
    });

    it("renders a row per recommendation type", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("type-row-industry")).toBeInTheDocument();
      expect(screen.getByTestId("type-row-channel")).toBeInTheDocument();
    });

    it("shows Building for low confidence quality score", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      const row = screen.getByTestId("type-row-channel");
      expect(row).toHaveTextContent("Building");
    });

    it("shows numeric quality score badge when not low confidence", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      const row = screen.getByTestId("type-row-industry");
      expect(row).toHaveTextContent("80");
    });

    it("shows empty state when by_type is empty", () => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData({ by_type: [] })) as ReturnType<typeof useRecommendationEffectiveness>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("type-table-empty")).toBeInTheDocument();
    });

    it("empty state message references outcomes", () => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData({ by_type: [] })) as ReturnType<typeof useRecommendationEffectiveness>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("type-table-empty")).toHaveTextContent(
        "No recommendation outcomes recorded yet."
      );
    });
  });

  // ── Calibration table ───────────────────────────────────────────────────────

  describe("Calibration Table", () => {
    beforeEach(() => {
      mockCalibration.mockReturnValue(
        dataState(makeCalibrationData()) as ReturnType<typeof useRecCalibration>
      );
    });

    it("renders a row per calibration type", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("cal-row-industry")).toBeInTheDocument();
      expect(screen.getByTestId("cal-row-channel")).toBeInTheDocument();
    });

    it("shows positive delta with + prefix", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      const cell = screen.getByTestId("cal-delta-industry");
      expect(cell).toHaveTextContent("+5.0");
    });

    it("shows negative delta without + prefix", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      const cell = screen.getByTestId("cal-delta-channel");
      expect(cell).toHaveTextContent("-20.0");
    });

    it("shows Calibrated label for |delta| < 5", () => {
      const data = makeCalibrationData({
        recommendation_types: [
          {
            recommendation_type: "industry",
            predicted_confidence: 70.0,
            observed_success_rate: 72.0,
            calibration_delta: 2.0, // |2| < 5
          },
        ],
      });
      mockCalibration.mockReturnValue(dataState(data) as ReturnType<typeof useRecCalibration>);
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("cal-delta-industry")).toHaveTextContent("Calibrated");
    });

    it("shows Warning label for delta in 5–15 range", () => {
      const data = makeCalibrationData({
        recommendation_types: [
          {
            recommendation_type: "industry",
            predicted_confidence: 70.0,
            observed_success_rate: 80.0,
            calibration_delta: 10.0, // 5 <= |10| <= 15
          },
        ],
      });
      mockCalibration.mockReturnValue(dataState(data) as ReturnType<typeof useRecCalibration>);
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("cal-delta-industry")).toHaveTextContent("Warning");
    });

    it("shows Attention label for |delta| > 15", () => {
      const data = makeCalibrationData({
        recommendation_types: [
          {
            recommendation_type: "channel",
            predicted_confidence: 80.0,
            observed_success_rate: 60.0,
            calibration_delta: -20.0, // |20| > 15
          },
        ],
      });
      mockCalibration.mockReturnValue(dataState(data) as ReturnType<typeof useRecCalibration>);
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("cal-delta-channel")).toHaveTextContent("Attention");
    });

    it("shows insufficient data empty state when insufficient_data=true", () => {
      mockCalibration.mockReturnValue(
        dataState(makeCalibrationData({ insufficient_data: true })) as ReturnType<typeof useRecCalibration>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("calibration-empty")).toBeInTheDocument();
    });

    it("empty state references the minimum threshold", () => {
      mockCalibration.mockReturnValue(
        dataState(
          makeCalibrationData({ insufficient_data: true, minimum_acted_recommendations: 5 })
        ) as ReturnType<typeof useRecCalibration>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("calibration-empty")).toHaveTextContent("5");
    });

    it("shows legend when data is sufficient", () => {
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("calibration-legend")).toBeInTheDocument();
    });

    it("hides legend when insufficient_data=true", () => {
      mockCalibration.mockReturnValue(
        dataState(makeCalibrationData({ insufficient_data: true })) as ReturnType<typeof useRecCalibration>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.queryByTestId("calibration-legend")).not.toBeInTheDocument();
    });
  });

  // ── Quality trend chart ─────────────────────────────────────────────────────

  describe("Quality Score Trend", () => {
    it("shows empty state when trend is empty", () => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData({ quality_trend: [] })) as ReturnType<typeof useRecommendationEffectiveness>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.getByTestId("trend-empty")).toBeInTheDocument();
    });

    it("renders chart when trend data exists", () => {
      mockEffectiveness.mockReturnValue(
        dataState(makeEffectivenessData()) as ReturnType<typeof useRecommendationEffectiveness>
      );
      render(<RecommendationHealthPanel workspaceId={WS} />);
      expect(screen.queryByTestId("trend-empty")).not.toBeInTheDocument();
    });
  });
});
