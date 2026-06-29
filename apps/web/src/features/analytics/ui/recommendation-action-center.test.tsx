import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RecommendationActionsListOut } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useRecommendationActions: vi.fn(),
  useAcceptRecommendation: vi.fn(),
  useDismissRecommendation: vi.fn(),
  useSnoozeRecommendation: vi.fn(),
}));

import {
  useRecommendationActions,
  useAcceptRecommendation,
  useDismissRecommendation,
  useSnoozeRecommendation,
} from "@/features/analytics/api/use-analytics";

const mockUseActions = vi.mocked(useRecommendationActions);
const mockAccept = vi.mocked(useAcceptRecommendation);
const mockDismiss = vi.mocked(useDismissRecommendation);
const mockSnooze = vi.mocked(useSnoozeRecommendation);

const { RecommendationActionCenter } = await import("./recommendation-action-center");

const WORKSPACE = "ws-test-1";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeAction(overrides: Partial<RecommendationActionsListOut["accepted"][0]> = {}) {
  return {
    id: "act-1",
    recommendation_id: "rec-aaaa-1111",
    action_type: "accepted",
    status: "accepted",
    reason: null,
    snooze_until: null,
    created_at: "2026-06-26T10:00:00Z",
    updated_at: "2026-06-26T10:00:00Z",
    ...overrides,
  };
}

const emptyList: RecommendationActionsListOut = {
  accepted: [],
  dismissed: [],
  snoozed: [],
  completed: [],
  expired: [],
  total: 0,
};

function setupMutations() {
  const acceptMutate = vi.fn();
  const dismissMutate = vi.fn();
  const snoozeMutate = vi.fn();
  mockAccept.mockReturnValue({ mutate: acceptMutate, isPending: false } as ReturnType<typeof useAcceptRecommendation>);
  mockDismiss.mockReturnValue({ mutate: dismissMutate, isPending: false } as ReturnType<typeof useDismissRecommendation>);
  mockSnooze.mockReturnValue({ mutate: snoozeMutate, isPending: false } as ReturnType<typeof useSnoozeRecommendation>);
  return { acceptMutate, dismissMutate, snoozeMutate };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RecommendationActionCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Root presence ─────────────────────────────────────────────────────────

  it("renders the root container", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("recommendation-action-center")).not.toBeNull();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it("shows skeleton while loading", () => {
    mockUseActions.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("action-center-skeleton")).not.toBeNull();
  });

  it("does not render sections while loading", () => {
    mockUseActions.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.queryByTestId("pending-section")).toBeNull();
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it("shows error banner on fetch failure", () => {
    mockUseActions.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("action-center-error")).not.toBeNull();
  });

  // ── Empty states ──────────────────────────────────────────────────────────

  it("shows pending empty state when no expired actions", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("pending-empty")).not.toBeNull();
    expect(screen.getByText("No pending recommendations.")).not.toBeNull();
  });

  it("shows accepted empty state when no accepted actions", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("accepted-empty")).not.toBeNull();
    expect(screen.getByText("No accepted recommendations.")).not.toBeNull();
  });

  it("shows dismissed empty state when no dismissed actions", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("dismissed-empty")).not.toBeNull();
  });

  it("shows snoozed empty state when no snoozed actions", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("snoozed-empty")).not.toBeNull();
  });

  it("shows timeline empty state when no history", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("timeline-empty")).not.toBeNull();
  });

  // ── Section structure ─────────────────────────────────────────────────────

  it("renders all 5 section headings", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("pending-section")).not.toBeNull();
    expect(screen.getByTestId("accepted-section")).not.toBeNull();
    expect(screen.getByTestId("dismissed-section")).not.toBeNull();
    expect(screen.getByTestId("snoozed-section")).not.toBeNull();
    expect(screen.getByTestId("timeline-section")).not.toBeNull();
  });

  // ── Accepted table ────────────────────────────────────────────────────────

  it("renders accepted table when accepted actions present", () => {
    const data = { ...emptyList, accepted: [makeAction()], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("accepted-table")).not.toBeNull();
    expect(screen.getByTestId("action-row-rec-aaaa-1111")).not.toBeNull();
  });

  it("does not render accepted table when bucket is empty", () => {
    mockUseActions.mockReturnValue({ data: emptyList, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.queryByTestId("accepted-table")).toBeNull();
  });

  // ── Dismissed table ───────────────────────────────────────────────────────

  it("renders dismissed table with reason", () => {
    const dismissedAction = makeAction({
      action_type: "dismissed",
      status: "dismissed",
      reason: "Not relevant",
      id: "act-2",
      recommendation_id: "rec-bbbb-2222",
    });
    const data = { ...emptyList, dismissed: [dismissedAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("dismissed-table")).not.toBeNull();
    expect(screen.getByText("Not relevant")).not.toBeNull();
  });

  // ── Snoozed table ─────────────────────────────────────────────────────────

  it("renders snoozed table with resume date", () => {
    const snoozedAction = makeAction({
      action_type: "snoozed",
      status: "snoozed",
      snooze_until: "2026-08-15",
      id: "act-3",
      recommendation_id: "rec-cccc-3333",
    });
    const data = { ...emptyList, snoozed: [snoozedAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("snoozed-table")).not.toBeNull();
  });

  // ── Expired in pending section ────────────────────────────────────────────

  it("shows expired actions as pending cards", () => {
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      snooze_until: "2025-01-01",
      id: "act-4",
      recommendation_id: "rec-dddd-4444",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("pending-card-rec-dddd-4444")).not.toBeNull();
  });

  // ── Accept button ─────────────────────────────────────────────────────────

  it("calls accept mutation when Accept button clicked on expired card", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-5",
      recommendation_id: "rec-eeee-5555",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    const { acceptMutate } = setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("accept-btn-rec-eeee-5555"));
    expect(acceptMutate).toHaveBeenCalledWith("rec-eeee-5555");
  });

  // ── Dismiss dialog ────────────────────────────────────────────────────────

  it("opens dismiss dialog when Dismiss button clicked", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-6",
      recommendation_id: "rec-ffff-6666",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("dismiss-btn-rec-ffff-6666"));
    expect(screen.getByTestId("dismiss-dialog")).not.toBeNull();
  });

  it("shows dismiss reason input in dialog", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-7",
      recommendation_id: "rec-gggg-7777",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("dismiss-btn-rec-gggg-7777"));
    expect(screen.getByTestId("dismiss-reason-input")).not.toBeNull();
  });

  it("calls dismiss mutation with reason on confirm", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-8",
      recommendation_id: "rec-hhhh-8888",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    const { dismissMutate } = setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("dismiss-btn-rec-hhhh-8888"));
    const input = screen.getByTestId("dismiss-reason-input");
    await user.clear(input);
    await user.type(input, "Old news");
    await user.click(screen.getByTestId("dismiss-confirm-btn"));
    expect(dismissMutate).toHaveBeenCalledWith(
      expect.objectContaining({ recommendationId: "rec-hhhh-8888", reason: "Old news" }),
      expect.any(Object),
    );
  });

  // ── Snooze dialog ─────────────────────────────────────────────────────────

  it("opens snooze dialog when Snooze button clicked", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-9",
      recommendation_id: "rec-iiii-9999",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("snooze-btn-rec-iiii-9999"));
    expect(screen.getByTestId("snooze-dialog")).not.toBeNull();
  });

  it("shows snooze date input in dialog", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-10",
      recommendation_id: "rec-jjjj-aaaa",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("snooze-btn-rec-jjjj-aaaa"));
    expect(screen.getByTestId("snooze-until-input")).not.toBeNull();
  });

  it("calls snooze mutation with date on confirm", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-11",
      recommendation_id: "rec-kkkk-bbbb",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    const { snoozeMutate } = setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("snooze-btn-rec-kkkk-bbbb"));
    await user.click(screen.getByTestId("snooze-confirm-btn"));
    expect(snoozeMutate).toHaveBeenCalledWith(
      expect.objectContaining({ recommendationId: "rec-kkkk-bbbb" }),
      expect.any(Object),
    );
  });

  // ── Timeline ──────────────────────────────────────────────────────────────

  it("renders timeline list when accepted actions exist", () => {
    const data = { ...emptyList, accepted: [makeAction()], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("timeline-list")).not.toBeNull();
  });

  it("renders timeline item for accepted action", () => {
    const action = makeAction({ id: "act-tl-1" });
    const data = { ...emptyList, accepted: [action], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("timeline-item-act-tl-1")).not.toBeNull();
  });

  it("timeline includes dismissed actions", () => {
    const d = makeAction({ id: "act-tl-d", action_type: "dismissed", status: "dismissed", recommendation_id: "rec-tl-d" });
    const data = { ...emptyList, dismissed: [d], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("timeline-item-act-tl-d")).not.toBeNull();
  });

  it("timeline includes completed actions", () => {
    const c = makeAction({ id: "act-tl-c", action_type: "completed", status: "completed", recommendation_id: "rec-tl-c" });
    const data = { ...emptyList, completed: [c], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getByTestId("timeline-item-act-tl-c")).not.toBeNull();
  });

  // ── No auto-campaign constraint ───────────────────────────────────────────

  it("Accept button triggers mutation only — no campaign creation side effect in component", async () => {
    const user = userEvent.setup();
    const expiredAction = makeAction({
      action_type: "snoozed",
      status: "expired",
      id: "act-no-campaign",
      recommendation_id: "rec-no-campaign",
    });
    const data = { ...emptyList, expired: [expiredAction], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    const { acceptMutate } = setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    await user.click(screen.getByTestId("accept-btn-rec-no-campaign"));
    // Only the mutation was called — no other side effects
    expect(acceptMutate).toHaveBeenCalledTimes(1);
    expect(acceptMutate).toHaveBeenCalledWith("rec-no-campaign");
  });

  // ── Status badge display ──────────────────────────────────────────────────

  it("displays status badge in accepted row", () => {
    const data = { ...emptyList, accepted: [makeAction()], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    const row = screen.getByTestId("action-row-rec-aaaa-1111");
    expect(row.textContent).toContain("accepted");
  });

  it("null reason shows dash in row", () => {
    const data = { ...emptyList, accepted: [makeAction({ reason: null })], total: 1 };
    mockUseActions.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useRecommendationActions>);
    setupMutations();
    render(<RecommendationActionCenter workspaceId={WORKSPACE} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
