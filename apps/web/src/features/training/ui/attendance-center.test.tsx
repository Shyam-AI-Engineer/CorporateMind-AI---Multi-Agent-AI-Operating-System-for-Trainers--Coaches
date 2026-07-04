import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TrainingAttendance } from "@/features/training/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/training/api/use-training", () => ({
  useAttendanceList: vi.fn(),
  useRegisterParticipant: vi.fn(),
  useUpdateAttendance: vi.fn(),
  useMarkPresent: vi.fn(),
  useMarkLate: vi.fn(),
  useMarkAbsent: vi.fn(),
  useMarkLeftEarly: vi.fn(),
  useCheckOut: vi.fn(),
}));

import {
  useAttendanceList,
  useRegisterParticipant,
  useUpdateAttendance,
  useMarkPresent,
  useMarkLate,
  useMarkAbsent,
  useMarkLeftEarly,
  useCheckOut,
} from "@/features/training/api/use-training";

const mockList = vi.mocked(useAttendanceList);
const mockRegister = vi.mocked(useRegisterParticipant);
const mockUpdateMut = vi.mocked(useUpdateAttendance);
const mockPresent = vi.mocked(useMarkPresent);
const mockLate = vi.mocked(useMarkLate);
const mockAbsent = vi.mocked(useMarkAbsent);
const mockLeftEarly = vi.mocked(useMarkLeftEarly);
const mockCheckOut = vi.mocked(useCheckOut);

const { AttendanceCenter } = await import("./attendance-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SESSION_ID = "sess-sprint44";
const WS = "ws-sprint44";

function makeAtt(overrides: Partial<TrainingAttendance> = {}): TrainingAttendance {
  return {
    id: "att-1",
    tenant_id: "org-1",
    workspace_id: WS,
    session_id: SESSION_ID,
    participant_name: "Alice Smith",
    participant_email: "alice@corp.com",
    participant_phone: "+91-9876543210",
    company: "Acme Corp",
    designation: "HR Manager",
    attendance_status: "registered",
    check_in_time: null,
    check_out_time: null,
    completion_percent: null,
    certificate_eligible: false,
    remarks: null,
    created_at: "2026-07-04T09:00:00Z",
    updated_at: "2026-07-04T09:00:00Z",
    ...overrides,
  };
}

function setupMuts(mutateAsync = vi.fn().mockResolvedValue({})) {
  mockRegister.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useRegisterParticipant>);
  mockUpdateMut.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useUpdateAttendance>);
  mockPresent.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkPresent>);
  mockLate.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkLate>);
  mockAbsent.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkAbsent>);
  mockLeftEarly.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkLeftEarly>);
  mockCheckOut.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useCheckOut>);
  return mutateAsync;
}

function setList(
  items: TrainingAttendance[],
  opts: { has_more?: boolean; next_cursor?: string | null; total?: number } = {},
) {
  mockList.mockReturnValue({
    data: {
      data: {
        items,
        total: opts.total ?? items.length,
        has_more: opts.has_more ?? false,
        next_cursor: opts.next_cursor ?? null,
      },
    },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAttendanceList>);
}

function renderCenter(
  items: TrainingAttendance[] = [],
  opts: { has_more?: boolean; next_cursor?: string | null; total?: number } = {},
) {
  setList(items, opts);
  setupMuts();
  return render(<AttendanceCenter sessionId={SESSION_ID} workspaceId={WS} />);
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("AttendanceCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── 1. Loading state ──────────────────────────────────────────────────────

  describe("Loading state", () => {
    beforeEach(() => {
      mockList.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as unknown as ReturnType<typeof useAttendanceList>);
      setupMuts();
    });

    it("renders loading indicator", () => {
      render(<AttendanceCenter sessionId={SESSION_ID} workspaceId={WS} />);
      expect(screen.getByTestId("attendance-loading")).not.toBeNull();
    });

    it("does not render main container while loading", () => {
      render(<AttendanceCenter sessionId={SESSION_ID} workspaceId={WS} />);
      expect(screen.queryByTestId("attendance-center")).toBeNull();
    });
  });

  // ── 2. Error state ────────────────────────────────────────────────────────

  describe("Error state", () => {
    beforeEach(() => {
      mockList.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as unknown as ReturnType<typeof useAttendanceList>);
      setupMuts();
    });

    it("renders error message", () => {
      render(<AttendanceCenter sessionId={SESSION_ID} workspaceId={WS} />);
      expect(screen.getByTestId("attendance-error")).not.toBeNull();
    });

    it("does not render main container on error", () => {
      render(<AttendanceCenter sessionId={SESSION_ID} workspaceId={WS} />);
      expect(screen.queryByTestId("attendance-center")).toBeNull();
    });
  });

  // ── 3. Empty state ────────────────────────────────────────────────────────

  describe("Empty state", () => {
    beforeEach(() => {
      renderCenter([]);
    });

    it("renders attendance-center container", () => {
      expect(screen.getByTestId("attendance-center")).not.toBeNull();
    });

    it("renders attendance-empty when no items", () => {
      expect(screen.getByTestId("attendance-empty")).not.toBeNull();
    });

    it("renders btn-register-empty", () => {
      expect(screen.getByTestId("btn-register-empty")).not.toBeNull();
    });

    it("renders toolbar register button", () => {
      expect(screen.getByTestId("btn-register")).not.toBeNull();
    });

    it("does not render attendance-table when empty", () => {
      expect(screen.queryByTestId("attendance-table")).toBeNull();
    });

    it("clicking btn-register-empty opens register dialog", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register-empty"));
      expect(screen.getByTestId("register-dialog")).not.toBeNull();
    });
  });

  // ── 4. KPI cards ──────────────────────────────────────────────────────────

  describe("KPI cards", () => {
    it("renders all four KPI card containers", () => {
      renderCenter([]);
      expect(screen.getByTestId("attendance-kpis")).not.toBeNull();
      expect(screen.getByTestId("kpi-total")).not.toBeNull();
      expect(screen.getByTestId("kpi-present")).not.toBeNull();
      expect(screen.getByTestId("kpi-absent")).not.toBeNull();
      expect(screen.getByTestId("kpi-certificate")).not.toBeNull();
    });

    it("kpi-total shows 0 for empty list", () => {
      renderCenter([]);
      expect(screen.getByTestId("kpi-total").textContent).toContain("0");
    });

    it("kpi-present shows 0 for empty list", () => {
      renderCenter([]);
      expect(screen.getByTestId("kpi-present").textContent).toContain("0");
    });

    it("kpi-absent shows 0 for empty list", () => {
      renderCenter([]);
      expect(screen.getByTestId("kpi-absent").textContent).toContain("0");
    });

    it("kpi-certificate shows 0 for empty list", () => {
      renderCenter([]);
      expect(screen.getByTestId("kpi-certificate").textContent).toContain("0");
    });

    it("kpi-total reflects total participant count", () => {
      renderCenter([makeAtt({ id: "a1" }), makeAtt({ id: "a2" }), makeAtt({ id: "a3" })]);
      expect(screen.getByTestId("kpi-total").textContent).toContain("3");
    });

    it("kpi-present counts present AND late as attended", () => {
      renderCenter([
        makeAtt({ id: "a1", attendance_status: "present" }),
        makeAtt({ id: "a2", attendance_status: "late" }),
        makeAtt({ id: "a3", attendance_status: "absent" }),
      ]);
      expect(screen.getByTestId("kpi-present").textContent).toContain("2");
    });

    it("kpi-absent only counts absent status", () => {
      renderCenter([
        makeAtt({ id: "a1", attendance_status: "absent" }),
        makeAtt({ id: "a2", attendance_status: "absent" }),
        makeAtt({ id: "a3", attendance_status: "present" }),
      ]);
      expect(screen.getByTestId("kpi-absent").textContent).toContain("2");
    });

    it("kpi-certificate counts certificate_eligible participants", () => {
      renderCenter([
        makeAtt({ id: "a1", certificate_eligible: true }),
        makeAtt({ id: "a2", certificate_eligible: true }),
        makeAtt({ id: "a3", certificate_eligible: false }),
      ]);
      expect(screen.getByTestId("kpi-certificate").textContent).toContain("2");
    });

    it("late status alone contributes to kpi-present", () => {
      renderCenter([makeAtt({ id: "a1", attendance_status: "late" })]);
      expect(screen.getByTestId("kpi-present").textContent).toContain("1");
    });

    it("left_early status not counted in kpi-present", () => {
      renderCenter([makeAtt({ id: "a1", attendance_status: "left_early" })]);
      expect(screen.getByTestId("kpi-present").textContent).toContain("0");
    });
  });

  // ── 5. Toolbar ────────────────────────────────────────────────────────────

  describe("Toolbar", () => {
    beforeEach(() => {
      renderCenter([]);
    });

    it("renders search input", () => {
      expect(screen.getByTestId("input-search")).not.toBeNull();
    });

    it("renders status filter select", () => {
      expect(screen.getByTestId("select-status-filter")).not.toBeNull();
    });

    it("renders register participant button", () => {
      expect(screen.getByTestId("btn-register")).not.toBeNull();
    });

    it("status filter contains All statuses option", () => {
      expect(screen.getByTestId("select-status-filter").textContent).toContain("All statuses");
    });

    it("status filter has 5 attendance status options plus default (6 total)", () => {
      const sel = screen.getByTestId("select-status-filter") as HTMLSelectElement;
      expect(sel.options.length).toBe(6);
    });

    it("search input has placeholder text mentioning Search", () => {
      const input = screen.getByTestId("input-search") as HTMLInputElement;
      expect(input.placeholder).toContain("Search");
    });
  });

  // ── 6. Attendance table ───────────────────────────────────────────────────

  describe("Attendance table", () => {
    const items = [
      makeAtt({ id: "a1", participant_name: "Alice", company: "AcmeCo", attendance_status: "present", certificate_eligible: true }),
      makeAtt({ id: "a2", participant_name: "Bob", company: "TechInc", attendance_status: "absent", certificate_eligible: false }),
      makeAtt({ id: "a3", participant_name: "Carol", company: "BizLtd", attendance_status: "late", certificate_eligible: true }),
    ];

    beforeEach(() => {
      renderCenter(items);
    });

    it("renders attendance-table", () => {
      expect(screen.getByTestId("attendance-table")).not.toBeNull();
    });

    it("renders a row for each participant", () => {
      expect(screen.getByTestId("attendance-row-a1")).not.toBeNull();
      expect(screen.getByTestId("attendance-row-a2")).not.toBeNull();
      expect(screen.getByTestId("attendance-row-a3")).not.toBeNull();
    });

    it("renders participant names in rows", () => {
      expect(screen.getByText("Alice")).not.toBeNull();
      expect(screen.getByText("Bob")).not.toBeNull();
      expect(screen.getByText("Carol")).not.toBeNull();
    });

    it("renders status badge for each row", () => {
      expect(screen.getByTestId("status-badge-a1")).not.toBeNull();
      expect(screen.getByTestId("status-badge-a2")).not.toBeNull();
      expect(screen.getByTestId("status-badge-a3")).not.toBeNull();
    });

    it("status badge shows correct label for present", () => {
      expect(screen.getByTestId("status-badge-a1").textContent).toContain("Present");
    });

    it("status badge shows correct label for absent", () => {
      expect(screen.getByTestId("status-badge-a2").textContent).toContain("Absent");
    });

    it("status badge shows correct label for late", () => {
      expect(screen.getByTestId("status-badge-a3").textContent).toContain("Late");
    });

    it("renders cert badge for certificate_eligible participant", () => {
      expect(screen.getByTestId("cert-badge-a1")).not.toBeNull();
    });

    it("does not render cert badge for non-eligible participant", () => {
      expect(screen.queryByTestId("cert-badge-a2")).toBeNull();
    });

    it("renders action button for each row", () => {
      expect(screen.getByTestId("btn-action-a1")).not.toBeNull();
      expect(screen.getByTestId("btn-action-a2")).not.toBeNull();
    });

    it("clicking a row opens the attendance drawer", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-a1"));
      expect(screen.getByTestId("attendance-drawer")).not.toBeNull();
    });

    it("clicking action button opens status dialog, not drawer", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-a1"));
      expect(screen.getByTestId("status-dialog")).not.toBeNull();
      expect(screen.queryByTestId("attendance-drawer")).toBeNull();
    });
  });

  // ── 7. Register participant dialog ────────────────────────────────────────

  describe("Register participant dialog", () => {
    beforeEach(() => {
      renderCenter([]);
    });

    it("register dialog is hidden by default", () => {
      expect(screen.queryByTestId("register-dialog")).toBeNull();
    });

    it("clicking btn-register opens dialog", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("register-dialog")).not.toBeNull();
    });

    it("dialog contains the register form", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("register-form")).not.toBeNull();
    });

    it("clicking cancel button closes dialog", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      await user.click(screen.getByTestId("btn-cancel-register"));
      expect(screen.queryByTestId("register-dialog")).toBeNull();
    });

    it("renders participant name input", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-participant-name")).not.toBeNull();
    });

    it("renders participant email input", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-participant-email")).not.toBeNull();
    });

    it("renders participant phone input", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-participant-phone")).not.toBeNull();
    });

    it("renders company input", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-company")).not.toBeNull();
    });

    it("renders designation input", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-designation")).not.toBeNull();
    });

    it("renders status select with all 5 options", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      const sel = screen.getByTestId("select-attendance-status") as HTMLSelectElement;
      expect(sel.options.length).toBe(5);
    });

    it("certificate checkbox is unchecked by default", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      const cb = screen.getByTestId("checkbox-certificate") as HTMLInputElement;
      expect(cb.checked).toBe(false);
    });

    it("remarks textarea renders", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("input-remarks")).not.toBeNull();
    });

    it("renders btn-submit-register", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      expect(screen.getByTestId("btn-submit-register")).not.toBeNull();
    });

    it("submitting with empty name shows validation error", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      await user.click(screen.getByTestId("btn-submit-register"));
      expect(screen.getByTestId("register-error")).not.toBeNull();
    });

    it("validation error text mentions name required", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      await user.click(screen.getByTestId("btn-submit-register"));
      expect(screen.getByTestId("register-error").textContent?.toLowerCase()).toContain("name");
    });

    it("successful submit calls mutateAsync and closes dialog", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockRegister.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useRegisterParticipant>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      await user.type(screen.getByTestId("input-participant-name"), "Test User");
      await user.click(screen.getByTestId("btn-submit-register"));
      await waitFor(() => {
        expect(screen.queryByTestId("register-dialog")).toBeNull();
      });
      expect(mutateAsync).toHaveBeenCalledOnce();
    });

    it("failed submit shows register-error message", async () => {
      const mutateAsync = vi.fn().mockRejectedValue(new Error("fail"));
      mockRegister.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useRegisterParticipant>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-register"));
      await user.type(screen.getByTestId("input-participant-name"), "Test User");
      await user.click(screen.getByTestId("btn-submit-register"));
      await waitFor(() => {
        expect(screen.getByTestId("register-error").textContent?.toLowerCase()).toContain("failed");
      });
    });
  });

  // ── 8. Attendance status dialog ───────────────────────────────────────────

  describe("Attendance status dialog", () => {
    const att = makeAtt({ id: "att-x", attendance_status: "registered" });

    beforeEach(() => {
      renderCenter([att]);
    });

    it("status dialog hidden by default", () => {
      expect(screen.queryByTestId("status-dialog")).toBeNull();
    });

    it("opens when action button is clicked", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("status-dialog")).not.toBeNull();
    });

    it("renders btn-status-present", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-status-present")).not.toBeNull();
    });

    it("renders btn-status-late", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-status-late")).not.toBeNull();
    });

    it("renders btn-status-absent", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-status-absent")).not.toBeNull();
    });

    it("renders btn-status-left-early", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-status-left-early")).not.toBeNull();
    });

    it("renders btn-checkout", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-checkout")).not.toBeNull();
    });

    it("renders btn-close-status", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("btn-close-status")).not.toBeNull();
    });

    it("clicking btn-close-status closes dialog", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-close-status"));
      expect(screen.queryByTestId("status-dialog")).toBeNull();
    });

    it("clicking Mark Present calls markPresent.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockPresent.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkPresent>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-status-present"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("clicking Mark Late calls markLate.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockLate.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkLate>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-status-late"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("clicking Mark Absent calls markAbsent.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockAbsent.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkAbsent>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-status-absent"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("clicking Mark Left Early calls markLeftEarly.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockLeftEarly.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkLeftEarly>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-status-left-early"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("renders input-checkout-time", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("input-checkout-time")).not.toBeNull();
    });

    it("renders input-completion-pct", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("input-completion-pct")).not.toBeNull();
    });

    it("renders checkbox-cert-checkout", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      expect(screen.getByTestId("checkbox-cert-checkout")).not.toBeNull();
    });

    it("clicking checkout calls checkOut.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockCheckOut.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useCheckOut>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-checkout"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("mark action failure shows status-error", async () => {
      const mutateAsync = vi.fn().mockRejectedValue(new Error("fail"));
      mockPresent.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useMarkPresent>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-action-att-x"));
      await user.click(screen.getByTestId("btn-status-present"));
      await waitFor(() => {
        expect(screen.getByTestId("status-error")).not.toBeNull();
      });
    });
  });

  // ── 9. Attendance drawer — view mode ──────────────────────────────────────

  describe("Attendance drawer — view mode", () => {
    const att = makeAtt({
      id: "drawer-att",
      participant_name: "Dave Jones",
      participant_email: "dave@corp.com",
      participant_phone: "+1-555-1234",
      company: "TechCorp",
      designation: "CTO",
      attendance_status: "present",
      certificate_eligible: true,
      check_in_time: "2026-07-04T09:00:00Z",
      check_out_time: "2026-07-04T17:00:00Z",
      completion_percent: 85,
      remarks: "Excellent session",
    });

    beforeEach(() => {
      renderCenter([att]);
    });

    it("drawer is hidden before row click", () => {
      expect(screen.queryByTestId("attendance-drawer")).toBeNull();
    });

    it("clicking row opens drawer", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("attendance-drawer")).not.toBeNull();
    });

    it("drawer shows participant name", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-participant-name").textContent).toContain("Dave Jones");
    });

    it("drawer shows status badge", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-status-badge").textContent).toContain("Present");
    });

    it("drawer shows certificate badge for eligible participant", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-certificate-badge")).not.toBeNull();
    });

    it("drawer shows company", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-company").textContent).toContain("TechCorp");
    });

    it("drawer shows designation", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-designation").textContent).toContain("CTO");
    });

    it("drawer shows email", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-email").textContent).toContain("dave@corp.com");
    });

    it("drawer shows phone", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-phone").textContent).toContain("+1-555-1234");
    });

    it("drawer shows completion percent", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-completion").textContent).toContain("85%");
    });

    it("drawer shows remarks", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-remarks").textContent).toContain("Excellent session");
    });

    it("btn-close-drawer closes the drawer", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      await user.click(screen.getByTestId("btn-close-drawer"));
      expect(screen.queryByTestId("attendance-drawer")).toBeNull();
    });

    it("drawer shows btn-update-status in view mode", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("btn-update-status")).not.toBeNull();
    });

    it("drawer shows btn-edit-participant in view mode", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("btn-edit-participant")).not.toBeNull();
    });

    it("clicking btn-update-status from drawer opens status dialog", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      await user.click(screen.getByTestId("btn-update-status"));
      expect(screen.getByTestId("status-dialog")).not.toBeNull();
    });

    it("drawer-check-in element renders", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-check-in")).not.toBeNull();
    });

    it("drawer-check-out element renders", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-drawer-att"));
      expect(screen.getByTestId("drawer-check-out")).not.toBeNull();
    });
  });

  // ── 10. Attendance drawer — edit mode ─────────────────────────────────────

  describe("Attendance drawer — edit mode", () => {
    const att = makeAtt({
      id: "edit-att",
      participant_name: "Eve Chen",
      company: "StartupXYZ",
      remarks: "Good attendance",
      certificate_eligible: false,
    });

    beforeEach(async () => {
      renderCenter([att]);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("attendance-row-edit-att"));
    });

    it("drawer-edit-form is hidden before clicking edit", () => {
      expect(screen.queryByTestId("drawer-edit-form")).toBeNull();
    });

    it("clicking btn-edit-participant shows edit form", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      expect(screen.getByTestId("drawer-edit-form")).not.toBeNull();
    });

    it("edit-participant-name has initial value from attendance", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      const input = screen.getByTestId("edit-participant-name") as HTMLInputElement;
      expect(input.value).toBe("Eve Chen");
    });

    it("edit-company has initial value", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      const input = screen.getByTestId("edit-company") as HTMLInputElement;
      expect(input.value).toBe("StartupXYZ");
    });

    it("edit-remarks has initial value", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      const ta = screen.getByTestId("edit-remarks") as HTMLTextAreaElement;
      expect(ta.value).toBe("Good attendance");
    });

    it("edit-certificate is unchecked matching attendance", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      const cb = screen.getByTestId("edit-certificate") as HTMLInputElement;
      expect(cb.checked).toBe(false);
    });

    it("renders btn-save-edit in edit mode", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      expect(screen.getByTestId("btn-save-edit")).not.toBeNull();
    });

    it("renders btn-cancel-edit in edit mode", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      expect(screen.getByTestId("btn-cancel-edit")).not.toBeNull();
    });

    it("clicking btn-cancel-edit hides edit form", async () => {
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      await user.click(screen.getByTestId("btn-cancel-edit"));
      expect(screen.queryByTestId("drawer-edit-form")).toBeNull();
    });

    it("saving edit calls updateAttendance.mutateAsync", async () => {
      const mutateAsync = vi.fn().mockResolvedValue({});
      mockUpdateMut.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useUpdateAttendance>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      await user.click(screen.getByTestId("btn-save-edit"));
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce());
    });

    it("save failure shows drawer-error", async () => {
      const mutateAsync = vi.fn().mockRejectedValue(new Error("fail"));
      mockUpdateMut.mockReturnValue({ mutateAsync, isPending: false } as ReturnType<typeof useUpdateAttendance>);
      const user = userEvent.setup();
      await user.click(screen.getByTestId("btn-edit-participant"));
      await user.click(screen.getByTestId("btn-save-edit"));
      await waitFor(() => {
        expect(screen.getByTestId("drawer-error")).not.toBeNull();
      });
    });
  });

  // ── 11. Pagination ────────────────────────────────────────────────────────

  describe("Pagination", () => {
    it("btn-load-more not shown when has_more is false", () => {
      renderCenter([makeAtt()], { has_more: false });
      expect(screen.queryByTestId("btn-load-more")).toBeNull();
    });

    it("btn-load-more shown when has_more is true", () => {
      renderCenter([makeAtt()], { has_more: true, next_cursor: "cur-abc" });
      expect(screen.getByTestId("btn-load-more")).not.toBeNull();
    });

    it("attendance-count shows correct count for multiple items", () => {
      renderCenter([makeAtt({ id: "a1" }), makeAtt({ id: "a2" }), makeAtt({ id: "a3" })]);
      expect(screen.getByTestId("attendance-count").textContent).toContain("3 participants");
    });

    it("attendance-count uses singular form for 1 participant", () => {
      renderCenter([makeAtt()]);
      expect(screen.getByTestId("attendance-count").textContent).toContain("1 participant");
    });
  });

  // ── 12. Status labels and badge colors ────────────────────────────────────

  describe("Status labels and badge colors", () => {
    it("registered status shows Registered label", () => {
      renderCenter([makeAtt({ id: "s1", attendance_status: "registered" })]);
      expect(screen.getByTestId("status-badge-s1").textContent).toContain("Registered");
    });

    it("left_early status shows Left Early label", () => {
      renderCenter([makeAtt({ id: "s2", attendance_status: "left_early" })]);
      expect(screen.getByTestId("status-badge-s2").textContent).toContain("Left Early");
    });

    it("absent status badge has red color class", () => {
      renderCenter([makeAtt({ id: "s3", attendance_status: "absent" })]);
      expect(screen.getByTestId("status-badge-s3").className).toContain("red");
    });

    it("present status badge has green color class", () => {
      renderCenter([makeAtt({ id: "s4", attendance_status: "present" })]);
      expect(screen.getByTestId("status-badge-s4").className).toContain("green");
    });

    it("late status badge has yellow color class", () => {
      renderCenter([makeAtt({ id: "s5", attendance_status: "late" })]);
      expect(screen.getByTestId("status-badge-s5").className).toContain("yellow");
    });
  });
});
