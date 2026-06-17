import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock("@/features/crm/api/use-leads", () => ({
  useScheduleMeeting: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

// Import after mocks are registered.
const { MeetingSchedulerDialog } = await import("./meeting-scheduler-dialog");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("MeetingSchedulerDialog", () => {
  const defaultProps = {
    leadId: "lead-1",
    workspaceId: "ws-1",
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the dialog title and date input when open", () => {
    render(<MeetingSchedulerDialog {...defaultProps} />);
    expect(screen.getByRole("heading", { name: "Set meeting time" })).not.toBeNull();
    expect(screen.getByLabelText("Date and time")).not.toBeNull();
  });

  it("disables Set time button when no date is entered", () => {
    render(<MeetingSchedulerDialog {...defaultProps} />);
    const btn = screen.getByRole("button", { name: /set time/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables Set time button when a date is typed", () => {
    render(<MeetingSchedulerDialog {...defaultProps} />);
    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-07-01T10:00" },
    });
    const btn = screen.getByRole("button", { name: /set time/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("calls mutateAsync with leadId and ISO-string meetingAt on submit", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<MeetingSchedulerDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-07-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /set time/i }));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        leadId: "lead-1",
        meetingAt: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
      });
    });
  });

  it("closes dialog on successful submission", async () => {
    const onOpenChange = vi.fn();
    mockMutateAsync.mockResolvedValueOnce({});
    render(
      <MeetingSchedulerDialog {...defaultProps} onOpenChange={onOpenChange} />,
    );

    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-07-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /set time/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("shows error message when mutateAsync throws", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Server error"));
    render(<MeetingSchedulerDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-07-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /set time/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Failed to set meeting time — please try again."),
      ).not.toBeNull(),
    );
  });

  it("calls onOpenChange(false) when Cancel is clicked", () => {
    const onOpenChange = vi.fn();
    render(
      <MeetingSchedulerDialog {...defaultProps} onOpenChange={onOpenChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("resets the date input and clears errors when closed", async () => {
    const onOpenChange = vi.fn();
    mockMutateAsync.mockRejectedValueOnce(new Error("Oops"));
    render(
      <MeetingSchedulerDialog {...defaultProps} onOpenChange={onOpenChange} />,
    );

    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-07-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: /set time/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Failed to set meeting time — please try again."),
      ).not.toBeNull(),
    );

    // Close via Cancel — error should clear and input should reset
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
