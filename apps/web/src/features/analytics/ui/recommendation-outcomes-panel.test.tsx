import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { RecommendationOutcomesPanel } from "./recommendation-outcomes-panel";
import type { ExecutionSummaryOut, RecommendationOutcomesOut } from "@/features/analytics/types";

// ── mock hooks ────────────────────────────────────────────────────────────────

const mockUseExecutionSummary = vi.fn();
const mockUseRecommendationOutcomes = vi.fn();

vi.mock("@/features/analytics/ui/../api/use-analytics", () => ({
  useExecutionSummary: (...args: unknown[]) => mockUseExecutionSummary(...args),
  useRecommendationOutcomes: (...args: unknown[]) =>
    mockUseRecommendationOutcomes(...args),
}));

// ── helpers ───────────────────────────────────────────────────────────────────

const WS = "ws-test-abc";

function makeSummary(overrides: Partial<ExecutionSummaryOut> = {}): ExecutionSummaryOut {
  return {
    accepted: 10,
    started: 8,
    completed: 5,
    blocked: 1,
    cancelled: 2,
    completion_rate: 0.5,
    cancellation_rate: 0.2,
    block_rate: 0.1,
    avg_days_to_start: 1.5,
    avg_days_to_complete: 4.0,
    avg_days_blocked: 2.0,
    avg_days_cancelled: 5.0,
    work_in_progress: 2,
    overdue: 0,
    insufficient_data: false,
    ...overrides,
  };
}

function makeOutcomes(overrides: Partial<RecommendationOutcomesOut> = {}): RecommendationOutcomesOut {
  return {
    completed: 5,
    blocked: 1,
    cancelled: 2,
    in_progress: 2,
    ready: 0,
    by_rec_type: [
      {
        rec_type: "pricing",
        accepted: 6,
        completed: 3,
        cancelled: 1,
        blocked: 1,
        completion_rate: 0.5,
        avg_days_to_complete: 4.0,
        avg_days_to_start: 1.5,
      },
      {
        rec_type: "segment",
        accepted: 4,
        completed: 2,
        cancelled: 1,
        blocked: 0,
        completion_rate: 0.5,
        avg_days_to_complete: 3.0,
        avg_days_to_start: 1.0,
      },
    ],
    insufficient_data: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

function renderLoaded(
  summaryOverrides: Partial<ExecutionSummaryOut> = {},
  outcomesOverrides: Partial<RecommendationOutcomesOut> = {},
) {
  mockUseExecutionSummary.mockReturnValue({
    data: makeSummary(summaryOverrides),
    isLoading: false,
    isError: false,
  });
  mockUseRecommendationOutcomes.mockReturnValue({
    data: makeOutcomes(outcomesOverrides),
    isLoading: false,
    isError: false,
  });
  render(<RecommendationOutcomesPanel workspaceId={WS} />);
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationOutcomesPanel", () => {
  describe("loading state", () => {
    it("renders skeleton while loading", () => {
      mockUseExecutionSummary.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });
      mockUseRecommendationOutcomes.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });
      render(<RecommendationOutcomesPanel workspaceId={WS} />);
      expect(screen.getByTestId("outcomes-skeleton")).not.toBeNull();
    });

    it("shows skeleton when only summary is loading", () => {
      mockUseExecutionSummary.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });
      mockUseRecommendationOutcomes.mockReturnValue({
        data: makeOutcomes(),
        isLoading: false,
        isError: false,
      });
      render(<RecommendationOutcomesPanel workspaceId={WS} />);
      expect(screen.getByTestId("outcomes-skeleton")).not.toBeNull();
    });
  });

  describe("error state", () => {
    it("renders error when summary fails", () => {
      mockUseExecutionSummary.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });
      mockUseRecommendationOutcomes.mockReturnValue({
        data: makeOutcomes(),
        isLoading: false,
        isError: false,
      });
      render(<RecommendationOutcomesPanel workspaceId={WS} />);
      expect(screen.getByTestId("outcomes-error")).not.toBeNull();
    });

    it("renders error when outcomes fails", () => {
      mockUseExecutionSummary.mockReturnValue({
        data: makeSummary(),
        isLoading: false,
        isError: false,
      });
      mockUseRecommendationOutcomes.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });
      render(<RecommendationOutcomesPanel workspaceId={WS} />);
      expect(screen.getByTestId("outcomes-error")).not.toBeNull();
    });
  });

  describe("empty state", () => {
    it("renders no-history when accepted is 0", () => {
      renderLoaded(
        { accepted: 0, completed: 0, work_in_progress: 0, started: 0, blocked: 0, cancelled: 0 },
        { completed: 0, blocked: 0, cancelled: 0, in_progress: 0, ready: 0, by_rec_type: [] },
      );
      expect(screen.getByTestId("no-history-section")).not.toBeNull();
      expect(screen.getByTestId("no-history-message")).not.toBeNull();
    });
  });

  describe("KPI section", () => {
    it("renders kpi section", () => {
      renderLoaded();
      expect(screen.getByTestId("kpi-section")).not.toBeNull();
    });

    it("renders accepted KPI card", () => {
      renderLoaded();
      expect(screen.getByTestId("kpi-accepted")).not.toBeNull();
    });

    it("renders completed KPI card", () => {
      renderLoaded();
      expect(screen.getByTestId("kpi-completed")).not.toBeNull();
    });

    it("renders blocked KPI card", () => {
      renderLoaded();
      expect(screen.getByTestId("kpi-blocked")).not.toBeNull();
    });

    it("renders cancelled KPI card", () => {
      renderLoaded();
      expect(screen.getByTestId("kpi-cancelled")).not.toBeNull();
    });

    it("renders completion rate KPI", () => {
      renderLoaded({ completion_rate: 0.5 });
      const card = screen.getByTestId("kpi-completion-rate");
      expect(card).not.toBeNull();
      // 0.5 → 50.0% — scoped within card to avoid collision with type table
      expect(within(card).getByText("50.0%")).not.toBeNull();
    });

    it("renders WIP KPI card", () => {
      renderLoaded({ work_in_progress: 3 });
      const card = screen.getByTestId("kpi-wip");
      expect(card).not.toBeNull();
      expect(within(card).getByText("3")).not.toBeNull();
    });
  });

  describe("funnel section", () => {
    it("renders funnel section", () => {
      renderLoaded();
      expect(screen.getByTestId("funnel-section")).not.toBeNull();
    });

    it("renders all funnel steps", () => {
      renderLoaded();
      expect(screen.getByTestId("funnel-accepted")).not.toBeNull();
      expect(screen.getByTestId("funnel-started")).not.toBeNull();
      expect(screen.getByTestId("funnel-completed")).not.toBeNull();
      expect(screen.getByTestId("funnel-cancelled")).not.toBeNull();
      expect(screen.getByTestId("funnel-blocked")).not.toBeNull();
    });
  });

  describe("type table section", () => {
    it("renders type table", () => {
      renderLoaded();
      expect(screen.getByTestId("type-table-section")).not.toBeNull();
      expect(screen.getByTestId("type-table")).not.toBeNull();
    });

    it("renders a row per type", () => {
      renderLoaded();
      expect(screen.getByTestId("type-row-pricing")).not.toBeNull();
      expect(screen.getByTestId("type-row-segment")).not.toBeNull();
    });

    it("renders type name in row", () => {
      renderLoaded();
      expect(screen.getByText("pricing")).not.toBeNull();
      expect(screen.getByText("segment")).not.toBeNull();
    });

    it("shows empty state when no types", () => {
      renderLoaded({}, { by_rec_type: [] });
      expect(screen.getByTestId("type-table-empty")).not.toBeNull();
    });
  });

  describe("health section", () => {
    it("renders health section", () => {
      renderLoaded();
      expect(screen.getByTestId("health-section")).not.toBeNull();
    });

    it("shows avg days to start", () => {
      renderLoaded({ avg_days_to_start: 1.5 });
      const card = screen.getByTestId("health-avg-start");
      expect(card).not.toBeNull();
      expect(within(card).getByText("1.5")).not.toBeNull();
    });

    it("shows avg days to complete", () => {
      renderLoaded({ avg_days_to_complete: 4.0 });
      const card = screen.getByTestId("health-avg-complete");
      expect(card).not.toBeNull();
      expect(within(card).getByText("4.0")).not.toBeNull();
    });

    it("shows avg days blocked", () => {
      renderLoaded({ avg_days_blocked: 2.0 });
      const card = screen.getByTestId("health-avg-blocked");
      expect(card).not.toBeNull();
      expect(within(card).getByText("2.0")).not.toBeNull();
    });

    it("shows overdue count", () => {
      renderLoaded({ overdue: 3 });
      const card = screen.getByTestId("health-overdue");
      expect(card).not.toBeNull();
      expect(within(card).getByText("3")).not.toBeNull();
    });
  });

  describe("warnings section", () => {
    it("shows no-completed warning when completed is 0", () => {
      renderLoaded({ completed: 0 });
      expect(screen.getByTestId("warning-no-completed")).not.toBeNull();
    });

    it("does not show no-completed warning when there are completions", () => {
      renderLoaded({ completed: 3 });
      expect(screen.queryByTestId("warning-no-completed")).toBeNull();
    });

    it("shows overdue warning when overdue > 0", () => {
      renderLoaded({ overdue: 3 });
      expect(screen.getByTestId("warning-overdue")).not.toBeNull();
      expect(screen.getByText("3 recommendations overdue.")).not.toBeNull();
    });

    it("shows singular overdue when overdue is 1", () => {
      renderLoaded({ overdue: 1 });
      expect(screen.getByText("1 recommendation overdue.")).not.toBeNull();
    });

    it("does not show overdue warning when overdue is 0", () => {
      renderLoaded({ overdue: 0 });
      expect(screen.queryByTestId("warning-overdue")).toBeNull();
    });

    it("shows blocked warning when blocked > 0", () => {
      renderLoaded({ blocked: 2 });
      expect(screen.getByTestId("warning-blocked")).not.toBeNull();
      expect(screen.getByText("2 recommendations blocked.")).not.toBeNull();
    });

    it("shows singular blocked when blocked is 1", () => {
      renderLoaded({ blocked: 1 });
      expect(screen.getByText("1 recommendation blocked.")).not.toBeNull();
    });

    it("does not show blocked warning when blocked is 0", () => {
      renderLoaded({ blocked: 0 });
      expect(screen.queryByTestId("warning-blocked")).toBeNull();
    });

    it("shows multiple warnings simultaneously", () => {
      renderLoaded({ completed: 0, overdue: 2, blocked: 1 });
      expect(screen.getByTestId("warning-no-completed")).not.toBeNull();
      expect(screen.getByTestId("warning-overdue")).not.toBeNull();
      expect(screen.getByTestId("warning-blocked")).not.toBeNull();
    });
  });

  describe("no automation constraint", () => {
    it("panel is read-only — no mutation hooks used", () => {
      renderLoaded();
      // Panel renders without mutation hooks (no useStartRecommendation etc.)
      expect(screen.getByTestId("recommendation-outcomes-panel")).not.toBeNull();
      expect(mockUseExecutionSummary).toHaveBeenCalledWith(WS);
      expect(mockUseRecommendationOutcomes).toHaveBeenCalledWith(WS);
    });
  });
});
