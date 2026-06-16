import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock("@/features/proposals/api/use-proposals", () => ({
  useRejectProposal: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

// Import after mocks are registered.
const { ProposalRejectDialog } = await import("./proposal-reject-dialog");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ProposalRejectDialog", () => {
  const defaultProps = {
    proposalId: "prop-1",
    workspaceId: "ws-1",
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the dialog when open", () => {
    render(<ProposalRejectDialog {...defaultProps} />);
    expect(screen.getByRole("heading", { name: "Reject proposal" })).not.toBeNull();
    expect(screen.getByLabelText("Reason")).not.toBeNull();
  });

  it("disables the Reject button when reason is empty", () => {
    render(<ProposalRejectDialog {...defaultProps} />);
    const rejectBtn = screen.getByRole("button", { name: /reject proposal/i });
    expect((rejectBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables the Reject button when a reason is typed", async () => {
    render(<ProposalRejectDialog {...defaultProps} />);
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Content needs revision" },
    });
    const rejectBtn = screen.getByRole("button", { name: /reject proposal/i });
    expect((rejectBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("calls mutateAsync with proposalId and reason on submit", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<ProposalRejectDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Needs stronger value proposition" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reject proposal/i }));

    await waitFor(() =>
      expect(mockMutateAsync).toHaveBeenCalledWith({
        proposalId: "prop-1",
        reason: "Needs stronger value proposition",
      }),
    );
  });

  it("closes the dialog on successful submission", async () => {
    const onOpenChange = vi.fn();
    mockMutateAsync.mockResolvedValueOnce({});
    render(
      <ProposalRejectDialog {...defaultProps} onOpenChange={onOpenChange} />,
    );

    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Not suitable for this contact" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reject proposal/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("shows an error message when mutateAsync throws", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Server error"));
    render(<ProposalRejectDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Some reason" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reject proposal/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Failed to reject — please try again."),
      ).not.toBeNull(),
    );
  });

  it("calls onOpenChange(false) when Cancel is clicked", () => {
    const onOpenChange = vi.fn();
    render(
      <ProposalRejectDialog {...defaultProps} onOpenChange={onOpenChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
