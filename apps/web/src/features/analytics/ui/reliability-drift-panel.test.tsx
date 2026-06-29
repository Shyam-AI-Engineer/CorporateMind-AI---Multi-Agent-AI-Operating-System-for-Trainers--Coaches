import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ── Hook mocks ────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useDrift: vi.fn(),
  useReliability: vi.fn(),
}));

import {
  useDrift,
  useReliability,
} from "@/features/analytics/api/use-analytics";
import type { DriftOut, ReliabilityOut } from "@/features/analytics/types";
import { ReliabilityDriftPanel } from "./reliability-drift-panel";

const mockUseDrift = vi.mocked(useDrift);
const mockUseReliability = vi.mocked(useReliability);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeTrend = (
  current = 70,
  previous = 60,
  direction = "improving",
) => ({
  current,
  previous,
  change: +(current - previous).toFixed(2),
  direction,
});

const fullDrift: DriftOut = {
  generated_at: "2026-06-24T10:00:00Z",
  overall: {
    quality_score: makeTrend(75, 60, "improving"),
    adoption_rate: makeTrend(45, 45, "stable"),
    success_rate: makeTrend(30, 50, "declining"),
  },
  by_type: [
    {
      recommendation_type: "channel",
      quality_score: makeTrend(80, 65, "improving"),
    },
    {
      recommendation_type: "topic",
      quality_score: makeTrend(55, 60, "declining"),
    },
  ],
  insufficient_data: false,
};

const fullReliability: ReliabilityOut = {
  generated_at: "2026-06-24T10:00:00Z",
  overall_reliability: { score: 80.0, rating: "high" },
  recommendation_types: [
    { recommendation_type: "channel", reliability_score: 90.0, rating: "high" },
    { recommendation_type: "topic", reliability_score: 55.0, rating: "medium" },
  ],
  insufficient_data: false,
};

function setStates(
  drift: Partial<ReturnType<typeof useDrift>>,
  reliability: Partial<ReturnType<typeof useReliability>>,
) {
  mockUseDrift.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...drift,
  } as ReturnType<typeof useDrift>);
  mockUseReliability.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...reliability,
  } as ReturnType<typeof useReliability>);
}

const WS = "ws-test-1";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ReliabilityDriftPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Root element ────────────────────────────────────────────────────────────

  it("renders the root panel element", () => {
    setStates({ isLoading: true }, { isLoading: true });
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-drift-panel")).not.toBeNull();
  });

  // ── Loading states ──────────────────────────────────────────────────────────

  it("shows skeletons while drift is loading", () => {
    setStates({ isLoading: true }, { isLoading: false, data: fullReliability });
    const { container } = render(<ReliabilityDriftPanel workspaceId={WS} />);
    const skeletons = container.querySelectorAll("[data-testid='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows skeletons while reliability is loading", () => {
    setStates({ isLoading: false, data: fullDrift }, { isLoading: true });
    const { container } = render(<ReliabilityDriftPanel workspaceId={WS} />);
    const skeletons = container.querySelectorAll("[data-testid='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  // ── Error states ────────────────────────────────────────────────────────────

  it("shows drift-error when drift query fails", () => {
    setStates({ isError: true }, { isLoading: false, data: fullReliability });
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-error")).not.toBeNull();
    expect(screen.getByText(/failed to load drift data/i)).not.toBeNull();
  });

  it("shows reliability-error when reliability query fails", () => {
    setStates({ isLoading: false, data: fullDrift }, { isError: true });
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-error")).not.toBeNull();
    expect(screen.getByText(/failed to load reliability data/i)).not.toBeNull();
  });

  it("drift error does not affect reliability section", () => {
    setStates({ isError: true }, { isLoading: false, data: fullReliability });
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-error")).not.toBeNull();
    expect(screen.getByTestId("card-reliability-score")).not.toBeNull();
  });

  it("reliability error does not affect drift section", () => {
    setStates({ isLoading: false, data: fullDrift }, { isError: true });
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-error")).not.toBeNull();
    expect(screen.getByTestId("card-drift-quality")).not.toBeNull();
  });

  // ── Insufficient data ───────────────────────────────────────────────────────

  it("shows drift-insufficient when insufficient_data flag is true", () => {
    const insuffDrift: DriftOut = { ...fullDrift, insufficient_data: true };
    setStates(
      { isLoading: false, data: insuffDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-insufficient")).not.toBeNull();
    expect(screen.getByText(/60 days/i)).not.toBeNull();
  });

  it("shows reliability-insufficient when insufficient_data flag is true", () => {
    const insuffRel: ReliabilityOut = { ...fullReliability, insufficient_data: true };
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: insuffRel },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-insufficient")).not.toBeNull();
  });

  // ── Drift cards (Section 1) ─────────────────────────────────────────────────

  it("renders card-drift-quality with correct current value", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-drift-quality");
    expect(card.textContent).toContain("75.0");
  });

  it("renders card-drift-adoption", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("card-drift-adoption")).not.toBeNull();
  });

  it("renders card-drift-success", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("card-drift-success")).not.toBeNull();
  });

  it("shows improving badge for improving direction", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    // fullDrift.overall.quality_score.direction = "improving"
    const card = screen.getByTestId("card-drift-quality");
    expect(card.textContent?.toLowerCase()).toContain("improving");
  });

  it("shows declining badge for declining direction", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    // fullDrift.overall.success_rate.direction = "declining"
    const card = screen.getByTestId("card-drift-success");
    expect(card.textContent?.toLowerCase()).toContain("declining");
  });

  it("shows positive change with + prefix", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-drift-quality");
    expect(card.textContent).toContain("+");
  });

  // ── Drift table (Section 2) ─────────────────────────────────────────────────

  it("renders drift-table when by_type is non-empty", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-table")).not.toBeNull();
  });

  it("renders drift-row for each rec type", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-row-channel")).not.toBeNull();
    expect(screen.getByTestId("drift-row-topic")).not.toBeNull();
  });

  it("shows drift-table-empty when by_type is empty", () => {
    const emptyDrift: DriftOut = { ...fullDrift, by_type: [] };
    setStates(
      { isLoading: false, data: emptyDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("drift-table-empty")).not.toBeNull();
  });

  // ── Reliability cards (Section 3) ──────────────────────────────────────────

  it("renders card-reliability-score", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const scoreCard = screen.getByTestId("card-reliability-score");
    expect(scoreCard.textContent).toContain("80.0");
  });

  it("renders card-reliability-rating with correct rating", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const ratingCard = screen.getByTestId("card-reliability-rating");
    expect(ratingCard.textContent?.toLowerCase()).toContain("high");
  });

  it("shows Reliability Rating label", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByText("Reliability Rating")).not.toBeNull();
  });

  // ── Reliability table (Section 4) ──────────────────────────────────────────

  it("renders reliability-table when recommendation_types is non-empty", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-table")).not.toBeNull();
  });

  it("renders reliability-row for each rec type", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-row-channel")).not.toBeNull();
    expect(screen.getByTestId("reliability-row-topic")).not.toBeNull();
  });

  it("shows reliability-table-empty when recommendation_types is empty", () => {
    const emptyRel: ReliabilityOut = {
      ...fullReliability,
      recommendation_types: [],
    };
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: emptyRel },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    expect(screen.getByTestId("reliability-table-empty")).not.toBeNull();
  });

  it("shows score in reliability row", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const row = screen.getByTestId("reliability-row-channel");
    expect(row.textContent).toContain("90.0");
  });

  it("shows rating badge in reliability row", () => {
    setStates(
      { isLoading: false, data: fullDrift },
      { isLoading: false, data: fullReliability },
    );
    render(<ReliabilityDriftPanel workspaceId={WS} />);
    const topicRow = screen.getByTestId("reliability-row-topic");
    expect(topicRow.textContent?.toLowerCase()).toContain("medium");
  });
});
