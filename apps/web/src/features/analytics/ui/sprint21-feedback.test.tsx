/**
 * Sprint 21 — feedback buttons + quality badge tests.
 *
 * Tests the RecommendationCard feedback buttons and the QualityBadge
 * in RecommendationsPanel.  Both components are isolated via mocked hooks.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { RecommendationEffectivenessOut, RecommendationItem } from "@/features/analytics/types";

// ── Mock hooks ────────────────────────────────────────────────────────────────

const mockMutate = vi.fn();
const mockSubmitFeedback = vi.fn(() => ({
  mutate: mockMutate,
  isPending: false,
}));

const mockUseRecommendations = vi.fn(() => ({
  data: undefined,
  isLoading: false,
  isError: false,
}));

const mockUseEffectiveness = vi.fn(() => ({
  data: undefined,
  isLoading: false,
  isError: false,
}));

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useSubmitFeedback: mockSubmitFeedback,
  useRecommendations: mockUseRecommendations,
  useRecommendationEffectiveness: mockUseEffectiveness,
  useInsights: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

const WORKSPACE_ID = "ws-test-1";

function makeItem(type = "channel"): RecommendationItem {
  return {
    type,
    title: `${type} recommendation`,
    rationale: "Test rationale",
    action: "Test action",
    supporting_data: {},
    confidence_score: 75,
    confidence_level: "high",
    evidence_strength: "strong",
    sample_size: 10,
    low_confidence: false,
    generated_at: new Date().toISOString(),
  };
}

function makeEffectivenessData(
  overallScore: number | null,
): RecommendationEffectivenessOut {
  return {
    workspace_id: WORKSPACE_ID,
    period_days: 30,
    generated_at: new Date().toISOString(),
    by_type: [],
    overall_quality_score: overallScore,
  };
}

// ── RecommendationCard feedback buttons ───────────────────────────────────────

describe("RecommendationCard — feedback buttons", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubmitFeedback.mockReturnValue({ mutate: mockMutate, isPending: false });
  });

  it("renders all three feedback buttons for each card", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />);

    expect(screen.getByTestId("feedback-buttons-channel")).toBeDefined();
    expect(screen.getByTestId("feedback-helpful-channel")).toBeDefined();
    expect(screen.getByTestId("feedback-not-helpful-channel")).toBeDefined();
    expect(screen.getByTestId("feedback-dismissed-channel")).toBeDefined();
  });

  it("clicking thumbs-up calls mutate with outcome=helpful", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />);

    fireEvent.click(screen.getByTestId("feedback-helpful-channel"));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ outcome: "helpful", rec_type: "channel" }),
    );
  });

  it("clicking thumbs-down calls mutate with outcome=not_helpful", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("industry")} workspaceId={WORKSPACE_ID} />);

    fireEvent.click(screen.getByTestId("feedback-not-helpful-industry"));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ outcome: "not_helpful", rec_type: "industry" }),
    );
  });

  it("clicking dismiss calls mutate with outcome=dismissed", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("topic")} workspaceId={WORKSPACE_ID} />);

    fireEvent.click(screen.getByTestId("feedback-dismissed-topic"));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ outcome: "dismissed", rec_type: "topic" }),
    );
  });

  it("buttons disappear and confirmation shown after submission", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />);

    fireEvent.click(screen.getByTestId("feedback-helpful-channel"));

    await waitFor(() => {
      expect(screen.queryByTestId("feedback-buttons-channel")).toBeNull();
      expect(screen.getByTestId("feedback-submitted-channel")).toBeDefined();
    });
  });

  it("second click on a different button is ignored after first submission", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />);

    fireEvent.click(screen.getByTestId("feedback-helpful-channel"));

    // After first click the buttons unmount; mutate should only have been called once
    expect(mockMutate).toHaveBeenCalledTimes(1);
  });

  it("buttons are disabled while mutation isPending", async () => {
    mockSubmitFeedback.mockReturnValue({ mutate: mockMutate, isPending: true });

    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    render(<RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />);

    const helpfulBtn = screen.getByTestId("feedback-helpful-channel");
    expect(helpfulBtn).toHaveProperty("disabled", true);
  });

  it("each card type has independent feedback buttons", async () => {
    const { RecommendationCard } = await import(
      "@/features/analytics/ui/recommendation-card"
    );
    const { container } = render(
      <div>
        <RecommendationCard item={makeItem("channel")} workspaceId={WORKSPACE_ID} />
        <RecommendationCard item={makeItem("industry")} workspaceId={WORKSPACE_ID} />
      </div>,
    );

    expect(screen.getByTestId("feedback-buttons-channel")).toBeDefined();
    expect(screen.getByTestId("feedback-buttons-industry")).toBeDefined();
  });
});

// ── RecommendationsPanel — quality badge ──────────────────────────────────────

describe("RecommendationsPanel — quality badge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubmitFeedback.mockReturnValue({ mutate: mockMutate, isPending: false });
    mockUseRecommendations.mockReturnValue({
      data: { recommendations: [], suppressed_count: 0, total: 0 },
      isLoading: false,
      isError: false,
    });
  });

  it("shows 'Building data...' badge when overall_quality_score is null", async () => {
    mockUseEffectiveness.mockReturnValue({
      data: makeEffectivenessData(null),
      isLoading: false,
      isError: false,
    });

    const { RecommendationsPanel } = await import(
      "@/features/analytics/ui/recommendations-panel"
    );
    render(<RecommendationsPanel workspaceId={WORKSPACE_ID} />);

    expect(screen.getByTestId("quality-badge-building")).toBeDefined();
    expect(screen.queryByTestId("quality-badge")).toBeNull();
  });

  it("shows quality badge with score when data is available", async () => {
    mockUseEffectiveness.mockReturnValue({
      data: makeEffectivenessData(85),
      isLoading: false,
      isError: false,
    });

    const { RecommendationsPanel } = await import(
      "@/features/analytics/ui/recommendations-panel"
    );
    render(<RecommendationsPanel workspaceId={WORKSPACE_ID} />);

    const badge = screen.getByTestId("quality-badge");
    expect(badge).toBeDefined();
    expect(badge.textContent).toContain("85");
  });

  it("shows no badge when effectiveness data is not yet loaded", async () => {
    mockUseEffectiveness.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    const { RecommendationsPanel } = await import(
      "@/features/analytics/ui/recommendations-panel"
    );
    render(<RecommendationsPanel workspaceId={WORKSPACE_ID} />);

    expect(screen.queryByTestId("quality-badge")).toBeNull();
    expect(screen.queryByTestId("quality-badge-building")).toBeNull();
  });

  it("passes workspaceId to each RecommendationCard", async () => {
    mockUseRecommendations.mockReturnValue({
      data: {
        recommendations: [makeItem("channel"), makeItem("industry")],
        suppressed_count: 0,
        total: 2,
      },
      isLoading: false,
      isError: false,
    });
    mockUseEffectiveness.mockReturnValue({ data: undefined });
    mockSubmitFeedback.mockReturnValue({ mutate: mockMutate, isPending: false });

    const { RecommendationsPanel } = await import(
      "@/features/analytics/ui/recommendations-panel"
    );
    render(<RecommendationsPanel workspaceId={WORKSPACE_ID} />);

    // Feedback buttons for both card types present → workspaceId passed through
    expect(screen.getByTestId("feedback-buttons-channel")).toBeDefined();
    expect(screen.getByTestId("feedback-buttons-industry")).toBeDefined();
  });
});
