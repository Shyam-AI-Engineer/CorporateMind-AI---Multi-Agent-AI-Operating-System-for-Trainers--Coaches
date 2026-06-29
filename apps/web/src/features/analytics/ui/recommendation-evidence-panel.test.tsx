import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { EvidenceOut } from "@/features/analytics/types";

// ── Mocks ──────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useEvidence: vi.fn(),
}));

import { useEvidence } from "@/features/analytics/api/use-analytics";
const mockUseEvidence = vi.mocked(useEvidence);

const { RecommendationEvidencePanel } = await import(
  "./recommendation-evidence-panel"
);

// ── Fixtures ───────────────────────────────────────────────────────────────────

const WORKSPACE = "ws-test-1";

const fullEvidence: EvidenceOut = {
  generated_at: "2026-06-25T10:00:00Z",
  recommendation_type: "industry",
  summary: {
    generated_count: 42,
    portfolio_percentage: 28.5,
    confidence_average: 74.0,
    quality_score: 81,
    acted_rate: 60.0,
    success_rate: 45.0,
    reliability_score: 82.0,
    reliability_rating: "high",
    avg_days_to_action: 3.2,
    avg_days_to_success: 9.1,
    drift_direction: "stable",
    stability_rating: "stable",
    calibration_status: "calibrated",
    coverage_status: "healthy",
    last_generated_at: "2026-06-24",
    days_since_last_generated: 1,
  },
  supporting_metrics: [
    { name: "Quality Score", value: 81, source: "recommendation_quality_scores" },
    { name: "Acted Rate", value: 60, source: "recommendation_outcomes" },
    { name: "Success Rate", value: 45, source: "recommendation_outcomes" },
  ],
  insufficient_data: false,
};

const insufficientEvidence: EvidenceOut = {
  ...fullEvidence,
  insufficient_data: true,
};

function renderPanel() {
  return render(<RecommendationEvidencePanel workspaceId={WORKSPACE} />);
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("RecommendationEvidencePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Panel root ───────────────────────────────────────────────────────────────

  it("renders the panel root with correct testid", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("recommendation-evidence-panel")).not.toBeNull();
  });

  // ── Section 1: Selector ──────────────────────────────────────────────────────

  it("renders the rec-type selector with all 5 options", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const select = screen.getByTestId("rec-type-selector") as HTMLSelectElement;
    expect(select).not.toBeNull();
    expect(screen.getByTestId("rec-type-option-industry")).not.toBeNull();
    expect(screen.getByTestId("rec-type-option-topic")).not.toBeNull();
    expect(screen.getByTestId("rec-type-option-campaign")).not.toBeNull();
    expect(screen.getByTestId("rec-type-option-pricing")).not.toBeNull();
    expect(screen.getByTestId("rec-type-option-channel")).not.toBeNull();
  });

  it("defaults to 'industry' recommendation type", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const select = screen.getByTestId("rec-type-selector") as HTMLSelectElement;
    expect(select.value).toBe("industry");
  });

  it("calls useEvidence with workspaceId and selected type", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(mockUseEvidence).toHaveBeenCalledWith(WORKSPACE, "industry");
  });

  it("re-queries when selector changes to 'topic'", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const select = screen.getByTestId("rec-type-selector");
    fireEvent.change(select, { target: { value: "topic" } });
    expect(mockUseEvidence).toHaveBeenCalledWith(WORKSPACE, "topic");
  });

  it("re-queries when selector changes to 'campaign'", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const select = screen.getByTestId("rec-type-selector");
    fireEvent.change(select, { target: { value: "campaign" } });
    expect(mockUseEvidence).toHaveBeenCalledWith(WORKSPACE, "campaign");
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it("shows skeletons while loading", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    const { container } = renderPanel();
    const skeletons = container.querySelectorAll("[data-testid='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("hides summary cards while loading", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.queryByTestId("card-generated-count")).toBeNull();
  });

  // ── Error state ───────────────────────────────────────────────────────────────

  it("shows error banner on fetch failure", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("evidence-error")).not.toBeNull();
    expect(screen.getByText(/failed to load evidence/i)).not.toBeNull();
  });

  it("hides summary cards on error", () => {
    mockUseEvidence.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.queryByTestId("card-generated-count")).toBeNull();
  });

  // ── Insufficient data state ───────────────────────────────────────────────────

  it("shows insufficient data notice when flag is true", () => {
    mockUseEvidence.mockReturnValue({ data: insufficientEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("evidence-insufficient")).not.toBeNull();
    expect(screen.getByText(/no evidence available/i)).not.toBeNull();
  });

  it("hides summary cards when insufficient_data is true", () => {
    mockUseEvidence.mockReturnValue({ data: insufficientEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.queryByTestId("card-generated-count")).toBeNull();
  });

  it("hides metrics table when insufficient_data is true", () => {
    mockUseEvidence.mockReturnValue({ data: insufficientEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.queryByTestId("metrics-table")).toBeNull();
  });

  // ── Section 2: Summary cards ─────────────────────────────────────────────────

  it("renders generated count card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("card-generated-count")).not.toBeNull();
    expect(screen.getByText("42")).not.toBeNull();
  });

  it("renders quality score card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("card-quality-score")).not.toBeNull();
    expect(screen.getByText("81")).not.toBeNull();
  });

  it("renders reliability card with formatted score", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-reliability");
    expect(card).not.toBeNull();
    expect(card.textContent).toContain("82.0");
  });

  it("renders success rate card as percentage", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-success-rate");
    expect(card).not.toBeNull();
    expect(card.textContent).toContain("45.0%");
  });

  it("shows dash for null quality_score", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, quality_score: null },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-quality-score");
    expect(card.textContent).toContain("—");
  });

  it("shows dash for null reliability_score", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, reliability_score: null },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-reliability");
    expect(card.textContent).toContain("—");
  });

  // ── Section 3: Timeline cards ─────────────────────────────────────────────────

  it("renders last generated card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-last-generated");
    expect(card.textContent).toContain("2026-06-24");
  });

  it("renders days since last generated card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-days-since");
    expect(card.textContent).toContain("1");
  });

  it("shows dash when last_generated_at is null", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: {
        ...fullEvidence.summary,
        last_generated_at: null,
        days_since_last_generated: null,
      },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("card-last-generated").textContent).toContain("—");
  });

  it("renders avg days to action card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-avg-days-action");
    expect(card.textContent).toContain("3.2");
  });

  it("renders avg days to success card", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const card = screen.getByTestId("card-avg-days-success");
    expect(card.textContent).toContain("9.1");
  });

  // ── Section 4: Supporting metrics table ──────────────────────────────────────

  it("renders the metrics table with correct headers", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const table = screen.getByTestId("metrics-table");
    expect(table.textContent).toContain("Metric");
    expect(table.textContent).toContain("Value");
    expect(table.textContent).toContain("Source");
  });

  it("renders each supporting metric row", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("metric-row-quality-score")).not.toBeNull();
    expect(screen.getByTestId("metric-row-acted-rate")).not.toBeNull();
    expect(screen.getByTestId("metric-row-success-rate")).not.toBeNull();
  });

  it("shows source attribution in metric rows", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    // quality_scores source appears once; outcomes appears multiple times
    expect(screen.getAllByText("recommendation_quality_scores").length).toBeGreaterThan(0);
    expect(screen.getAllByText("recommendation_outcomes").length).toBeGreaterThan(0);
  });

  it("shows empty message when supporting_metrics is empty", () => {
    const ev: EvidenceOut = { ...fullEvidence, supporting_metrics: [] };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("metrics-table-empty")).not.toBeNull();
    expect(screen.queryByTestId("metrics-table")).toBeNull();
  });

  it("shows dash for null metric value", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      supporting_metrics: [{ name: "Quality Score", value: null, source: "recommendation_quality_scores" }],
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const row = screen.getByTestId("metric-row-quality-score");
    expect(row.textContent).toContain("—");
  });

  // ── Section 5: Health badges ──────────────────────────────────────────────────

  it("renders the health badges container", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("health-badges")).not.toBeNull();
  });

  it("renders calibration badge with correct value", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const badge = screen.getByTestId("badge-calibration");
    expect(badge.textContent).toBe("calibrated");
  });

  it("renders reliability badge with correct value", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const badge = screen.getByTestId("badge-reliability");
    expect(badge.textContent).toBe("high");
  });

  it("renders stability badge with correct value", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const badge = screen.getByTestId("badge-stability");
    expect(badge.textContent).toBe("stable");
  });

  it("renders coverage badge with correct value", () => {
    mockUseEvidence.mockReturnValue({ data: fullEvidence, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    const badge = screen.getByTestId("badge-coverage");
    expect(badge.textContent).toBe("healthy");
  });

  it("shows dash for null calibration_status", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, calibration_status: null },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("badge-calibration").textContent).toBe("—");
  });

  it("shows dash for null stability_rating", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, stability_rating: null },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("badge-stability").textContent).toBe("—");
  });

  it("shows dash for null reliability_rating", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, reliability_rating: null },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("badge-reliability").textContent).toBe("—");
  });

  it("reflects 'warning' calibration badge", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, calibration_status: "warning" },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("badge-calibration").textContent).toBe("warning");
  });

  it("reflects 'missing' coverage badge", () => {
    const ev: EvidenceOut = {
      ...fullEvidence,
      summary: { ...fullEvidence.summary, coverage_status: "missing" },
    };
    mockUseEvidence.mockReturnValue({ data: ev, isLoading: false, isError: false } as ReturnType<typeof useEvidence>);
    renderPanel();
    expect(screen.getByTestId("badge-coverage").textContent).toBe("missing");
  });
});
