import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TrainingSession } from "@/features/training/types";
import { SESSION_STATUSES } from "@/features/training/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/training/api/use-training", () => ({
  useCreateTrainingSession: vi.fn(),
  useUpdateTrainingSession: vi.fn(),
  useStartSession: vi.fn(),
  useCompleteSession: vi.fn(),
  useCancelSession: vi.fn(),
  useAssignSessionTrainer: vi.fn(),
  useEngagementSessions: vi.fn(),
}));

import {
  useCreateTrainingSession,
  useUpdateTrainingSession,
  useStartSession,
  useCompleteSession,
  useCancelSession,
  useAssignSessionTrainer,
  useEngagementSessions,
} from "@/features/training/api/use-training";

const mockCreate = vi.mocked(useCreateTrainingSession);
const mockUpdate = vi.mocked(useUpdateTrainingSession);
const mockStart = vi.mocked(useStartSession);
const mockComplete = vi.mocked(useCompleteSession);
const mockCancel = vi.mocked(useCancelSession);
const mockAssign = vi.mocked(useAssignSessionTrainer);
const mockEngagementSessions = vi.mocked(useEngagementSessions);

const { TrainingSessionCenter } = await import("./training-session-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS = "ws-sprint43";
const ENG = "eng-sprint43";

function makeSession(overrides: Partial<TrainingSession> = {}): TrainingSession {
  return {
    id: "sess-1",
    tenant_id: "org-1",
    workspace_id: WS,
    engagement_id: ENG,
    session_name: "Day 1 Morning",
    session_number: 1,
    status: "planned",
    scheduled_start: null,
    scheduled_end: null,
    actual_start: null,
    actual_end: null,
    trainer_id: null,
    location: null,
    meeting_link: null,
    capacity: 30,
    expected_attendees: 25,
    actual_attendees: null,
    notes: null,
    created_at: "2026-07-04T09:00:00Z",
    updated_at: "2026-07-04T09:00:00Z",
    ...overrides,
  };
}

function setupMutations() {
  const createMutate = vi.fn().mockResolvedValue({ data: makeSession() });
  const updateMutate = vi.fn().mockResolvedValue({ data: makeSession() });
  const startMutate = vi.fn();
  const completeMutate = vi.fn().mockResolvedValue({ data: makeSession({ status: "completed" }) });
  const cancelMutate = vi.fn().mockResolvedValue({ data: makeSession({ status: "cancelled" }) });
  const assignMutate = vi.fn().mockResolvedValue({ data: makeSession({ trainer_id: "trainer-1" }) });

  mockCreate.mockReturnValue({ mutateAsync: createMutate, isPending: false } as ReturnType<typeof useCreateTrainingSession>);
  mockUpdate.mockReturnValue({ mutateAsync: updateMutate, isPending: false } as ReturnType<typeof useUpdateTrainingSession>);
  mockStart.mockReturnValue({ mutate: startMutate, isPending: false } as ReturnType<typeof useStartSession>);
  mockComplete.mockReturnValue({ mutateAsync: completeMutate, isPending: false } as ReturnType<typeof useCompleteSession>);
  mockCancel.mockReturnValue({ mutateAsync: cancelMutate, isPending: false } as ReturnType<typeof useCancelSession>);
  mockAssign.mockReturnValue({ mutateAsync: assignMutate, isPending: false } as ReturnType<typeof useAssignSessionTrainer>);

  return { createMutate, updateMutate, startMutate, completeMutate, cancelMutate, assignMutate };
}

function setupSessions(sessions: TrainingSession[], opts: { isLoading?: boolean; isError?: boolean } = {}) {
  mockEngagementSessions.mockReturnValue({
    data: { data: sessions },
    isLoading: opts.isLoading ?? false,
    isError: opts.isError ?? false,
  } as ReturnType<typeof useEngagementSessions>);
}

// ── TrainingSessionCenter ─────────────────────────────────────────────────────

describe("TrainingSessionCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading / error / empty states ─────────────────────────────────────────

  it("renders loading state", () => {
    setupMutations();
    setupSessions([], { isLoading: true });
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-loading")).not.toBeNull();
  });

  it("renders error state", () => {
    setupMutations();
    setupSessions([], { isError: true });
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-error")).not.toBeNull();
  });

  it("renders empty state when no sessions", () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-empty")).not.toBeNull();
  });

  it("renders session table when sessions exist", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-table")).not.toBeNull();
  });

  it("renders session center root element", () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("training-session-center")).not.toBeNull();
  });

  it("does not render loading or error in success state", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.queryByTestId("session-loading")).toBeNull();
    expect(screen.queryByTestId("session-error")).toBeNull();
  });

  // ── KPI cards ──────────────────────────────────────────────────────────────

  it("renders KPI cards when sessions exist", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-kpis")).not.toBeNull();
  });

  it("shows correct planned count in KPI", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "planned" }),
      makeSession({ id: "s2", status: "planned" }),
      makeSession({ id: "s3", status: "completed" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const kpi = screen.getByTestId("kpi-planned");
    expect(kpi.textContent).toContain("2");
  });

  it("shows correct scheduled count in KPI", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "scheduled" }),
      makeSession({ id: "s2", status: "planned" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const kpi = screen.getByTestId("kpi-scheduled");
    expect(kpi.textContent).toContain("1");
  });

  it("shows correct in-progress count in KPI", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "in_progress" }),
      makeSession({ id: "s2", status: "in_progress" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const kpi = screen.getByTestId("kpi-in-progress");
    expect(kpi.textContent).toContain("2");
  });

  it("shows correct completed count in KPI", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "completed" }),
      makeSession({ id: "s2", status: "cancelled" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const kpi = screen.getByTestId("kpi-completed");
    expect(kpi.textContent).toContain("1");
  });

  it("shows zero planned when no planned sessions", () => {
    setupMutations();
    setupSessions([makeSession({ status: "completed" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const kpi = screen.getByTestId("kpi-planned");
    expect(kpi.textContent).toContain("0");
  });

  // ── Session table rows ──────────────────────────────────────────────────────

  it("renders a row for each session", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1" }),
      makeSession({ id: "s2", session_name: "Day 2" }),
      makeSession({ id: "s3", session_name: "Day 3" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-row-s1")).not.toBeNull();
    expect(screen.getByTestId("session-row-s2")).not.toBeNull();
    expect(screen.getByTestId("session-row-s3")).not.toBeNull();
  });

  it("shows session name in table row", () => {
    setupMutations();
    setupSessions([makeSession({ session_name: "Afternoon Breakout" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByText("Afternoon Breakout")).not.toBeNull();
  });

  it("shows dash for null session_number", () => {
    setupMutations();
    setupSessions([makeSession({ session_number: null })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows session number when provided", () => {
    setupMutations();
    setupSessions([makeSession({ session_number: 3 })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByText("3")).not.toBeNull();
  });

  // ── Status badges ───────────────────────────────────────────────────────────

  it("renders planned status badge", () => {
    setupMutations();
    setupSessions([makeSession({ status: "planned" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-status-planned")).not.toBeNull();
  });

  it("renders scheduled status badge", () => {
    setupMutations();
    setupSessions([makeSession({ status: "scheduled" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-status-scheduled")).not.toBeNull();
  });

  it("renders in_progress status badge", () => {
    setupMutations();
    setupSessions([makeSession({ status: "in_progress" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-status-in_progress")).not.toBeNull();
  });

  it("renders completed status badge", () => {
    setupMutations();
    setupSessions([makeSession({ status: "completed" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-status-completed")).not.toBeNull();
  });

  it("renders cancelled status badge", () => {
    setupMutations();
    setupSessions([makeSession({ status: "cancelled" })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-status-cancelled")).not.toBeNull();
  });

  it("all 5 status values are correctly typed", () => {
    const expected = ["planned", "scheduled", "in_progress", "completed", "cancelled"];
    expect(SESSION_STATUSES).toEqual(expected);
  });

  // ── Create session dialog ───────────────────────────────────────────────────

  it("shows create dialog when create button clicked", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    expect(screen.getByTestId("create-session-dialog")).not.toBeNull();
  });

  it("hides create dialog after cancel", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.click(screen.getByTestId("btn-cancel-create"));
    expect(screen.queryByTestId("create-session-dialog")).toBeNull();
  });

  it("create dialog has session name input", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    expect(screen.getByTestId("input-session-name")).not.toBeNull();
  });

  it("create dialog has status select with all 5 options", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    const select = screen.getByTestId("select-status") as HTMLSelectElement;
    expect(select.options.length).toBe(5);
  });

  it("create dialog shows error for empty session name on submit", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.click(screen.getByTestId("btn-submit-create"));
    expect(screen.getByTestId("create-error")).not.toBeNull();
  });

  it("create dialog calls mutateAsync on valid submit", async () => {
    const { createMutate } = setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.type(screen.getByTestId("input-session-name"), "Morning Session");
    await userEvent.click(screen.getByTestId("btn-submit-create"));
    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledOnce();
    });
  });

  it("create dialog passes correct body to mutateAsync", async () => {
    const { createMutate } = setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.type(screen.getByTestId("input-session-name"), "Day 1");
    await userEvent.click(screen.getByTestId("btn-submit-create"));
    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    const body = createMutate.mock.calls[0][0];
    expect(body.session_name).toBe("Day 1");
    expect(body.workspace_id).toBe(WS);
    expect(body.engagement_id).toBe(ENG);
  });

  it("create dialog shows error when mutateAsync throws", async () => {
    setupMutations();
    mockCreate.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error("API error")),
      isPending: false,
    } as ReturnType<typeof useCreateTrainingSession>);
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.type(screen.getByTestId("input-session-name"), "Session X");
    await userEvent.click(screen.getByTestId("btn-submit-create"));
    await waitFor(() => {
      expect(screen.getByTestId("create-error")).not.toBeNull();
    });
  });

  it("create dialog submit button is disabled while pending", async () => {
    setupMutations();
    mockCreate.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    } as ReturnType<typeof useCreateTrainingSession>);
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    const btn = screen.getByTestId("btn-submit-create") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("create dialog submit shows 'Creating…' while pending", async () => {
    setupMutations();
    mockCreate.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    } as ReturnType<typeof useCreateTrainingSession>);
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    expect(screen.getByTestId("btn-submit-create").textContent).toContain("Creating");
  });

  it("create dialog includes optional fields in body when filled", async () => {
    const { createMutate } = setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    await userEvent.type(screen.getByTestId("input-session-name"), "Day 2");
    await userEvent.type(screen.getByTestId("input-session-number"), "2");
    await userEvent.type(screen.getByTestId("input-location"), "Room B");
    await userEvent.click(screen.getByTestId("btn-submit-create"));
    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    const body = createMutate.mock.calls[0][0];
    expect(body.session_number).toBe(2);
    expect(body.location).toBe("Room B");
  });

  it("create dialog default status is planned", async () => {
    setupMutations();
    setupSessions([]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-create-session"));
    const select = screen.getByTestId("select-status") as HTMLSelectElement;
    expect(select.value).toBe("planned");
  });

  // ── Session row click → drawer ──────────────────────────────────────────────

  it("clicking a row opens the session drawer", async () => {
    setupMutations();
    const session = makeSession();
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("session-drawer")).not.toBeNull();
  });

  it("drawer shows the session name", async () => {
    setupMutations();
    const session = makeSession({ session_name: "Evening Wrap-up" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getAllByText("Evening Wrap-up").length).toBeGreaterThan(0);
  });

  it("drawer shows status badge", async () => {
    setupMutations();
    const session = makeSession({ status: "scheduled" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getAllByTestId("session-status-scheduled").length).toBeGreaterThan(0);
  });

  it("drawer closes when close button clicked", async () => {
    setupMutations();
    const session = makeSession();
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-close-drawer"));
    expect(screen.queryByTestId("session-drawer")).toBeNull();
  });

  it("drawer shows location when present", async () => {
    setupMutations();
    const session = makeSession({ location: "Training Room B" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("drawer-location").textContent).toBe("Training Room B");
  });

  it("drawer shows dash for null location", async () => {
    setupMutations();
    const session = makeSession({ location: null });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("drawer-location").textContent).toBe("—");
  });

  // ── Drawer action buttons ───────────────────────────────────────────────────

  it("drawer shows Start button for planned session", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-start-session")).not.toBeNull();
  });

  it("drawer shows Start button for scheduled session", async () => {
    setupMutations();
    const session = makeSession({ status: "scheduled" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-start-session")).not.toBeNull();
  });

  it("drawer shows Complete button for in-progress session", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-complete-session")).not.toBeNull();
  });

  it("drawer shows Cancel button for cancellable sessions (planned)", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-cancel-session")).not.toBeNull();
  });

  it("drawer shows Cancel button for cancellable sessions (in_progress)", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-cancel-session")).not.toBeNull();
  });

  it("drawer hides action buttons for completed session", async () => {
    setupMutations();
    const session = makeSession({ status: "completed" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.queryByTestId("btn-start-session")).toBeNull();
    expect(screen.queryByTestId("btn-complete-session")).toBeNull();
    expect(screen.queryByTestId("btn-cancel-session")).toBeNull();
  });

  it("drawer hides action buttons for cancelled session", async () => {
    setupMutations();
    const session = makeSession({ status: "cancelled" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.queryByTestId("btn-start-session")).toBeNull();
    expect(screen.queryByTestId("btn-cancel-session")).toBeNull();
  });

  it("drawer always shows Assign Trainer button", async () => {
    setupMutations();
    const session = makeSession({ status: "completed" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    expect(screen.getByTestId("btn-assign-trainer")).not.toBeNull();
  });

  // ── Start session action ────────────────────────────────────────────────────

  it("clicking Start button calls start.mutate", async () => {
    const { startMutate } = setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-start-session"));
    expect(startMutate).toHaveBeenCalledOnce();
  });

  it("start is called with correct session id and engagement id", async () => {
    const { startMutate } = setupMutations();
    const session = makeSession({ id: "sess-xyz", status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("session-row-sess-xyz"));
    await userEvent.click(screen.getByTestId("btn-start-session"));
    const args = startMutate.mock.calls[0][0];
    expect(args.id).toBe("sess-xyz");
    expect(args.engagementId).toBe(ENG);
  });

  it("start button is disabled while pending", async () => {
    setupMutations();
    mockStart.mockReturnValue({ mutate: vi.fn(), isPending: true } as ReturnType<typeof useStartSession>);
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    const btn = screen.getByTestId("btn-start-session") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  // ── Complete session dialog ─────────────────────────────────────────────────

  it("clicking Complete opens complete dialog", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    expect(screen.getByTestId("complete-session-dialog")).not.toBeNull();
  });

  it("complete dialog has actual attendees input", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    expect(screen.getByTestId("input-actual-attendees")).not.toBeNull();
  });

  it("complete dialog submits with attendees", async () => {
    const { completeMutate } = setupMutations();
    const session = makeSession({ id: "sess-ip", status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("session-row-sess-ip"));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    await userEvent.type(screen.getByTestId("input-actual-attendees"), "22");
    await userEvent.click(screen.getByTestId("btn-submit-complete"));
    await waitFor(() => expect(completeMutate).toHaveBeenCalled());
    const args = completeMutate.mock.calls[0][0];
    expect(args.id).toBe("sess-ip");
    expect(args.body.actual_attendees).toBe(22);
  });

  it("complete dialog has notes input", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    expect(screen.getByTestId("input-complete-notes")).not.toBeNull();
  });

  it("complete dialog cancel dismisses dialog", async () => {
    setupMutations();
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    await userEvent.click(screen.getByTestId("btn-cancel-complete"));
    expect(screen.queryByTestId("complete-session-dialog")).toBeNull();
  });

  it("complete submit disabled while pending", async () => {
    setupMutations();
    mockComplete.mockReturnValue({ mutateAsync: vi.fn(), isPending: true } as ReturnType<typeof useCompleteSession>);
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    const btn = screen.getByTestId("btn-submit-complete") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("complete submit shows 'Completing…' while pending", async () => {
    setupMutations();
    mockComplete.mockReturnValue({ mutateAsync: vi.fn(), isPending: true } as ReturnType<typeof useCompleteSession>);
    const session = makeSession({ status: "in_progress" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-complete-session"));
    expect(screen.getByTestId("btn-submit-complete").textContent).toContain("Completing");
  });

  // ── Cancel session dialog ───────────────────────────────────────────────────

  it("clicking Cancel opens cancel dialog", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    expect(screen.getByTestId("cancel-session-dialog")).not.toBeNull();
  });

  it("cancel dialog has notes input", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    expect(screen.getByTestId("input-cancel-notes")).not.toBeNull();
  });

  it("cancel dialog submits with notes", async () => {
    const { cancelMutate } = setupMutations();
    const session = makeSession({ id: "sess-pl", status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("session-row-sess-pl"));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    await userEvent.type(screen.getByTestId("input-cancel-notes"), "Venue conflict");
    await userEvent.click(screen.getByTestId("btn-submit-cancel"));
    await waitFor(() => expect(cancelMutate).toHaveBeenCalled());
    const args = cancelMutate.mock.calls[0][0];
    expect(args.id).toBe("sess-pl");
    expect(args.body.notes).toBe("Venue conflict");
  });

  it("cancel dialog back button dismisses dialog", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    await userEvent.click(screen.getByTestId("btn-cancel-cancel"));
    expect(screen.queryByTestId("cancel-session-dialog")).toBeNull();
  });

  it("cancel submit shows 'Cancelling…' while pending", async () => {
    setupMutations();
    mockCancel.mockReturnValue({ mutateAsync: vi.fn(), isPending: true } as ReturnType<typeof useCancelSession>);
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    expect(screen.getByTestId("btn-submit-cancel").textContent).toContain("Cancelling");
  });

  it("cancel submit disabled while pending", async () => {
    setupMutations();
    mockCancel.mockReturnValue({ mutateAsync: vi.fn(), isPending: true } as ReturnType<typeof useCancelSession>);
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-cancel-session"));
    const btn = screen.getByTestId("btn-submit-cancel") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  // ── Assign trainer dialog ───────────────────────────────────────────────────

  it("clicking Assign Trainer opens assign dialog", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-assign-trainer"));
    expect(screen.getByTestId("assign-trainer-dialog")).not.toBeNull();
  });

  it("assign trainer dialog submits with trainer id", async () => {
    const { assignMutate } = setupMutations();
    const session = makeSession({ id: "sess-at", status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("session-row-sess-at"));
    await userEvent.click(screen.getByTestId("btn-assign-trainer"));
    const input = screen.getByTestId("input-trainer-id");
    await userEvent.clear(input);
    await userEvent.type(input, "trainer-uuid-1");
    await userEvent.click(screen.getByTestId("btn-submit-assign"));
    await waitFor(() => expect(assignMutate).toHaveBeenCalled());
    const args = assignMutate.mock.calls[0][0];
    expect(args.id).toBe("sess-at");
    expect(args.body.trainer_id).toBe("trainer-uuid-1");
  });

  it("assign trainer dialog cancel dismisses", async () => {
    setupMutations();
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-assign-trainer"));
    await userEvent.click(screen.getByTestId("btn-cancel-assign"));
    expect(screen.queryByTestId("assign-trainer-dialog")).toBeNull();
  });

  it("assign trainer dialog submit disabled while pending", async () => {
    setupMutations();
    mockAssign.mockReturnValue({ mutateAsync: vi.fn(), isPending: true } as ReturnType<typeof useAssignSessionTrainer>);
    const session = makeSession({ status: "planned" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-assign-trainer"));
    const btn = screen.getByTestId("btn-submit-assign") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("assign trainer pre-fills with existing trainer id", async () => {
    setupMutations();
    const session = makeSession({ trainer_id: "existing-trainer" });
    setupSessions([session]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId(`session-row-${session.id}`));
    await userEvent.click(screen.getByTestId("btn-assign-trainer"));
    const input = screen.getByTestId("input-trainer-id") as HTMLInputElement;
    expect(input.value).toBe("existing-trainer");
  });

  // ── Timeline view ───────────────────────────────────────────────────────────

  it("switches to timeline view when timeline button clicked", async () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-view-timeline"));
    expect(screen.getByTestId("session-timeline")).not.toBeNull();
  });

  it("table is hidden after switching to timeline", async () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-view-timeline"));
    expect(screen.queryByTestId("session-table")).toBeNull();
  });

  it("timeline shows a dot for each session", async () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", session_number: 1 }),
      makeSession({ id: "s2", session_number: 2 }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-view-timeline"));
    expect(screen.getByTestId("timeline-dot-s1")).not.toBeNull();
    expect(screen.getByTestId("timeline-dot-s2")).not.toBeNull();
  });

  it("timeline sorts by session_number ascending", async () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s3", session_number: 3, session_name: "Third" }),
      makeSession({ id: "s1", session_number: 1, session_name: "First" }),
      makeSession({ id: "s2", session_number: 2, session_name: "Second" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-view-timeline"));
    const dots = screen.getAllByTestId(/^timeline-dot-/);
    expect(dots[0].getAttribute("data-testid")).toBe("timeline-dot-s1");
    expect(dots[1].getAttribute("data-testid")).toBe("timeline-dot-s2");
    expect(dots[2].getAttribute("data-testid")).toBe("timeline-dot-s3");
  });

  it("switches back to table view when table button clicked", async () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.click(screen.getByTestId("btn-view-timeline"));
    await userEvent.click(screen.getByTestId("btn-view-table"));
    expect(screen.getByTestId("session-table")).not.toBeNull();
  });

  // ── Filters ─────────────────────────────────────────────────────────────────

  it("renders filter row when sessions exist", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("session-filters")).not.toBeNull();
  });

  it("filter search input is present", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("input-search")).not.toBeNull();
  });

  it("filter status select is present", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByTestId("select-status-filter")).not.toBeNull();
  });

  it("search filter hides non-matching sessions", async () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", session_name: "Morning Session" }),
      makeSession({ id: "s2", session_name: "Evening Session" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.type(screen.getByTestId("input-search"), "Evening");
    expect(screen.queryByTestId("session-row-s1")).toBeNull();
    expect(screen.getByTestId("session-row-s2")).not.toBeNull();
  });

  it("search is case-insensitive", async () => {
    setupMutations();
    const sessions = [makeSession({ id: "s1", session_name: "Morning Session" })];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.type(screen.getByTestId("input-search"), "morning");
    expect(screen.getByTestId("session-row-s1")).not.toBeNull();
  });

  it("status filter shows only matching status", async () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "planned" }),
      makeSession({ id: "s2", status: "completed" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const select = screen.getByTestId("select-status-filter") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "completed" } });
    expect(screen.queryByTestId("session-row-s1")).toBeNull();
    expect(screen.getByTestId("session-row-s2")).not.toBeNull();
  });

  it("status filter all shows all sessions", () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", status: "planned" }),
      makeSession({ id: "s2", status: "completed" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const select = screen.getByTestId("select-status-filter") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "" } });
    expect(screen.getByTestId("session-row-s1")).not.toBeNull();
    expect(screen.getByTestId("session-row-s2")).not.toBeNull();
  });

  it("status filter has All statuses option", () => {
    setupMutations();
    setupSessions([makeSession()]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    const select = screen.getByTestId("select-status-filter") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("");
  });

  it("combined search + status filter works", async () => {
    setupMutations();
    const sessions = [
      makeSession({ id: "s1", session_name: "Morning", status: "planned" }),
      makeSession({ id: "s2", session_name: "Morning", status: "completed" }),
      makeSession({ id: "s3", session_name: "Evening", status: "planned" }),
    ];
    setupSessions(sessions);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    await userEvent.type(screen.getByTestId("input-search"), "Morning");
    fireEvent.change(screen.getByTestId("select-status-filter"), { target: { value: "planned" } });
    expect(screen.getByTestId("session-row-s1")).not.toBeNull();
    expect(screen.queryByTestId("session-row-s2")).toBeNull();
    expect(screen.queryByTestId("session-row-s3")).toBeNull();
  });

  // ── Attendees display ───────────────────────────────────────────────────────

  it("shows actual_attendees when available", () => {
    setupMutations();
    setupSessions([makeSession({ actual_attendees: 18, expected_attendees: 25 })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByText("18")).not.toBeNull();
  });

  it("falls back to expected_attendees when actual is null", () => {
    setupMutations();
    setupSessions([makeSession({ actual_attendees: null, expected_attendees: 25 })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getByText("25")).not.toBeNull();
  });

  it("shows dash when both attendee counts are null", () => {
    setupMutations();
    setupSessions([makeSession({ actual_attendees: null, expected_attendees: null })]);
    render(<TrainingSessionCenter workspaceId={WS} engagementId={ENG} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  // ── Types: SESSION_STATUSES ────────────────────────────────────────────────

  it("SESSION_STATUSES includes all 5 statuses", () => {
    expect(SESSION_STATUSES).toHaveLength(5);
    expect(SESSION_STATUSES).toContain("planned");
    expect(SESSION_STATUSES).toContain("scheduled");
    expect(SESSION_STATUSES).toContain("in_progress");
    expect(SESSION_STATUSES).toContain("completed");
    expect(SESSION_STATUSES).toContain("cancelled");
  });

  it("SESSION_STATUSES order matches spec", () => {
    expect(SESSION_STATUSES[0]).toBe("planned");
    expect(SESSION_STATUSES[4]).toBe("cancelled");
  });
});
