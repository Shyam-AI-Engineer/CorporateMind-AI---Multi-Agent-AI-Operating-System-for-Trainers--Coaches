import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ── Hook mocks ────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useLifecycle: vi.fn(),
  useDecay: vi.fn(),
}));

import {
  useLifecycle,
  useDecay,
} from "@/features/analytics/api/use-analytics";
import type { LifecycleOut, DecayOut } from "@/features/analytics/types";
import { LifecycleObservatoryPanel } from "./lifecycle-observatory-panel";

const mockUseLifecycle = vi.mocked(useLifecycle);
const mockUseDecay = vi.mocked(useDecay);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const fullLifecycle: LifecycleOut = {
  generated_at: "2026-06-25T10:00:00Z",
  overall: {
    avg_days_to_action: 5.5,
    avg_days_to_success: 18.2,
    acted_rate: 62.5,
    success_rate: 41.0,
  },
  recommendation_types: [
    {
      recommendation_type: "channel",
      avg_days_to_action: 4.0,
      avg_days_to_success: 14.0,
      acted_rate: 70.0,
      success_rate: 45.0,
    },
    {
      recommendation_type: "topic",
      avg_days_to_action: 7.0,
      avg_days_to_success: 22.0,
      acted_rate: 55.0,
      success_rate: 37.0,
    },
  ],
  insufficient_data: false,
};

const fullDecay: DecayOut = {
  generated_at: "2026-06-25T10:00:00Z",
  buckets: [
    { age_bucket: "0-7", acted_rate: 80.0, success_rate: 60.0, sample_size: 20 },
    { age_bucket: "8-30", acted_rate: 65.0, success_rate: 45.0, sample_size: 30 },
    { age_bucket: "31-60", acted_rate: 40.0, success_rate: 25.0, sample_size: 10 },
    { age_bucket: "60+", acted_rate: 20.0, success_rate: 10.0, sample_size: 5 },
  ],
  recommendation_types: [
    {
      recommendation_type: "channel",
      best_bucket: "0-7",
      worst_bucket: "60+",
      decay_detected: true,
    },
    {
      recommendation_type: "topic",
      best_bucket: "8-30",
      worst_bucket: "60+",
      decay_detected: false,
    },
  ],
};

function setStates(
  lc: Partial<ReturnType<typeof useLifecycle>>,
  dc: Partial<ReturnType<typeof useDecay>>,
) {
  mockUseLifecycle.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...lc,
  } as ReturnType<typeof useLifecycle>);
  mockUseDecay.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...dc,
  } as ReturnType<typeof useDecay>);
}

const WS = "ws-lifecycle-1";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("LifecycleObservatoryPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  // ── Root ────────────────────────────────────────────────────────────────────

  it("renders the root panel element", () => {
    setStates({ isLoading: true }, { isLoading: true });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-observatory-panel")).not.toBeNull();
  });

  // ── Loading states ──────────────────────────────────────────────────────────

  it("shows skeletons while lifecycle is loading", () => {
    setStates({ isLoading: true }, { isLoading: false, data: fullDecay });
    const { container } = render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThan(0);
  });

  it("shows skeletons while decay is loading", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: true });
    const { container } = render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThan(0);
  });

  // ── Error states ────────────────────────────────────────────────────────────

  it("shows lifecycle-error when lifecycle query fails", () => {
    setStates({ isError: true }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-error")).not.toBeNull();
    expect(screen.getByText(/failed to load lifecycle data/i)).not.toBeNull();
  });

  it("shows decay-error when decay query fails", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isError: true });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-error")).not.toBeNull();
    expect(screen.getByText(/failed to load decay data/i)).not.toBeNull();
  });

  it("lifecycle error does not affect decay section", () => {
    setStates({ isError: true }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-error")).not.toBeNull();
    expect(screen.getByTestId("decay-table")).not.toBeNull();
  });

  it("decay error does not affect lifecycle section", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isError: true });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-error")).not.toBeNull();
    expect(screen.getByTestId("card-avg-days-action")).not.toBeNull();
  });

  // ── Insufficient data ───────────────────────────────────────────────────────

  it("shows lifecycle-insufficient when insufficient_data is true", () => {
    const insuffLc: LifecycleOut = { ...fullLifecycle, insufficient_data: true };
    setStates({ isLoading: false, data: insuffLc }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-insufficient")).not.toBeNull();
    expect(screen.getByText(/completed recommendation outcomes/i)).not.toBeNull();
  });

  // ── Section 1: Lifecycle Summary cards ─────────────────────────────────────

  it("renders card-avg-days-action with correct value", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-avg-days-action");
    expect(card.textContent).toContain("5.5");
  });

  it("renders card-avg-days-success", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-avg-days-success");
    expect(card.textContent).toContain("18.2");
  });

  it("renders card-acted-rate as percentage", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-acted-rate");
    expect(card.textContent).toContain("62.5%");
  });

  it("renders card-success-rate as percentage", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const card = screen.getByTestId("card-success-rate");
    expect(card.textContent).toContain("41.0%");
  });

  // ── Section 2: Recommendation Lifecycle Table ───────────────────────────────

  it("renders lifecycle-table when recommendation_types is non-empty", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-table")).not.toBeNull();
  });

  it("renders lifecycle-row for each type", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-row-channel")).not.toBeNull();
    expect(screen.getByTestId("lifecycle-row-topic")).not.toBeNull();
  });

  it("shows lifecycle-table-empty when recommendation_types is empty", () => {
    const emptyLc: LifecycleOut = { ...fullLifecycle, recommendation_types: [] };
    setStates({ isLoading: false, data: emptyLc }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("lifecycle-table-empty")).not.toBeNull();
  });

  it("lifecycle row contains acted_rate value", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const row = screen.getByTestId("lifecycle-row-channel");
    expect(row.textContent).toContain("70.0%");
  });

  // ── Section 3: Effectiveness Decay ─────────────────────────────────────────

  it("renders decay-table when buckets have data", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-table")).not.toBeNull();
  });

  it("renders a row for each bucket", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-bucket-0-7")).not.toBeNull();
    expect(screen.getByTestId("decay-bucket-8-30")).not.toBeNull();
    expect(screen.getByTestId("decay-bucket-31-60")).not.toBeNull();
    expect(screen.getByTestId("decay-bucket-60+")).not.toBeNull();
  });

  it("shows sample_size in decay bucket row", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const row = screen.getByTestId("decay-bucket-0-7");
    expect(row.textContent).toContain("20");
  });

  it("shows decay-table-empty when all buckets have sample_size 0", () => {
    const emptyDecay: DecayOut = {
      ...fullDecay,
      buckets: fullDecay.buckets.map((b) => ({ ...b, sample_size: 0, acted_rate: 0, success_rate: 0 })),
    };
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: emptyDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-table-empty")).not.toBeNull();
  });

  // ── Section 4: Decay Detection ──────────────────────────────────────────────

  it("renders decay-detection-table when recommendation_types is non-empty", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-detection-table")).not.toBeNull();
  });

  it("renders decay-detection-row for each type", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-detection-row-channel")).not.toBeNull();
    expect(screen.getByTestId("decay-detection-row-topic")).not.toBeNull();
  });

  it("shows Yes badge when decay_detected is true", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const row = screen.getByTestId("decay-detection-row-channel");
    expect(row.textContent).toContain("Yes");
  });

  it("shows No badge when decay_detected is false", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const row = screen.getByTestId("decay-detection-row-topic");
    expect(row.textContent).toContain("No");
  });

  it("shows best_bucket and worst_bucket in decay detection row", () => {
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: fullDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    const row = screen.getByTestId("decay-detection-row-channel");
    expect(row.textContent).toContain("0-7");
    expect(row.textContent).toContain("60+");
  });

  it("shows decay-detection-table-empty when recommendation_types is empty", () => {
    const emptyDecay: DecayOut = { ...fullDecay, recommendation_types: [] };
    setStates({ isLoading: false, data: fullLifecycle }, { isLoading: false, data: emptyDecay });
    render(<LifecycleObservatoryPanel workspaceId={WS} />);
    expect(screen.getByTestId("decay-detection-table-empty")).not.toBeNull();
  });
});
