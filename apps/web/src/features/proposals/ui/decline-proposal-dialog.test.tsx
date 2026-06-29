import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock("@/features/proposals/api/use-proposals", () => ({
  useDeclineProposal: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

const { DeclineProposalDialog } = await import("./decline-proposal-dialog");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("DeclineProposalDialog", () => {
  const defaultProps = {
    proposalId: "prop-1",
    workspaceId: "ws-1",
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the dialog with optional reason field", () => {
    render(<DeclineProposalDialog {...defaultProps} />);
    expect(screen.getByRole("heading", { name: /record decline/i })).not.toBeNull();
    expect(screen.getByLabelText(/reason/i)).not.toBeNull();
  });

  it("submit button is enabled without a reason (reason is optional)", () => {
    render(<DeclineProposalDialog {...defaultProps} />);
    const btn = screen.getByRole("button", { name: /record decline/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("calls mutateAsync without reason when submitted empty", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<DeclineProposalDialog {...defaultProps} />);

    fireEvent.click(screen.getByRole("button", { name: /record decline/i }));

    await waitFor(() =>
      expect(mockMutateAsync).toHaveBeenCalledWith({
        proposalId: "prop-1",
        reason: undefined,
      }),
    );
  });

  it("passes reason string when provided", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<DeclineProposalDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/reason/i), {
      target: { value: "Budget constraints" },
    });
    fireEvent.click(screen.getByRole("button", { name: /record decline/i }));

    await waitFor(() =>
      expect(mockMutateAsync).toHaveBeenCalledWith({
        proposalId: "prop-1",
        reason: "Budget constraints",
      }),
    );
  });

  it("closes on successful submission", async () => {
    const onOpenChange = vi.fn();
    mockMutateAsync.mockResolvedValueOnce({});
    render(<DeclineProposalDialog {...defaultProps} onOpenChange={onOpenChange} />);

    fireEvent.click(screen.getByRole("button", { name: /record decline/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("shows an error message when mutateAsync throws", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Server error"));
    render(<DeclineProposalDialog {...defaultProps} />);

    fireEvent.click(screen.getByRole("button", { name: /record decline/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Failed to record decline — please try again."),
      ).not.toBeNull(),
    );
  });

  it("calls onOpenChange(false) when Cancel is clicked", () => {
    const onOpenChange = vi.fn();
    render(<DeclineProposalDialog {...defaultProps} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
