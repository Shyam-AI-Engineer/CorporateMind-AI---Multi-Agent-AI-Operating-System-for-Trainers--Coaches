import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

vi.mock("@/features/proposals/api/use-proposals", () => ({
  useAcceptProposal: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

const { AcceptProposalDialog } = await import("./accept-proposal-dialog");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AcceptProposalDialog", () => {
  const defaultProps = {
    proposalId: "prop-1",
    workspaceId: "ws-1",
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the dialog with required fields when open", () => {
    render(<AcceptProposalDialog {...defaultProps} />);
    expect(screen.getByRole("heading", { name: /record acceptance/i })).not.toBeNull();
    expect(screen.getByLabelText(/deal value/i)).not.toBeNull();
    expect(screen.getByLabelText(/expected value/i)).not.toBeNull();
  });

  it("disables submit when actual value is empty", () => {
    render(<AcceptProposalDialog {...defaultProps} />);
    const btn = screen.getByRole("button", { name: /record acceptance/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("disables submit when actual value is zero", () => {
    render(<AcceptProposalDialog {...defaultProps} />);
    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "0" } });
    const btn = screen.getByRole("button", { name: /record acceptance/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables submit when actual value is positive", () => {
    render(<AcceptProposalDialog {...defaultProps} />);
    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "150000" } });
    const btn = screen.getByRole("button", { name: /record acceptance/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("calls mutateAsync with proposalId and actual_value_inr on submit", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<AcceptProposalDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "200000" } });
    fireEvent.click(screen.getByRole("button", { name: /record acceptance/i }));

    await waitFor(() =>
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ proposalId: "prop-1", actual_value_inr: 200000 }),
      ),
    );
  });

  it("includes expected_value_inr when provided", async () => {
    mockMutateAsync.mockResolvedValueOnce({});
    render(<AcceptProposalDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "200000" } });
    fireEvent.change(screen.getByLabelText(/expected value/i), { target: { value: "250000" } });
    fireEvent.click(screen.getByRole("button", { name: /record acceptance/i }));

    await waitFor(() =>
      expect(mockMutateAsync).toHaveBeenCalledWith({
        proposalId: "prop-1",
        actual_value_inr: 200000,
        expected_value_inr: 250000,
      }),
    );
  });

  it("closes on successful submission", async () => {
    const onOpenChange = vi.fn();
    mockMutateAsync.mockResolvedValueOnce({});
    render(<AcceptProposalDialog {...defaultProps} onOpenChange={onOpenChange} />);

    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "100000" } });
    fireEvent.click(screen.getByRole("button", { name: /record acceptance/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("shows an error message when mutateAsync throws", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Server error"));
    render(<AcceptProposalDialog {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/deal value/i), { target: { value: "100000" } });
    fireEvent.click(screen.getByRole("button", { name: /record acceptance/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Failed to record acceptance — please try again."),
      ).not.toBeNull(),
    );
  });

  it("calls onOpenChange(false) when Cancel is clicked", () => {
    const onOpenChange = vi.fn();
    render(<AcceptProposalDialog {...defaultProps} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
