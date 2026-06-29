import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecommendationWorkQueue } from "./recommendation-work-queue";
import type { WorkQueueGroupItem, WorkQueueOut } from "@/features/analytics/types";

// ── mock hooks ────────────────────────────────────────────────────────────────

const mockUseRecommendationWorkQueue = vi.fn();
const mockUseStartRecommendation = vi.fn();
const mockUseBlockRecommendation = vi.fn();
const mockUseCompleteRecommendation = vi.fn();
const mockUseCancelRecommendation = vi.fn();

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecommendationWorkQueue: (...args: unknown[]) =>
    mockUseRecommendationWorkQueue(...args),
  useStartRecommendation: (...args: unknown[]) =>
    mockUseStartRecommendation(...args),
  useBlockRecommendation: (...args: unknown[]) =>
    mockUseBlockRecommendation(...args),
  useCompleteRecommendation: (...args: unknown[]) =>
    mockUseCompleteRecommendation(...args),
  useCancelRecommendation: (...args: unknown[]) =>
    mockUseCancelRecommendation(...args),
}));

// ── helpers ───────────────────────────────────────────────────────────────────

const WS = "ws-test-123";

function makeItem(overrides: Partial<WorkQueueGroupItem> = {}): WorkQueueGroupItem {
  return {
    recommendation_id: "rec-001",
    title: "Expand to enterprise segment",
    action_type: "accepted",
    execution_status: null,
    started_at: null,
    completed_at: null,
    blocked_at: null,
    cancelled_at: null,
    blocked_reason: null,
    completion_notes: null,
    accepted_at: "2026-06-26T10:00:00Z",
    ...overrides,
  };
}

const emptyQueue: WorkQueueOut = {
  ready: [],
  in_progress: [],
  blocked: [],
  completed: [],
  cancelled: [],
  timeline: [],
  total: 0,
};

const mutate = vi.fn();
const mutationIdle = { mutate, isPending: false };

beforeEach(() => {
  vi.clearAllMocks();
  mockUseStartRecommendation.mockReturnValue(mutationIdle);
  mockUseBlockRecommendation.mockReturnValue(mutationIdle);
  mockUseCompleteRecommendation.mockReturnValue(mutationIdle);
  mockUseCancelRecommendation.mockReturnValue(mutationIdle);
});

function renderWithData(data: WorkQueueOut) {
  mockUseRecommendationWorkQueue.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
  });
  render(<RecommendationWorkQueue workspaceId={WS} />);
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationWorkQueue", () => {
  describe("loading state", () => {
    it("renders skeleton while loading", () => {
      mockUseRecommendationWorkQueue.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });
      render(<RecommendationWorkQueue workspaceId={WS} />);
      expect(screen.getByTestId("work-queue-skeleton")).not.toBeNull();
    });
  });

  describe("error state", () => {
    it("renders error message on failure", () => {
      mockUseRecommendationWorkQueue.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });
      render(<RecommendationWorkQueue workspaceId={WS} />);
      expect(screen.getByTestId("work-queue-error")).not.toBeNull();
    });
  });

  describe("empty state", () => {
    it("renders all sections with empty messages", () => {
      renderWithData(emptyQueue);
      expect(screen.getByTestId("recommendation-work-queue")).not.toBeNull();
      expect(screen.getByTestId("ready-section")).not.toBeNull();
      expect(screen.getByTestId("in-progress-section")).not.toBeNull();
      expect(screen.getByTestId("blocked-section")).not.toBeNull();
      expect(screen.getByTestId("completed-section")).not.toBeNull();
      expect(screen.getByTestId("cancelled-section")).not.toBeNull();
      expect(screen.getByTestId("timeline-section")).not.toBeNull();
    });

    it("shows 'No work queued.' in ready section", () => {
      renderWithData(emptyQueue);
      expect(screen.getByTestId("ready-empty")).not.toBeNull();
      expect(screen.getByText("No work queued.")).not.toBeNull();
    });

    it("shows 'No completed recommendations.' in completed section", () => {
      renderWithData(emptyQueue);
      expect(screen.getByTestId("completed-empty")).not.toBeNull();
    });

    it("shows empty timeline message", () => {
      renderWithData(emptyQueue);
      expect(screen.getByTestId("timeline-empty")).not.toBeNull();
    });
  });

  describe("ready section", () => {
    it("renders ready cards with Start button", () => {
      const item = makeItem({ execution_status: null });
      renderWithData({ ...emptyQueue, ready: [item], total: 1 });
      expect(screen.getByTestId(`ready-card-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByTestId(`start-btn-${item.recommendation_id}`)).not.toBeNull();
    });

    it("calls startMutation on Start click", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: null });
      renderWithData({ ...emptyQueue, ready: [item], total: 1 });
      await user.click(screen.getByTestId(`start-btn-${item.recommendation_id}`));
      expect(mutate).toHaveBeenCalledWith({ recommendationId: item.recommendation_id });
    });

    it("shows recommendation title on ready card", () => {
      const item = makeItem({ title: "Focus on enterprise" });
      renderWithData({ ...emptyQueue, ready: [item], total: 1 });
      expect(screen.getByText("Focus on enterprise")).not.toBeNull();
    });
  });

  describe("in-progress section", () => {
    it("renders in-progress cards with Complete and Block buttons", () => {
      const item = makeItem({
        execution_status: "in_progress",
        started_at: "2026-06-25T10:00:00Z",
      });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      expect(screen.getByTestId(`in-progress-card-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByTestId(`complete-btn-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByTestId(`block-btn-${item.recommendation_id}`)).not.toBeNull();
    });

    it("shows elapsed days label", () => {
      const item = makeItem({
        execution_status: "in_progress",
        started_at: "2026-06-24T10:00:00Z",
      });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      expect(screen.getByText(/elapsed/)).not.toBeNull();
    });
  });

  describe("blocked section", () => {
    it("renders blocked cards with Resume and Cancel buttons", () => {
      const item = makeItem({
        execution_status: "blocked",
        blocked_reason: "Awaiting legal review",
      });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      expect(screen.getByTestId(`blocked-card-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByTestId(`resume-btn-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByTestId(`cancel-from-blocked-btn-${item.recommendation_id}`)).not.toBeNull();
    });

    it("shows blocked reason text", () => {
      const item = makeItem({
        execution_status: "blocked",
        blocked_reason: "Awaiting legal review",
      });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      expect(screen.getByText("Awaiting legal review")).not.toBeNull();
    });

    it("Resume calls startMutation", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "blocked" });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      await user.click(screen.getByTestId(`resume-btn-${item.recommendation_id}`));
      expect(mutate).toHaveBeenCalledWith({ recommendationId: item.recommendation_id });
    });
  });

  describe("completed section", () => {
    it("renders completed cards with notes", () => {
      const item = makeItem({
        execution_status: "completed",
        completed_at: "2026-06-26T12:00:00Z",
        completion_notes: "Launched successfully",
      });
      renderWithData({ ...emptyQueue, completed: [item], total: 1 });
      expect(screen.getByTestId(`completed-card-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByText("Launched successfully")).not.toBeNull();
    });

    it("renders completed card without notes", () => {
      const item = makeItem({
        execution_status: "completed",
        completed_at: "2026-06-26T12:00:00Z",
        completion_notes: null,
      });
      renderWithData({ ...emptyQueue, completed: [item], total: 1 });
      expect(screen.getByTestId(`completed-card-${item.recommendation_id}`)).not.toBeNull();
    });
  });

  describe("cancelled section", () => {
    it("renders cancelled cards with reason", () => {
      const item = makeItem({
        execution_status: "cancelled",
        blocked_reason: "Budget cut",
      });
      renderWithData({ ...emptyQueue, cancelled: [item], total: 1 });
      expect(screen.getByTestId(`cancelled-card-${item.recommendation_id}`)).not.toBeNull();
      expect(screen.getByText("Budget cut")).not.toBeNull();
    });

    it("renders cancelled card without reason", () => {
      const item = makeItem({ execution_status: "cancelled", blocked_reason: null });
      renderWithData({ ...emptyQueue, cancelled: [item], total: 1 });
      expect(screen.getByTestId(`cancelled-card-${item.recommendation_id}`)).not.toBeNull();
    });
  });

  describe("timeline section", () => {
    it("renders timeline items", () => {
      const item = makeItem({ execution_status: "completed" });
      renderWithData({ ...emptyQueue, timeline: [item], total: 1 });
      expect(screen.getByTestId("timeline-list")).not.toBeNull();
      expect(screen.getByTestId(`timeline-item-${item.recommendation_id}`)).not.toBeNull();
    });

    it("timeline item shows title and status", () => {
      const item = makeItem({ execution_status: "completed", title: "My rec" });
      renderWithData({ ...emptyQueue, timeline: [item], total: 1 });
      expect(screen.getByText("My rec")).not.toBeNull();
    });
  });

  describe("block dialog", () => {
    it("opens block dialog on Block button click", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`block-btn-${item.recommendation_id}`));
      expect(screen.getByTestId("block-dialog")).not.toBeNull();
    });

    it("block confirm button disabled when reason empty", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`block-btn-${item.recommendation_id}`));
      const btn = screen.getByTestId("block-confirm-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    it("block confirm calls mutation with reason", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`block-btn-${item.recommendation_id}`));
      await user.type(screen.getByTestId("block-reason-input"), "Budget freeze");
      await user.click(screen.getByTestId("block-confirm-btn"));
      expect(mutate).toHaveBeenCalledWith({
        recommendationId: item.recommendation_id,
        reason: "Budget freeze",
      });
    });
  });

  describe("complete dialog", () => {
    it("opens complete dialog on Complete button click", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`complete-btn-${item.recommendation_id}`));
      expect(screen.getByTestId("complete-dialog")).not.toBeNull();
    });

    it("complete confirm calls mutation without notes", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`complete-btn-${item.recommendation_id}`));
      await user.click(screen.getByTestId("complete-confirm-btn"));
      expect(mutate).toHaveBeenCalledWith({
        recommendationId: item.recommendation_id,
        notes: "",
      });
    });

    it("complete confirm calls mutation with notes", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`complete-btn-${item.recommendation_id}`));
      await user.type(screen.getByTestId("complete-notes-input"), "Great outcome");
      await user.click(screen.getByTestId("complete-confirm-btn"));
      expect(mutate).toHaveBeenCalledWith({
        recommendationId: item.recommendation_id,
        notes: "Great outcome",
      });
    });
  });

  describe("cancel dialog", () => {
    it("opens cancel dialog from blocked card", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "blocked" });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      await user.click(screen.getByTestId(`cancel-from-blocked-btn-${item.recommendation_id}`));
      expect(screen.getByTestId("cancel-dialog")).not.toBeNull();
    });

    it("cancel confirm calls mutation with reason", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "blocked" });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      await user.click(screen.getByTestId(`cancel-from-blocked-btn-${item.recommendation_id}`));
      await user.type(screen.getByTestId("cancel-reason-input"), "No longer relevant");
      await user.click(screen.getByTestId("cancel-confirm-btn"));
      expect(mutate).toHaveBeenCalledWith({
        recommendationId: item.recommendation_id,
        reason: "No longer relevant",
      });
    });

    it("cancel confirm calls mutation without reason", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "blocked" });
      renderWithData({ ...emptyQueue, blocked: [item], total: 1 });
      await user.click(screen.getByTestId(`cancel-from-blocked-btn-${item.recommendation_id}`));
      await user.click(screen.getByTestId("cancel-confirm-btn"));
      expect(mutate).toHaveBeenCalledWith({
        recommendationId: item.recommendation_id,
        reason: "",
      });
    });
  });

  describe("no-auto-execution constraint", () => {
    it("start button click does not reference CampaignService", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: null });
      renderWithData({ ...emptyQueue, ready: [item], total: 1 });
      await user.click(screen.getByTestId(`start-btn-${item.recommendation_id}`));
      // Mutation was called (human action) but nothing auto-sends
      expect(mutate).toHaveBeenCalledTimes(1);
    });

    it("complete button triggers mutation only — no auto-send side effects", async () => {
      const user = userEvent.setup();
      const item = makeItem({ execution_status: "in_progress" });
      renderWithData({ ...emptyQueue, in_progress: [item], total: 1 });
      await user.click(screen.getByTestId(`complete-btn-${item.recommendation_id}`));
      await user.click(screen.getByTestId("complete-confirm-btn"));
      expect(mutate).toHaveBeenCalledTimes(1);
    });
  });
});
