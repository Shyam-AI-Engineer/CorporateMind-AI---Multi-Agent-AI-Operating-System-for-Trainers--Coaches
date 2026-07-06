import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TrainingFeedback, TrainingFeedbackListOut } from "@/features/training/types";

// ── Mocks ──────────────────────────────────────────────────────────────────────

vi.mock("@/features/training/api/use-training", () => ({
  useFeedbackList: vi.fn(),
  useCreateFeedback: vi.fn(),
  useUpdateFeedback: vi.fn(),
  useCustomerFeedback: vi.fn(),
}));

import {
  useFeedbackList,
  useCreateFeedback,
  useUpdateFeedback,
  useCustomerFeedback,
} from "@/features/training/api/use-training";

const mockFeedbackList = vi.mocked(useFeedbackList);
const mockCreateFeedback = vi.mocked(useCreateFeedback);
const mockUpdateFeedback = vi.mocked(useUpdateFeedback);
const mockCustomerFeedback = vi.mocked(useCustomerFeedback);

const { FeedbackCenter } = await import("./feedback-center");

// ── Fixtures ───────────────────────────────────────────────────────────────────

const SESSION_ID = "session-111";
const WORKSPACE_ID = "ws-222";
const CUSTOMER_ID = "cust-333";
const FEEDBACK_ID = "fb-444";
const ATTENDANCE_ID = "att-555";

function makeFeedback(overrides: Partial<TrainingFeedback> = {}): TrainingFeedback {
  return {
    id: FEEDBACK_ID,
    tenant_id: "tenant-1",
    workspace_id: WORKSPACE_ID,
    attendance_id: ATTENDANCE_ID,
    session_id: SESSION_ID,
    customer_id: CUSTOMER_ID,
    trainer_id: null,
    overall_rating: 4,
    trainer_rating: 5,
    content_rating: 3,
    materials_rating: null,
    venue_rating: null,
    would_recommend: true,
    comments: "Very helpful session",
    submitted_at: "2026-07-05T10:00:00Z",
    created_at: "2026-07-05T10:00:00Z",
    updated_at: "2026-07-05T10:00:00Z",
    ...overrides,
  };
}

function makeListData(
  items: TrainingFeedback[],
  overrides: Partial<TrainingFeedbackListOut> = {}
) {
  const listOut: TrainingFeedbackListOut = {
    items,
    next_cursor: null,
    has_more: false,
    total: items.length,
    ...overrides,
  };
  return { data: { data: listOut } };
}

function noopMutation() {
  return { mutate: vi.fn(), isPending: false };
}

function setupDefaults(items: TrainingFeedback[] = [], overrides = {}) {
  mockFeedbackList.mockReturnValue(makeListData(items, overrides) as any);
  mockCreateFeedback.mockReturnValue(noopMutation() as any);
  mockUpdateFeedback.mockReturnValue(noopMutation() as any);
}

// ── Loading / error / empty states ─────────────────────────────────────────────

describe("FeedbackCenter — loading and error states", () => {
  beforeEach(() => {
    mockCreateFeedback.mockReturnValue(noopMutation() as any);
    mockUpdateFeedback.mockReturnValue(noopMutation() as any);
  });

  it("shows loading-state while data is loading", () => {
    mockFeedbackList.mockReturnValue({ data: undefined, isLoading: true, isError: false } as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("loading-state")).not.toBeNull();
  });

  it("hides table while loading", () => {
    mockFeedbackList.mockReturnValue({ data: undefined, isLoading: true, isError: false } as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.queryByTestId("feedback-table")).toBeNull();
  });

  it("shows error-state when query errors", () => {
    mockFeedbackList.mockReturnValue({ data: undefined, isLoading: false, isError: true } as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("error-state")).not.toBeNull();
  });

  it("shows empty-row when items list is empty", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("empty-row")).not.toBeNull();
  });

  it("does not show loading-state when loaded", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.queryByTestId("loading-state")).toBeNull();
  });
});

// ── KPI cards ─────────────────────────────────────────────────────────────────

describe("FeedbackCenter — KPI cards", () => {
  it("renders kpi-total with correct count", () => {
    setupDefaults([makeFeedback(), makeFeedback({ id: "fb-2" })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-total").textContent).toContain("2");
  });

  it("renders kpi-avg-rating for single item with rating 4", () => {
    setupDefaults([makeFeedback({ overall_rating: 4 })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-avg-rating").textContent).toContain("4.0");
  });

  it("renders avg rating dash when all items have null rating", () => {
    setupDefaults([makeFeedback({ overall_rating: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-avg-rating").textContent).toContain("—");
  });

  it("renders kpi-recommend-rate as 100% when all recommend", () => {
    setupDefaults([makeFeedback({ would_recommend: true }), makeFeedback({ id: "fb-2", would_recommend: true })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-recommend-rate").textContent).toContain("100%");
  });

  it("renders kpi-recommend-rate as 0% when none recommend", () => {
    setupDefaults([makeFeedback({ would_recommend: false })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-recommend-rate").textContent).toContain("0%");
  });

  it("renders kpi-recommend-rate dash when no items", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-recommend-rate").textContent).toContain("—");
  });

  it("renders kpi-with-comments count correctly", () => {
    setupDefaults([
      makeFeedback({ comments: "great" }),
      makeFeedback({ id: "fb-2", comments: null }),
      makeFeedback({ id: "fb-3", comments: "good" }),
    ]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-with-comments").textContent).toContain("2");
  });

  it("shows 0 with-comments when no comments", () => {
    setupDefaults([makeFeedback({ comments: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-with-comments").textContent).toContain("0");
  });

  it("kpi-total reflects data.total not items length", () => {
    setupDefaults([makeFeedback()], { total: 42 });
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-total").textContent).toContain("42");
  });
});

// ── Toolbar ────────────────────────────────────────────────────────────────────

describe("FeedbackCenter — toolbar", () => {
  it("renders search-input", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("search-input")).not.toBeNull();
  });

  it("renders filter-min-rating select", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("filter-min-rating")).not.toBeNull();
  });

  it("renders btn-add-feedback button", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("btn-add-feedback")).not.toBeNull();
  });

  it("typing in search-input updates value", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    const input = screen.getByTestId("search-input");
    await userEvent.type(input, "excellent");
    expect((input as HTMLInputElement).value).toBe("excellent");
  });

  it("changing min-rating select updates value", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    const select = screen.getByTestId("filter-min-rating");
    await userEvent.selectOptions(select, "4");
    expect((select as HTMLInputElement).value).toBe("4");
  });
});

// ── Feedback table rows ────────────────────────────────────────────────────────

describe("FeedbackCenter — table rows", () => {
  it("renders feedback-row for each item", () => {
    setupDefaults([makeFeedback(), makeFeedback({ id: "fb-2" })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("feedback-row")).toHaveLength(2);
  });

  it("renders rating-stars for overall_rating", () => {
    setupDefaults([makeFeedback({ overall_rating: 4 })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("rating-stars").length).toBeGreaterThan(0);
  });

  it("renders rating-null when overall_rating is null", () => {
    setupDefaults([makeFeedback({ overall_rating: null, trainer_rating: null, content_rating: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("rating-null").length).toBeGreaterThan(0);
  });

  it("renders recommend-yes badge for would_recommend=true", () => {
    setupDefaults([makeFeedback({ would_recommend: true })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-yes")).not.toBeNull();
  });

  it("renders recommend-no badge for would_recommend=false", () => {
    setupDefaults([makeFeedback({ would_recommend: false })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-no")).not.toBeNull();
  });

  it("renders recommend-null badge for would_recommend=null", () => {
    setupDefaults([makeFeedback({ would_recommend: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-null")).not.toBeNull();
  });

  it("renders feedback-table element", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-table")).not.toBeNull();
  });

  it("clicking a feedback-row opens drawer", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("feedback-drawer")).not.toBeNull();
  });
});

// ── Pagination ─────────────────────────────────────────────────────────────────

describe("FeedbackCenter — pagination", () => {
  it("shows btn-load-more when has_more is true", () => {
    setupDefaults([makeFeedback()], { has_more: true, next_cursor: "cursor-xyz" });
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("btn-load-more")).not.toBeNull();
  });

  it("does not show btn-load-more when has_more is false", () => {
    setupDefaults([makeFeedback()], { has_more: false });
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.queryByTestId("btn-load-more")).toBeNull();
  });

  it("does not show btn-load-more for empty list", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.queryByTestId("btn-load-more")).toBeNull();
  });
});

// ── Create dialog ─────────────────────────────────────────────────────────────

describe("FeedbackCenter — create dialog", () => {
  it("create dialog not visible initially", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.queryByTestId("create-feedback-dialog")).toBeNull();
  });

  it("clicking btn-add-feedback opens create dialog", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    expect(screen.getByTestId("create-feedback-dialog")).not.toBeNull();
  });

  it("clicking btn-cancel-create closes dialog", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.click(screen.getByTestId("btn-cancel-create"));
    expect(screen.queryByTestId("create-feedback-dialog")).toBeNull();
  });

  it("shows create-error when attendance_id is empty and submit clicked", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.click(screen.getByTestId("btn-submit-feedback"));
    expect(screen.getByTestId("create-error")).not.toBeNull();
  });

  it("shows create-error when customer_id is empty", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-attendance-id"), ATTENDANCE_ID);
    await userEvent.click(screen.getByTestId("btn-submit-feedback"));
    expect(screen.getByTestId("create-error")).not.toBeNull();
  });

  it("no error shown before submit", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    expect(screen.queryByTestId("create-error")).toBeNull();
  });

  it("can fill in attendance_id field", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-attendance-id"), ATTENDANCE_ID);
    expect((screen.getByTestId("input-attendance-id") as HTMLInputElement).value).toBe(ATTENDANCE_ID);
  });

  it("can fill in customer_id field", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-customer-id"), CUSTOMER_ID);
    expect((screen.getByTestId("input-customer-id") as HTMLInputElement).value).toBe(CUSTOMER_ID);
  });

  it("can select overall rating", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.selectOptions(screen.getByTestId("select-overall-rating"), "5");
    expect((screen.getByTestId("select-overall-rating") as HTMLInputElement).value).toBe("5");
  });

  it("can select would-recommend", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.selectOptions(screen.getByTestId("select-would-recommend"), "yes");
    expect((screen.getByTestId("select-would-recommend") as HTMLInputElement).value).toBe("yes");
  });

  it("can type comments in create dialog", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-comments"), "Excellent");
    expect((screen.getByTestId("input-comments") as HTMLInputElement).value).toBe("Excellent");
  });

  it("calls mutate on valid form submit", async () => {
    const mutateFn = vi.fn();
    mockFeedbackList.mockReturnValue(makeListData([]) as any);
    mockCreateFeedback.mockReturnValue({ mutate: mutateFn, isPending: false } as any);
    mockUpdateFeedback.mockReturnValue(noopMutation() as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-attendance-id"), ATTENDANCE_ID);
    await userEvent.type(screen.getByTestId("input-customer-id"), CUSTOMER_ID);
    await userEvent.click(screen.getByTestId("btn-submit-feedback"));
    expect(mutateFn).toHaveBeenCalledOnce();
  });

  it("mutate called with correct session_id", async () => {
    const mutateFn = vi.fn();
    mockFeedbackList.mockReturnValue(makeListData([]) as any);
    mockCreateFeedback.mockReturnValue({ mutate: mutateFn, isPending: false } as any);
    mockUpdateFeedback.mockReturnValue(noopMutation() as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.type(screen.getByTestId("input-attendance-id"), ATTENDANCE_ID);
    await userEvent.type(screen.getByTestId("input-customer-id"), CUSTOMER_ID);
    await userEvent.click(screen.getByTestId("btn-submit-feedback"));
    expect(mutateFn.mock.calls[0][0].session_id).toBe(SESSION_ID);
  });

  it("can select trainer rating in create dialog", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.selectOptions(screen.getByTestId("select-trainer-rating"), "3");
    expect((screen.getByTestId("select-trainer-rating") as HTMLInputElement).value).toBe("3");
  });

  it("can select content rating in create dialog", async () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("btn-add-feedback"));
    await userEvent.selectOptions(screen.getByTestId("select-content-rating"), "2");
    expect((screen.getByTestId("select-content-rating") as HTMLInputElement).value).toBe("2");
  });
});

// ── Feedback drawer — view mode ────────────────────────────────────────────────

describe("FeedbackCenter — drawer view mode", () => {
  it("opens drawer with feedback-drawer testid", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("feedback-drawer")).not.toBeNull();
  });

  it("drawer shows overall rating via rating-stars", async () => {
    setupDefaults([makeFeedback({ overall_rating: 5 })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-overall-rating")).not.toBeNull();
  });

  it("drawer shows trainer rating", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-trainer-rating")).not.toBeNull();
  });

  it("drawer shows content rating", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-content-rating")).not.toBeNull();
  });

  it("drawer shows materials rating", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-materials-rating")).not.toBeNull();
  });

  it("drawer shows would-recommend badge", async () => {
    setupDefaults([makeFeedback({ would_recommend: true })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-would-recommend")).not.toBeNull();
  });

  it("drawer shows comments when present", async () => {
    setupDefaults([makeFeedback({ comments: "Awesome!" })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-comments").textContent).toContain("Awesome!");
  });

  it("drawer shows submitted_at date", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("drawer-submitted-at")).not.toBeNull();
  });

  it("drawer shows btn-edit-feedback button", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    expect(screen.getByTestId("btn-edit-feedback")).not.toBeNull();
  });

  it("clicking drawer-close closes drawer", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("feedback-drawer")).toBeNull();
  });
});

// ── Feedback drawer — edit mode ────────────────────────────────────────────────

describe("FeedbackCenter — drawer edit mode", () => {
  it("clicking btn-edit-feedback enters edit mode", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("edit-overall-rating")).not.toBeNull();
  });

  it("edit mode shows edit-trainer-rating select", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("edit-trainer-rating")).not.toBeNull();
  });

  it("edit mode shows edit-content-rating select", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("edit-content-rating")).not.toBeNull();
  });

  it("edit mode shows edit-would-recommend select", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("edit-would-recommend")).not.toBeNull();
  });

  it("edit mode shows edit-comments textarea", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("edit-comments")).not.toBeNull();
  });

  it("edit mode pre-fills comments from feedback", async () => {
    setupDefaults([makeFeedback({ comments: "Pre-existing comment" })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect((screen.getByTestId("edit-comments") as HTMLInputElement).value).toBe("Pre-existing comment");
  });

  it("clicking btn-cancel-edit returns to view mode", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    await userEvent.click(screen.getByTestId("btn-cancel-edit"));
    expect(screen.queryByTestId("edit-overall-rating")).toBeNull();
    expect(screen.getByTestId("btn-edit-feedback")).not.toBeNull();
  });

  it("clicking btn-save-feedback calls update mutate", async () => {
    const mutateFn = vi.fn();
    mockFeedbackList.mockReturnValue(makeListData([makeFeedback()]) as any);
    mockCreateFeedback.mockReturnValue(noopMutation() as any);
    mockUpdateFeedback.mockReturnValue({ mutate: mutateFn, isPending: false } as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    await userEvent.click(screen.getByTestId("btn-save-feedback"));
    expect(mutateFn).toHaveBeenCalledOnce();
  });

  it("save passes correct feedback id", async () => {
    const mutateFn = vi.fn();
    mockFeedbackList.mockReturnValue(makeListData([makeFeedback({ id: "fb-special" })]) as any);
    mockCreateFeedback.mockReturnValue(noopMutation() as any);
    mockUpdateFeedback.mockReturnValue({ mutate: mutateFn, isPending: false } as any);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    await userEvent.click(screen.getByTestId("btn-save-feedback"));
    expect(mutateFn.mock.calls[0][0].id).toBe("fb-special");
  });

  it("can change comments in edit mode", async () => {
    setupDefaults([makeFeedback({ comments: "Old" })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    await userEvent.clear(screen.getByTestId("edit-comments"));
    await userEvent.type(screen.getByTestId("edit-comments"), "New comment");
    expect((screen.getByTestId("edit-comments") as HTMLInputElement).value).toBe("New comment");
  });

  it("edit mode shows btn-save-feedback", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("btn-save-feedback")).not.toBeNull();
  });

  it("edit mode shows btn-cancel-edit", async () => {
    setupDefaults([makeFeedback()]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    await userEvent.click(screen.getByTestId("feedback-row"));
    await userEvent.click(screen.getByTestId("btn-edit-feedback"));
    expect(screen.getByTestId("btn-cancel-edit")).not.toBeNull();
  });
});

// ── Rating components ──────────────────────────────────────────────────────────

describe("RatingStars and RecommendBadge", () => {
  it("rating-stars shown for rated row", () => {
    setupDefaults([makeFeedback({ overall_rating: 3 })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    const stars = screen.getAllByTestId("rating-stars");
    expect(stars.length).toBeGreaterThan(0);
  });

  it("recommend-yes renders Yes text", () => {
    setupDefaults([makeFeedback({ would_recommend: true })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-yes").textContent).toContain("Yes");
  });

  it("recommend-no renders No text", () => {
    setupDefaults([makeFeedback({ would_recommend: false })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-no").textContent).toContain("No");
  });

  it("rating-null shown when overall_rating is null", () => {
    setupDefaults([makeFeedback({ overall_rating: null, trainer_rating: null, content_rating: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("rating-null").length).toBeGreaterThan(0);
  });

  it("recommend-null shows dash text", () => {
    setupDefaults([makeFeedback({ would_recommend: null })]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("recommend-null").textContent).toContain("—");
  });
});

// ── Session tab integration ────────────────────────────────────────────────────

describe("FeedbackCenter — session tab integration", () => {
  it("renders without crashing when customerId prop not passed", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-table")).not.toBeNull();
  });

  it("renders with customerId prop", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} customerId={CUSTOMER_ID} />);
    expect(screen.getByTestId("feedback-table")).not.toBeNull();
  });

  it("useFeedbackList called with session_id", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(mockFeedbackList).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: SESSION_ID })
    );
  });

  it("useFeedbackList called with workspace_id", () => {
    setupDefaults([]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(mockFeedbackList).toHaveBeenCalledWith(
      expect.objectContaining({ workspace_id: WORKSPACE_ID })
    );
  });

  it("multiple feedback rows rendered correctly", () => {
    setupDefaults([
      makeFeedback(),
      makeFeedback({ id: "fb-2" }),
      makeFeedback({ id: "fb-3" }),
    ]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("feedback-row")).toHaveLength(3);
  });

  it("avg rating computed across multiple items", () => {
    setupDefaults([
      makeFeedback({ overall_rating: 4 }),
      makeFeedback({ id: "fb-2", overall_rating: 2 }),
    ]);
    render(<FeedbackCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("kpi-avg-rating").textContent).toContain("3.0");
  });
});

// ── Customer feedback history ──────────────────────────────────────────────────

describe("CustomerFeedbackHistory", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows feedback-history-loading when loading", async () => {
    mockCustomerFeedback.mockReturnValue({ data: undefined, isLoading: true, isError: false } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-history-loading")).not.toBeNull();
  });

  it("shows feedback-history-empty when no items", async () => {
    mockCustomerFeedback.mockReturnValue({ data: { data: [] }, isLoading: false, isError: false } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-history-empty")).not.toBeNull();
  });

  it("shows feedback-history-list when items present", async () => {
    mockCustomerFeedback.mockReturnValue({
      data: { data: [makeFeedback()] }, isLoading: false, isError: false,
    } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-history-list")).not.toBeNull();
  });

  it("renders feedback-history-item for each feedback", async () => {
    mockCustomerFeedback.mockReturnValue({
      data: { data: [makeFeedback(), makeFeedback({ id: "fb-2" })] }, isLoading: false, isError: false,
    } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getAllByTestId("feedback-history-item")).toHaveLength(2);
  });

  it("shows feedback-history-comment when comments present", async () => {
    mockCustomerFeedback.mockReturnValue({
      data: { data: [makeFeedback({ comments: "Great!" })] }, isLoading: false, isError: false,
    } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("feedback-history-comment").textContent).toContain("Great!");
  });

  it("wraps content in customer-feedback-history container", async () => {
    mockCustomerFeedback.mockReturnValue({
      data: { data: [] }, isLoading: false, isError: false,
    } as any);
    const { CustomerFeedbackHistory } = await import("@/features/customers/ui/customer-center");
    render(<CustomerFeedbackHistory customerId={CUSTOMER_ID} workspaceId={WORKSPACE_ID} />);
    expect(screen.getByTestId("customer-feedback-history")).not.toBeNull();
  });
});
