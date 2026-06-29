import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import type {
  ApprovalRequestOut,
  ApprovalTimelineEventOut,
} from "@/features/approvals/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("@/features/approvals/api/use-approvals", () => ({
  useApprovals: vi.fn(),
  useMyReviewApprovals: vi.fn(),
  useApprovalDetail: vi.fn(),
  useApprovalTimeline: vi.fn(),
  useCreateApproval: vi.fn(),
  useAssignReviewer: vi.fn(),
  useApproveRequest: vi.fn(),
  useRejectRequest: vi.fn(),
  useCancelRequest: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/approvals/some-id"),
  useParams: vi.fn(() => ({ id: "some-id" })),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useApprovalDetail,
  useApprovalTimeline,
  useApproveRequest,
  useRejectRequest,
  useCancelRequest,
} from "@/features/approvals/api/use-approvals";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseApprovalDetail = vi.mocked(useApprovalDetail);
const mockUseApprovalTimeline = vi.mocked(useApprovalTimeline);
const mockUseApproveRequest = vi.mocked(useApproveRequest);
const mockUseRejectRequest = vi.mocked(useRejectRequest);
const mockUseCancelRequest = vi.mocked(useCancelRequest);

const { ApprovalDetailPage } = await import("./approval-detail-page");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-detail-1";
const APPROVAL_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
const USER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc";
const REVIEWER_ID = "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr";

function makeApproval(overrides: Partial<ApprovalRequestOut> = {}): ApprovalRequestOut {
  return {
    id: APPROVAL_ID,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    entity_type: "task",
    entity_id: null,
    requested_by: USER_ID,
    assigned_reviewer: null,
    priority: "medium",
    status: "pending",
    decision: "none",
    comments: null,
    due_date: null,
    reviewed_at: null,
    created_at: "2026-06-28T10:00:00Z",
    updated_at: "2026-06-28T10:00:00Z",
    ...overrides,
  };
}

function makeTimelineEvent(
  overrides: Partial<ApprovalTimelineEventOut> = {}
): ApprovalTimelineEventOut {
  return {
    id: "ev-1111",
    approval_request_id: APPROVAL_ID,
    tenant_id: "org-1",
    event_type: "request_created",
    actor_user_id: USER_ID,
    notes: null,
    occurred_at: "2026-06-28T10:00:00Z",
    ...overrides,
  };
}

function setupMocks({
  workspaceId = WS_ID,
  approval = makeApproval() as ApprovalRequestOut | undefined,
  detailLoading = false,
  detailError = false,
  timeline = [] as ApprovalTimelineEventOut[],
  timelineLoading = false,
  timelineError = false,
  approveMutate = vi.fn(),
  rejectMutate = vi.fn(),
  cancelMutate = vi.fn(),
}: {
  workspaceId?: string | null;
  approval?: ApprovalRequestOut | undefined;
  detailLoading?: boolean;
  detailError?: boolean;
  timeline?: ApprovalTimelineEventOut[];
  timelineLoading?: boolean;
  timelineError?: boolean;
  approveMutate?: ReturnType<typeof vi.fn>;
  rejectMutate?: ReturnType<typeof vi.fn>;
  cancelMutate?: ReturnType<typeof vi.fn>;
} = {}) {
  mockUseWorkspace.mockReturnValue({
    workspaceId: workspaceId ?? null,
  } as ReturnType<typeof useWorkspace>);
  mockUseApprovalDetail.mockReturnValue({
    data: approval,
    isLoading: detailLoading,
    isError: detailError,
  } as ReturnType<typeof useApprovalDetail>);
  mockUseApprovalTimeline.mockReturnValue({
    data: timeline,
    isLoading: timelineLoading,
    isError: timelineError,
  } as ReturnType<typeof useApprovalTimeline>);
  mockUseApproveRequest.mockReturnValue({
    mutate: approveMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useApproveRequest>);
  mockUseRejectRequest.mockReturnValue({
    mutate: rejectMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRejectRequest>);
  mockUseCancelRequest.mockReturnValue({
    mutate: cancelMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCancelRequest>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ApprovalDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Workspace guard
  describe("workspace guard", () => {
    it("shows no-workspace message when workspaceId is null", () => {
      setupMocks({ workspaceId: null });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-detail-no-workspace")).not.toBeNull();
    });

    it("does not render detail when no workspace", () => {
      setupMocks({ workspaceId: null });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approval-detail-page")).toBeNull();
    });
  });

  // Loading
  describe("loading states", () => {
    it("shows skeleton when detail is loading", () => {
      setupMocks({ detailLoading: true });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-detail-skeleton")).not.toBeNull();
    });

    it("does not show detail page while loading", () => {
      setupMocks({ detailLoading: true });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approval-detail-page")).toBeNull();
    });
  });

  // Error
  describe("error states", () => {
    it("shows error message when detail fetch fails", () => {
      setupMocks({ detailError: true, detailLoading: false, approval: undefined });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-detail-error")).not.toBeNull();
    });

    it("shows error when approval is undefined", () => {
      setupMocks();
      // Override after setupMocks — destructuring defaults activate on undefined,
      // so we must override directly to truly pass undefined as data.
      mockUseApprovalDetail.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useApprovalDetail>);
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-detail-error")).not.toBeNull();
    });
  });

  // Detail rendering
  describe("approval detail", () => {
    it("shows the detail page", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-detail-page")).not.toBeNull();
    });

    it("renders back link", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("back-to-approvals")).not.toBeNull();
    });

    it("shows priority badge", () => {
      setupMocks({ approval: makeApproval({ priority: "urgent" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-priority-badge-urgent")).not.toBeNull();
    });

    it("shows status badge", () => {
      setupMocks({ approval: makeApproval({ status: "in_review" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-status-badge-in_review")).not.toBeNull();
    });

    it("shows reviewer when assigned", () => {
      setupMocks({ approval: makeApproval({ assigned_reviewer: REVIEWER_ID }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-reviewer")).not.toBeNull();
    });

    it("does not show reviewer when unassigned", () => {
      setupMocks({ approval: makeApproval({ assigned_reviewer: null }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("detail-reviewer")).toBeNull();
    });

    it("shows entity id when present", () => {
      setupMocks({
        approval: makeApproval({ entity_id: "dddddddd-dddd-dddd-dddd-dddddddddddd" }),
      });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-entity-id")).not.toBeNull();
    });

    it("does not show entity id when null", () => {
      setupMocks({ approval: makeApproval({ entity_id: null }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("detail-entity-id")).toBeNull();
    });

    it("shows due date when present", () => {
      setupMocks({ approval: makeApproval({ due_date: "2026-07-01" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-due-date")).not.toBeNull();
    });

    it("does not show due date when null", () => {
      setupMocks({ approval: makeApproval({ due_date: null }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("detail-due-date")).toBeNull();
    });

    it("shows comments when present", () => {
      setupMocks({ approval: makeApproval({ comments: "Please review carefully" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-comments")).not.toBeNull();
    });

    it("does not show comments when null", () => {
      setupMocks({ approval: makeApproval({ comments: null }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("detail-comments")).toBeNull();
    });

    it("shows reviewed_at when present", () => {
      setupMocks({
        approval: makeApproval({ reviewed_at: "2026-06-28T12:00:00Z" }),
      });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("detail-reviewed-at")).not.toBeNull();
    });
  });

  // Action buttons
  describe("action buttons", () => {
    it("shows approve/reject/cancel buttons for pending request", () => {
      setupMocks({ approval: makeApproval({ status: "pending" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-actions")).not.toBeNull();
      expect(screen.getByTestId("approve-btn")).not.toBeNull();
      expect(screen.getByTestId("reject-btn")).not.toBeNull();
      expect(screen.getByTestId("cancel-btn")).not.toBeNull();
    });

    it("shows action buttons for in_review request", () => {
      setupMocks({ approval: makeApproval({ status: "in_review" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-actions")).not.toBeNull();
    });

    it("hides action buttons for approved request", () => {
      setupMocks({ approval: makeApproval({ status: "approved" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approval-actions")).toBeNull();
    });

    it("hides action buttons for rejected request", () => {
      setupMocks({ approval: makeApproval({ status: "rejected" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approval-actions")).toBeNull();
    });

    it("hides action buttons for cancelled request", () => {
      setupMocks({ approval: makeApproval({ status: "cancelled" }) });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approval-actions")).toBeNull();
    });
  });

  // Approve dialog
  describe("approve dialog", () => {
    it("opens approve dialog on approve button click", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      expect(screen.getByTestId("approve-dialog")).not.toBeNull();
    });

    it("does not show approve dialog initially", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("approve-dialog")).toBeNull();
    });

    it("shows comments input in approve dialog", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      expect(screen.getByTestId("decision-comments-input")).not.toBeNull();
    });

    it("shows approve submit button", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      expect(screen.getByTestId("approve-submit-btn")).not.toBeNull();
    });

    it("calls approve mutate on submit", () => {
      const approveMutate = vi.fn();
      setupMocks({ approveMutate });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      fireEvent.submit(screen.getByTestId("approve-dialog").querySelector("form")!);
      expect(approveMutate).toHaveBeenCalledOnce();
    });

    it("closes approve dialog on cancel", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      const dialog = screen.getByTestId("approve-dialog");
      fireEvent.click(dialog.querySelector("[type='button']")!);
      expect(screen.queryByTestId("approve-dialog")).toBeNull();
    });

    it("shows error when approve fails", () => {
      const approveMutate = vi.fn((_args: unknown, { onError }: { onError: (e: Error) => void }) => {
        onError(new Error("Permission denied"));
      });
      setupMocks({ approveMutate });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("approve-btn"));
      act(() => {
        fireEvent.submit(screen.getByTestId("approve-dialog").querySelector("form")!);
      });
      expect(screen.getByTestId("decision-error")).not.toBeNull();
    });
  });

  // Reject dialog
  describe("reject dialog", () => {
    it("opens reject dialog on reject button click", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("reject-btn"));
      expect(screen.getByTestId("reject-dialog")).not.toBeNull();
    });

    it("shows reject submit button", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("reject-btn"));
      expect(screen.getByTestId("reject-submit-btn")).not.toBeNull();
    });

    it("calls reject mutate on submit", () => {
      const rejectMutate = vi.fn();
      setupMocks({ rejectMutate });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("reject-btn"));
      fireEvent.submit(screen.getByTestId("reject-dialog").querySelector("form")!);
      expect(rejectMutate).toHaveBeenCalledOnce();
    });

    it("does not show reject dialog initially", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("reject-dialog")).toBeNull();
    });
  });

  // Cancel dialog
  describe("cancel dialog", () => {
    it("opens cancel dialog on cancel button click", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("cancel-btn"));
      expect(screen.getByTestId("cancel-dialog")).not.toBeNull();
    });

    it("shows cancel confirm button", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("cancel-btn"));
      expect(screen.getByTestId("cancel-confirm-btn")).not.toBeNull();
    });

    it("calls cancel mutate on confirm", () => {
      const cancelMutate = vi.fn();
      setupMocks({ cancelMutate });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("cancel-btn"));
      fireEvent.click(screen.getByTestId("cancel-confirm-btn"));
      expect(cancelMutate).toHaveBeenCalledOnce();
    });

    it("does not show cancel dialog initially", () => {
      setupMocks();
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("cancel-dialog")).toBeNull();
    });

    it("shows error when cancel fails", () => {
      const cancelMutate = vi.fn((_args: unknown, { onError }: { onError: (e: Error) => void }) => {
        onError(new Error("Cannot cancel"));
      });
      setupMocks({ cancelMutate });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      fireEvent.click(screen.getByTestId("cancel-btn"));
      act(() => {
        fireEvent.click(screen.getByTestId("cancel-confirm-btn"));
      });
      expect(screen.getByTestId("cancel-error")).not.toBeNull();
    });
  });

  // Timeline
  describe("timeline", () => {
    it("shows timeline section when events exist", () => {
      setupMocks({ timeline: [makeTimelineEvent()] });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("approval-timeline")).not.toBeNull();
    });

    it("shows timeline skeleton when loading", () => {
      setupMocks({ timelineLoading: true });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-skeleton")).not.toBeNull();
    });

    it("shows timeline error", () => {
      setupMocks({ timelineError: true, timelineLoading: false });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-error")).not.toBeNull();
    });

    it("shows empty timeline message when no events", () => {
      setupMocks({ timeline: [] });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-empty")).not.toBeNull();
    });

    it("renders timeline events", () => {
      const events = [
        makeTimelineEvent({ event_type: "request_created" }),
        makeTimelineEvent({ id: "ev-2", event_type: "reviewer_assigned" }),
      ];
      setupMocks({ timeline: events });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-event-0")).not.toBeNull();
      expect(screen.getByTestId("timeline-event-1")).not.toBeNull();
    });

    it("renders event type label", () => {
      const events = [makeTimelineEvent({ event_type: "approved" })];
      setupMocks({ timeline: events });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-event-type-0").textContent).toBe("Approved");
    });

    it("renders event notes when present", () => {
      const events = [makeTimelineEvent({ notes: "Looks great!" })];
      setupMocks({ timeline: events });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.getByTestId("timeline-event-notes-0")).not.toBeNull();
    });

    it("does not render notes element when notes is null", () => {
      const events = [makeTimelineEvent({ notes: null })];
      setupMocks({ timeline: events });
      render(<ApprovalDetailPage approvalId={APPROVAL_ID} />);
      expect(screen.queryByTestId("timeline-event-notes-0")).toBeNull();
    });
  });
});
