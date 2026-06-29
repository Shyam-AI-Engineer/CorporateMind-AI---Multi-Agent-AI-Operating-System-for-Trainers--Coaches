import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { Lead } from "@/features/crm/types";
import type { ProposalListOut, Proposal } from "@/features/proposals/types";

// ── Shared mock state ──────────────────────────────────────────────────────────

const mockAdvance = vi.fn();
const mockMarkLost = vi.fn();

vi.mock("@/features/crm/api/use-leads", () => ({
  useGetLead: vi.fn(),
  useAdvanceStage: () => ({ mutateAsync: mockAdvance, isPending: false }),
  useMarkLost: () => ({ mutateAsync: mockMarkLost, isPending: false }),
}));

vi.mock("@/features/proposals/api/use-proposals", () => ({
  useProposalsForContact: vi.fn(),
}));

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-1" }),
}));

// Lightweight stubs for heavy child components
vi.mock("@/features/crm/ui/activity-timeline", () => ({
  ActivityTimeline: () => <div data-testid="activity-timeline" />,
}));

vi.mock("@/features/crm/ui/lead-stage-timeline", () => ({
  LeadStageTimeline: ({ currentStage }: { currentStage: string }) => (
    <div data-testid={`stage-timeline-${currentStage}`} />
  ),
}));

vi.mock("@/features/crm/ui/meeting-scheduler-dialog", () => ({
  MeetingSchedulerDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="meeting-dialog" /> : null,
}));

vi.mock("@/features/proposals/ui/generate-proposal-dialog", () => ({
  GenerateProposalDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="generate-dialog" /> : null,
}));

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

import { useGetLead } from "@/features/crm/api/use-leads";
import { useProposalsForContact } from "@/features/proposals/api/use-proposals";
const mockUseGetLead = vi.mocked(useGetLead);
const mockUseProposalsForContact = vi.mocked(useProposalsForContact);

function makeLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: "lead-1",
    workspace_id: "ws-1",
    contact_id: "contact-abc",
    stage: "discovered",
    score: 60,
    notes: null,
    extra: {},
    meeting_scheduled_at: null,
    booked_at: null,
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-02T10:00:00Z",
    ...overrides,
  };
}

function makeProposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    id: "prop-1",
    workspace_id: "ws-1",
    contact_id: "contact-abc",
    title: "Leadership Training Proposal",
    status: "draft",
    content: {},
    cloudinary_url: null,
    sent_at: null,
    created_at: "2026-01-01T12:00:00Z",
    approval_status: "pending_approval",
    approved_by: null,
    approved_at: null,
    rejected_reason: null,
    outbound_message_id: null,
    delivery_status: null,
    lead_id: null,
    expected_value_inr: null,
    actual_value_inr: null,
    client_status: null,
    client_accepted_at: null,
    client_declined_at: null,
    ...overrides,
  };
}

function mockLoaded(lead: Lead) {
  mockUseGetLead.mockReturnValue({
    data: lead,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useGetLead>);
}

function mockNoProposals() {
  mockUseProposalsForContact.mockReturnValue({
    data: { items: [], total: 0, limit: 20, offset: 0 } as ProposalListOut,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useProposalsForContact>);
}

// Import page after all mocks are registered.
const { default: LeadDetailPage } = await import(
  "@/app/(dashboard)/crm/leads/[id]/page"
);

vi.mock("next/navigation", async (importOriginal) => {
  const original = await importOriginal<typeof import("next/navigation")>();
  return {
    ...original,
    useParams: () => ({ id: "lead-1" }),
    useRouter: () => ({ push: vi.fn() }),
  };
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("LeadDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNoProposals();
  });

  describe("discovered state", () => {
    it("shows Mark Engaged and Mark Lost buttons", () => {
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      expect(screen.getByRole("button", { name: /mark engaged/i })).not.toBeNull();
      expect(screen.getByRole("button", { name: /mark lost/i })).not.toBeNull();
    });

    it("does not show Set meeting time button", () => {
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      expect(screen.queryByRole("button", { name: /set meeting time/i })).toBeNull();
    });

    it("does not show Generate proposal button", () => {
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      expect(screen.queryByRole("button", { name: /generate proposal/i })).toBeNull();
    });

    it("calls advance mutateAsync with the lead id", async () => {
      mockAdvance.mockResolvedValueOnce({});
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /mark engaged/i }));
      await waitFor(() =>
        expect(mockAdvance).toHaveBeenCalledWith({ leadId: "lead-1" }),
      );
    });

    it("shows error when advance fails", async () => {
      mockAdvance.mockRejectedValueOnce(new Error("Permission denied"));
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /mark engaged/i }));
      await waitFor(() =>
        expect(screen.getByText("Action failed — please try again.")).not.toBeNull(),
      );
    });

    it("calls mark lost mutateAsync with the lead id", async () => {
      mockMarkLost.mockResolvedValueOnce({});
      mockLoaded(makeLead({ stage: "discovered" }));
      render(<LeadDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /mark lost/i }));
      await waitFor(() =>
        expect(mockMarkLost).toHaveBeenCalledWith({ leadId: "lead-1" }),
      );
    });
  });

  describe("meeting_scheduled state", () => {
    it("shows Set meeting time and Mark Meeting Completed buttons", () => {
      mockLoaded(makeLead({ stage: "meeting_scheduled" }));
      render(<LeadDetailPage />);
      expect(
        screen.getByRole("button", { name: /set meeting time/i }),
      ).not.toBeNull();
      expect(
        screen.getByRole("button", { name: /mark meeting completed/i }),
      ).not.toBeNull();
    });

    it("opens meeting dialog when Set meeting time is clicked", () => {
      mockLoaded(makeLead({ stage: "meeting_scheduled" }));
      render(<LeadDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /set meeting time/i }));
      expect(screen.getByTestId("meeting-dialog")).not.toBeNull();
    });

    it("shows meeting_scheduled_at when set", () => {
      mockLoaded(
        makeLead({
          stage: "meeting_scheduled",
          meeting_scheduled_at: "2026-07-15T10:00:00Z",
        }),
      );
      render(<LeadDetailPage />);
      // Format is "Jul 15, ..." — just assert the month is present.
      expect(screen.getByText(/Jul 15/)).not.toBeNull();
    });
  });

  describe("meeting_completed state", () => {
    it("shows Generate proposal and Mark Booked buttons", () => {
      mockLoaded(makeLead({ stage: "meeting_completed" }));
      render(<LeadDetailPage />);
      expect(
        screen.getByRole("button", { name: /generate proposal/i }),
      ).not.toBeNull();
      expect(
        screen.getByRole("button", { name: /mark booked/i }),
      ).not.toBeNull();
    });

    it("opens generate proposal dialog when clicked", () => {
      mockLoaded(makeLead({ stage: "meeting_completed" }));
      render(<LeadDetailPage />);
      fireEvent.click(screen.getByRole("button", { name: /generate proposal/i }));
      expect(screen.getByTestId("generate-dialog")).not.toBeNull();
    });

    it("does not show Set meeting time button", () => {
      mockLoaded(makeLead({ stage: "meeting_completed" }));
      render(<LeadDetailPage />);
      expect(screen.queryByRole("button", { name: /set meeting time/i })).toBeNull();
    });
  });

  describe("terminal states", () => {
    it("shows no action buttons when booked", () => {
      mockLoaded(
        makeLead({ stage: "booked", booked_at: "2026-06-01T09:00:00Z" }),
      );
      render(<LeadDetailPage />);
      expect(screen.queryByRole("button", { name: /mark/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /generate/i })).toBeNull();
    });

    it("shows no action buttons when lost", () => {
      mockLoaded(makeLead({ stage: "lost" }));
      render(<LeadDetailPage />);
      expect(screen.queryByRole("button", { name: /mark/i })).toBeNull();
    });

    it("shows booked_at in metadata when booked", () => {
      mockLoaded(
        makeLead({ stage: "booked", booked_at: "2026-06-01T09:00:00Z" }),
      );
      render(<LeadDetailPage />);
      // MetaCell "Booked at" should be visible
      expect(screen.getByText("Booked at")).not.toBeNull();
    });
  });

  describe("proposal history panel", () => {
    it("shows empty state when no proposals", () => {
      mockLoaded(makeLead());
      render(<LeadDetailPage />);
      expect(
        screen.getByText("No proposals yet for this contact."),
      ).not.toBeNull();
    });

    it("renders proposal rows with title, approval badge, and View link", () => {
      mockLoaded(makeLead({ stage: "meeting_completed" }));
      mockUseProposalsForContact.mockReturnValue({
        data: {
          items: [
            makeProposal({ title: "Leadership Training Proposal" }),
          ],
          total: 1,
          limit: 20,
          offset: 0,
        } as ProposalListOut,
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useProposalsForContact>);
      render(<LeadDetailPage />);
      expect(screen.getByText("Leadership Training Proposal")).not.toBeNull();
      expect(screen.getByRole("link", { name: "View" })).not.toBeNull();
    });

    it("shows sent timestamp when proposal is sent", () => {
      mockLoaded(makeLead());
      mockUseProposalsForContact.mockReturnValue({
        data: {
          items: [
            makeProposal({
              sent_at: "2026-06-10T08:00:00Z",
              status: "sent",
              approval_status: "approved",
            }),
          ],
          total: 1,
          limit: 20,
          offset: 0,
        } as ProposalListOut,
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useProposalsForContact>);
      render(<LeadDetailPage />);
      expect(screen.getByText(/Sent Jun 10/)).not.toBeNull();
    });
  });

  describe("loading and error states", () => {
    it("shows skeleton rows while loading", () => {
      mockUseGetLead.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as unknown as ReturnType<typeof useGetLead>);
      const { container } = render(<LeadDetailPage />);
      expect(screen.queryByText("Lead not found.")).toBeNull();
      // No action buttons rendered during loading
      expect(container.querySelectorAll("button").length).toBe(0);
    });

    it("shows not-found message on error", () => {
      mockUseGetLead.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as unknown as ReturnType<typeof useGetLead>);
      render(<LeadDetailPage />);
      expect(screen.getByText("Lead not found.")).not.toBeNull();
    });
  });

  describe("stage timeline", () => {
    it("renders the stage timeline with the current stage", () => {
      mockLoaded(makeLead({ stage: "engaged" }));
      render(<LeadDetailPage />);
      expect(screen.getByTestId("stage-timeline-engaged")).not.toBeNull();
    });
  });
});
