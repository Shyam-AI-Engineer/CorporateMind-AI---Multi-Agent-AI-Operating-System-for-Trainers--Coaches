import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { Proposal } from "@/features/proposals/types";

// ── Shared mock state ──────────────────────────────────────────────────────────

const mockApprove = vi.fn();
const mockDeliver = vi.fn();

vi.mock("@/features/proposals/api/use-proposals", () => ({
  useProposal: vi.fn(),
  useApproveProposal: () => ({ mutateAsync: mockApprove, isPending: false }),
  useDeliverProposal: () => ({ mutateAsync: mockDeliver, isPending: false }),
}));

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-1" }),
}));

// Avoid rendering the full ProposalContentView to keep tests lightweight.
vi.mock("@/features/proposals/ui/proposal-content-view", () => ({
  ProposalContentView: () => <div data-testid="content-view" />,
}));

// ProposalRejectDialog is tested separately; stub it here.
vi.mock("@/features/proposals/ui/proposal-reject-dialog", () => ({
  ProposalRejectDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="reject-dialog" /> : null,
}));

// Stub Link so we don't need the full Next.js router.
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

// ── Helpers ────────────────────────────────────────────────────────────────────

import { useProposal } from "@/features/proposals/api/use-proposals";
const mockUseProposal = vi.mocked(useProposal);

function makeProposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: "prop-1",
    workspace_id: "ws-1",
    contact_id: "contact-abc123",
    title: "Leadership Training Proposal",
    status: "draft",
    content: { title: "Leadership", executive_summary: "Transform your team." },
    cloudinary_url: null,
    sent_at: null,
    created_at: "2026-01-01T10:00:00Z",
    approval_status: "pending_approval",
    approved_by: null,
    approved_at: null,
    rejected_reason: null,
    outbound_message_id: null,
    delivery_status: null,
    ...overrides,
  };
}

function mockLoaded(proposal: Proposal) {
  mockUseProposal.mockReturnValue({
    data: proposal,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useProposal>);
}

// Import page after mocks are registered.
const { default: ProposalDetailPage } = await import(
  "@/app/(dashboard)/proposals/[id]/page"
);

// Provide the [id] param via next/navigation (already mocked in setup.ts via useRouter;
// extend with useParams here).
vi.mock("next/navigation", async (importOriginal) => {
  const original = await importOriginal<typeof import("next/navigation")>();
  return {
    ...original,
    useParams: () => ({ id: "prop-1" }),
  };
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ProposalDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("pending_approval state", () => {
    it("shows Approve and Reject buttons", () => {
      mockLoaded(makeProposal({ approval_status: "pending_approval" }));
      render(<ProposalDetailPage />);
      expect(screen.getByRole("button", { name: /approve/i })).not.toBeNull();
      expect(screen.getByRole("button", { name: /reject/i })).not.toBeNull();
    });

    it("does not show Send proposal button", () => {
      mockLoaded(makeProposal({ approval_status: "pending_approval" }));
      render(<ProposalDetailPage />);
      expect(screen.queryByRole("button", { name: /send proposal/i })).toBeNull();
    });

    it("calls approve mutateAsync with the proposal id", async () => {
      mockApprove.mockResolvedValueOnce({});
      mockLoaded(makeProposal({ approval_status: "pending_approval" }));
      render(<ProposalDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /approve/i }));
      await waitFor(() =>
        expect(mockApprove).toHaveBeenCalledWith("prop-1"),
      );
    });

    it("opens the reject dialog when Reject is clicked", () => {
      mockLoaded(makeProposal({ approval_status: "pending_approval" }));
      render(<ProposalDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /reject/i }));
      expect(screen.getByTestId("reject-dialog")).not.toBeNull();
    });

    it("shows an inline error when approve fails", async () => {
      mockApprove.mockRejectedValueOnce(new Error("Permission denied"));
      mockLoaded(makeProposal({ approval_status: "pending_approval" }));
      render(<ProposalDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /approve/i }));
      await waitFor(() =>
        expect(
          screen.getByText("Approval failed — please try again."),
        ).not.toBeNull(),
      );
    });
  });

  describe("approved + draft state", () => {
    it("shows Send proposal button", () => {
      mockLoaded(
        makeProposal({ approval_status: "approved", status: "draft" }),
      );
      render(<ProposalDetailPage />);
      expect(
        screen.getByRole("button", { name: /send proposal/i }),
      ).not.toBeNull();
    });

    it("does not show Approve or Reject buttons", () => {
      mockLoaded(
        makeProposal({ approval_status: "approved", status: "draft" }),
      );
      render(<ProposalDetailPage />);
      expect(screen.queryByRole("button", { name: /^approve$/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
    });

    it("calls deliver mutateAsync with the proposal id", async () => {
      mockDeliver.mockResolvedValueOnce({});
      mockLoaded(
        makeProposal({ approval_status: "approved", status: "draft" }),
      );
      render(<ProposalDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /send proposal/i }));
      await waitFor(() =>
        expect(mockDeliver).toHaveBeenCalledWith("prop-1"),
      );
    });

    it("shows an inline error when deliver fails", async () => {
      mockDeliver.mockRejectedValueOnce(new Error("Network error"));
      mockLoaded(
        makeProposal({ approval_status: "approved", status: "draft" }),
      );
      render(<ProposalDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /send proposal/i }));
      await waitFor(() =>
        expect(
          screen.getByText("Delivery failed — please try again."),
        ).not.toBeNull(),
      );
    });
  });

  describe("approved + sent state", () => {
    it("shows no action buttons", () => {
      mockLoaded(
        makeProposal({
          approval_status: "approved",
          status: "sent",
          sent_at: "2026-01-02T10:00:00Z",
          delivery_status: "queued",
        }),
      );
      render(<ProposalDetailPage />);
      expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /send proposal/i })).toBeNull();
    });

    it("shows the Queued delivery badge", () => {
      mockLoaded(
        makeProposal({
          approval_status: "approved",
          status: "sent",
          delivery_status: "queued",
        }),
      );
      render(<ProposalDetailPage />);
      expect(screen.getByText("Queued")).not.toBeNull();
    });
  });

  describe("rejected state", () => {
    it("shows the rejection reason", () => {
      mockLoaded(
        makeProposal({
          approval_status: "rejected",
          rejected_reason: "Proposal too generic",
        }),
      );
      render(<ProposalDetailPage />);
      expect(screen.getByText("Proposal too generic")).not.toBeNull();
    });

    it("shows no action buttons", () => {
      mockLoaded(
        makeProposal({
          approval_status: "rejected",
          rejected_reason: "Too short",
        }),
      );
      render(<ProposalDetailPage />);
      expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /send proposal/i })).toBeNull();
    });
  });

  describe("compliance blocked state", () => {
    it("shows the blocked callout when delivery_status is blocked", () => {
      mockLoaded(
        makeProposal({
          approval_status: "approved",
          status: "sent",
          delivery_status: "blocked",
        }),
      );
      render(<ProposalDetailPage />);
      expect(
        screen.getByText("Delivery blocked by compliance"),
      ).not.toBeNull();
    });
  });

  describe("loading and error states", () => {
    it("shows skeleton rows while loading", () => {
      mockUseProposal.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as unknown as ReturnType<typeof useProposal>);
      const { container } = render(<ProposalDetailPage />);
      // Skeletons are divs — just verify the error/content are absent
      expect(screen.queryByText("Proposal not found.")).toBeNull();
      expect(container.querySelectorAll("[data-testid='content-view']").length).toBe(0);
    });

    it("shows not-found message on error", () => {
      mockUseProposal.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as unknown as ReturnType<typeof useProposal>);
      render(<ProposalDetailPage />);
      expect(screen.getByText("Proposal not found.")).not.toBeNull();
    });
  });
});
