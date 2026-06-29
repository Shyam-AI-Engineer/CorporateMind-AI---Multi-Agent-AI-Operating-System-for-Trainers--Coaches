import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type {
  LearningOut,
  LearningVersionOut,
  VersionHistoryOut,
} from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecommendationLearning: vi.fn(),
  useRecommendationVersionHistory: vi.fn(),
}));

vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import {
  useRecommendationLearning,
  useRecommendationVersionHistory,
} from "@/features/analytics/api/use-analytics";
import { RecommendationLearningPanel } from "./recommendation-learning-panel";

const mockLearning = vi.mocked(useRecommendationLearning);
const mockHistory = vi.mocked(useRecommendationVersionHistory);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS_ID = "ws-sprint27";

function makeVersion(
  version: string,
  overrides: Partial<LearningVersionOut> = {},
): LearningVersionOut {
  return {
    version,
    first_seen: version,
    last_seen: version,
    recommendations_generated: 5,
    acted: 3,
    completed: 2,
    successful: 2,
    avg_confidence: 70.0,
    quality_score: 80.0,
    ...overrides,
  };
}

const VERSION_NEW = makeVersion("2026-06-20");
const VERSION_OLD = makeVersion("2026-06-13", { avg_confidence: 65.0, quality_score: 75.0 });

const twoVersionHistory: VersionHistoryOut = {
  versions: [VERSION_NEW, VERSION_OLD],
  total_versions: 2,
  insufficient_data: false,
};

const emptyHistory: VersionHistoryOut = {
  versions: [],
  total_versions: 0,
  insufficient_data: true,
};

const insufficientHistory: VersionHistoryOut = {
  versions: [VERSION_NEW],
  total_versions: 1,
  insufficient_data: true,
};

const twoVersionLearning: LearningOut = {
  generated_at: "2026-06-27T00:00:00Z",
  current_version: "2026-06-20",
  previous_version: "2026-06-13",
  comparison: {
    quality_delta: 5.0,
    success_delta: 10.0,
    confidence_delta: 5.0,
    adoption_delta: 8.0,
    execution_delta: 3.0,
  },
  summary: {
    lines: [
      "Quality improved by 5.0 points.",
      "Adoption increased by 8.0%.",
    ],
  },
  insufficient_data: false,
};

const insufficientLearning: LearningOut = {
  generated_at: "2026-06-27T00:00:00Z",
  current_version: "2026-06-20",
  previous_version: null,
  comparison: null,
  summary: { lines: ["Insufficient data to compare versions."] },
  insufficient_data: true,
};

const emptyLearning: LearningOut = {
  generated_at: "2026-06-27T00:00:00Z",
  current_version: null,
  previous_version: null,
  comparison: null,
  summary: { lines: [] },
  insufficient_data: true,
};

function mockLoaded(
  learningData: LearningOut = twoVersionLearning,
  historyData: VersionHistoryOut = twoVersionHistory,
) {
  mockLearning.mockReturnValue({
    data: learningData,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useRecommendationLearning>);

  mockHistory.mockReturnValue({
    data: historyData,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useRecommendationVersionHistory>);
}

function mockLoading() {
  mockLearning.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  } as ReturnType<typeof useRecommendationLearning>);

  mockHistory.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  } as ReturnType<typeof useRecommendationVersionHistory>);
}

function mockError() {
  mockLearning.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
  } as ReturnType<typeof useRecommendationLearning>);

  mockHistory.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
  } as ReturnType<typeof useRecommendationVersionHistory>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationLearningPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it("shows skeleton while loading", () => {
    mockLoading();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("learning-skeleton")).not.toBeNull();
  });

  it("does not show main panel while loading", () => {
    mockLoading();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("recommendation-learning-panel")).toBeNull();
  });

  it("skeleton disappears when data loaded", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("learning-skeleton")).toBeNull();
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it("shows error state when query fails", () => {
    mockError();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("learning-error")).not.toBeNull();
  });

  it("shows error message text", () => {
    mockError();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByText(/failed to load recommendation learning/i)).not.toBeNull();
  });

  it("does not show panel when in error state", () => {
    mockError();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("recommendation-learning-panel")).toBeNull();
  });

  // ── Empty / no-history state ──────────────────────────────────────────────

  it("shows no-history state when 0 versions", () => {
    mockLoaded(emptyLearning, emptyHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("learning-no-history")).not.toBeNull();
  });

  it("shows descriptive message in no-history state", () => {
    mockLoaded(emptyLearning, emptyHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("learning-no-history-message")).not.toBeNull();
    expect(
      screen.getByText(/no recommendation versions recorded yet/i),
    ).not.toBeNull();
  });

  it("does not show main panel in no-history state", () => {
    mockLoaded(emptyLearning, emptyHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("recommendation-learning-panel")).toBeNull();
  });

  // ── Happy path — root panel ───────────────────────────────────────────────

  it("renders main panel when 2+ versions exist", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("recommendation-learning-panel")).not.toBeNull();
  });

  it("renders 4 sections in happy path", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("comparison-section")).not.toBeNull();
    expect(screen.getByTestId("timeline-section")).not.toBeNull();
    expect(screen.getByTestId("trend-section")).not.toBeNull();
    expect(screen.getByTestId("summary-section")).not.toBeNull();
  });

  // ── Section 1: Version Comparison ────────────────────────────────────────

  it("shows current version card", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("card-current-version")).not.toBeNull();
  });

  it("shows previous version card", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("card-previous-version")).not.toBeNull();
  });

  it("displays current version value", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-current-version");
    expect(within(card).getByText("2026-06-20")).not.toBeNull();
  });

  it("displays previous version value", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-previous-version");
    expect(within(card).getByText("2026-06-13")).not.toBeNull();
  });

  it("shows quality delta card", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("card-quality-delta")).not.toBeNull();
  });

  it("shows positive quality delta with + prefix", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-quality-delta");
    expect(within(card).getByText("+5.0 pts")).not.toBeNull();
  });

  it("shows success delta card", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("card-success-delta")).not.toBeNull();
  });

  it("shows success delta with % unit", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-success-delta");
    expect(within(card).getByText("+10.0 %")).not.toBeNull();
  });

  it("shows confidence delta card", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("card-confidence-delta")).not.toBeNull();
  });

  it("shows dash for null delta", () => {
    const learningNullComparison: LearningOut = {
      ...twoVersionLearning,
      comparison: {
        quality_delta: null,
        success_delta: null,
        confidence_delta: null,
        adoption_delta: null,
        execution_delta: null,
      },
    };
    mockLoaded(learningNullComparison, twoVersionHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-quality-delta");
    expect(within(card).getByText("—")).not.toBeNull();
  });

  // ── Section 2: Version Timeline ───────────────────────────────────────────

  it("shows version table with two rows", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("version-table")).not.toBeNull();
  });

  it("renders a row for each version", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("version-row-2026-06-20")).not.toBeNull();
    expect(screen.getByTestId("version-row-2026-06-13")).not.toBeNull();
  });

  it("shows timeline-empty when versions list is empty", () => {
    const oneVersionLearning: LearningOut = {
      ...insufficientLearning,
      insufficient_data: false,
    };
    const noVersionsHistory: VersionHistoryOut = {
      versions: [],
      total_versions: 0,
      insufficient_data: false,
    };
    mockLoaded(oneVersionLearning, noVersionsHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("timeline-empty")).not.toBeNull();
  });

  it("version row displays generated count", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const row = screen.getByTestId("version-row-2026-06-20");
    expect(within(row).getByText("5")).not.toBeNull();
  });

  // ── Section 3: Improvement Trend ─────────────────────────────────────────

  it("shows trend chart when 2+ versions", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("trend-chart")).not.toBeNull();
  });

  it("shows trend-insufficient when fewer than 2 versions in history", () => {
    mockLoaded(insufficientLearning, insufficientHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("trend-insufficient")).not.toBeNull();
  });

  it("trend-insufficient message mentions 2 versions required", () => {
    mockLoaded(insufficientLearning, insufficientHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(
      screen.getByText(/at least 2 versions required/i),
    ).not.toBeNull();
  });

  it("trend chart is not shown when only 1 version", () => {
    mockLoaded(insufficientLearning, insufficientHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("trend-chart")).toBeNull();
  });

  // ── Section 4: Change Summary ─────────────────────────────────────────────

  it("shows summary lines when lines present", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("summary-lines")).not.toBeNull();
  });

  it("renders each summary line with correct testid", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("summary-line-0")).not.toBeNull();
    expect(screen.getByTestId("summary-line-1")).not.toBeNull();
  });

  it("shows summary line content", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByText("Quality improved by 5.0 points.")).not.toBeNull();
  });

  it("shows summary-empty when lines is empty array", () => {
    const noLines: LearningOut = {
      ...twoVersionLearning,
      summary: { lines: [] },
    };
    mockLoaded(noLines, twoVersionHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.getByTestId("summary-empty")).not.toBeNull();
  });

  it("does not show summary-lines when no lines", () => {
    const noLines: LearningOut = {
      ...twoVersionLearning,
      summary: { lines: [] },
    };
    mockLoaded(noLines, twoVersionHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(screen.queryByTestId("summary-lines")).toBeNull();
  });

  // ── Negative delta formatting ─────────────────────────────────────────────

  it("shows negative delta without + prefix", () => {
    const negLearning: LearningOut = {
      ...twoVersionLearning,
      comparison: {
        ...twoVersionLearning.comparison!,
        quality_delta: -5.0,
      },
    };
    mockLoaded(negLearning, twoVersionHistory);
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    const card = screen.getByTestId("card-quality-delta");
    expect(within(card).getByText("-5.0 pts")).not.toBeNull();
  });

  // ── workspaceId forwarding ────────────────────────────────────────────────

  it("passes workspaceId to useRecommendationLearning", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(mockLearning).toHaveBeenCalledWith(WS_ID);
  });

  it("passes workspaceId to useRecommendationVersionHistory", () => {
    mockLoaded();
    render(<RecommendationLearningPanel workspaceId={WS_ID} />);
    expect(mockHistory).toHaveBeenCalledWith(WS_ID);
  });
});
