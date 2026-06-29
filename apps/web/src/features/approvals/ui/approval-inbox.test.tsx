import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  ApprovalListPage,
  ApprovalRequestOut,
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

// Next/navigation mock for Link
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/approvals"),
  useParams: vi.fn(() => ({})),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useApprovals,
  useMyReviewApprovals,
} from "@/features/approvals/api/use-approvals";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseApprovals = vi.mocked(useApprovals);
const mockUseMyReviewApprovals = vi.mocked(useMyReviewApprovals);

const { ApprovalInbox } = await import("./approval-inbox");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-inbox-1";
const APPROVAL_A = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
const APPROVAL_B = "ffffffff-ffff-ffff-ffff-ffffffffffff";

function makeApproval(overrides: Partial<ApprovalRequestOut> = {}): ApprovalRequestOut {
  return {
    id: APPROVAL_A,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    entity_type: "task",
    entity_id: null,
    requested_by: "user-req-1",
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

function makeListPage(overrides: Partial<ApprovalListPage> = {}): ApprovalListPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function setupMocks({
  workspaceId = WS_ID,
  approvals = [] as ApprovalRequestOut[],
  approvalsLoading = false,
  approvalsError = false,
  approvalsNextCursor = null as string | null,
  approvalsHasMore = false,
  myReviews = [] as ApprovalRequestOut[],
  myReviewsLoading = false,
  myReviewsError = false,
  myReviewsHasMore = false,
}: {
  workspaceId?: string | null;
  approvals?: ApprovalRequestOut[];
  approvalsLoading?: boolean;
  approvalsError?: boolean;
  approvalsNextCursor?: string | null;
  approvalsHasMore?: boolean;
  myReviews?: ApprovalRequestOut[];
  myReviewsLoading?: boolean;
  myReviewsError?: boolean;
  myReviewsHasMore?: boolean;
} = {}) {
  mockUseWorkspace.mockReturnValue({ workspaceId: workspaceId ?? null } as ReturnType<typeof useWorkspace>);
  mockUseApprovals.mockReturnValue({
    data: makeListPage({ items: approvals, next_cursor: approvalsNextCursor, has_more: approvalsHasMore }),
    isLoading: approvalsLoading,
    isError: approvalsError,
  } as ReturnType<typeof useApprovals>);
  mockUseMyReviewApprovals.mockReturnValue({
    data: makeListPage({ items: myReviews, has_more: myReviewsHasMore }),
    isLoading: myReviewsLoading,
    isError: myReviewsError,
  } as ReturnType<typeof useMyReviewApprovals>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ApprovalInbox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Workspace guard
  describe("workspace guard", () => {
    it("shows no-workspace message when workspaceId is null", () => {
      setupMocks({ workspaceId: null });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("approvals-no-workspace")).not.toBeNull();
    });

    it("does not show main content when workspaceId is null", () => {
      setupMocks({ workspaceId: null });
      render(<ApprovalInbox />);
      expect(screen.queryByTestId("approval-inbox")).toBeNull();
    });

    it("shows approval inbox when workspaceId is set", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("approval-inbox")).not.toBeNull();
    });
  });

  // Tabs
  describe("tabs", () => {
    it("renders both tab triggers", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("tab-all")).not.toBeNull();
      expect(screen.getByTestId("tab-my-reviews")).not.toBeNull();
    });

    it("shows approval tabs", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("approval-tabs")).not.toBeNull();
    });
  });

  // Loading states
  describe("loading states", () => {
    it("shows all-approvals skeleton when loading", () => {
      setupMocks({ approvalsLoading: true });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("all-approvals-list-skeleton")).not.toBeNull();
    });

    it("does not show approval list when loading", () => {
      setupMocks({ approvalsLoading: true });
      render(<ApprovalInbox />);
      expect(screen.queryByTestId("all-approvals-list")).toBeNull();
    });
  });

  // Error states
  describe("error states", () => {
    it("shows error when approvals fetch fails", () => {
      setupMocks({ approvalsError: true, approvalsLoading: false });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("all-approvals-list-error")).not.toBeNull();
    });
  });

  // Empty states
  describe("empty states", () => {
    it("shows empty message when no approvals", () => {
      setupMocks({ approvals: [] });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("all-approvals-list-empty")).not.toBeNull();
    });
  });

  // Data rendering
  describe("approval rows", () => {
    it("renders approval row for each item", () => {
      const items = [
        makeApproval({ id: APPROVAL_A }),
        makeApproval({ id: APPROVAL_B }),
      ];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.getByTestId(`approval-row-${APPROVAL_A}`)).not.toBeNull();
      expect(screen.getByTestId(`approval-row-${APPROVAL_B}`)).not.toBeNull();
    });

    it("renders entity type in each row", () => {
      const items = [makeApproval({ id: APPROVAL_A, entity_type: "proposal" })];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.getByTestId(`approval-entity-type-${APPROVAL_A}`)).not.toBeNull();
    });

    it("renders priority badge", () => {
      const items = [makeApproval({ id: APPROVAL_A, priority: "urgent" })];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("priority-badge-urgent")).not.toBeNull();
    });

    it("renders status badge", () => {
      const items = [makeApproval({ id: APPROVAL_A, status: "in_review" })];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("status-badge-in_review")).not.toBeNull();
    });

    it("renders due date when set", () => {
      const items = [makeApproval({ id: APPROVAL_A, due_date: "2026-07-15" })];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.getByTestId(`approval-due-${APPROVAL_A}`)).not.toBeNull();
    });

    it("does not render due date when null", () => {
      const items = [makeApproval({ id: APPROVAL_A, due_date: null })];
      setupMocks({ approvals: items });
      render(<ApprovalInbox />);
      expect(screen.queryByTestId(`approval-due-${APPROVAL_A}`)).toBeNull();
    });
  });

  // Priority badges
  describe("priority badges", () => {
    it.each(["low", "medium", "high", "urgent"] as const)("renders %s priority badge", (p) => {
      setupMocks({ approvals: [makeApproval({ priority: p })] });
      render(<ApprovalInbox />);
      expect(screen.getByTestId(`priority-badge-${p}`)).not.toBeNull();
    });
  });

  // Status badges
  describe("status badges", () => {
    it.each(["pending", "in_review", "approved", "rejected", "cancelled"] as const)(
      "renders %s status badge",
      (s) => {
        setupMocks({ approvals: [makeApproval({ status: s })] });
        render(<ApprovalInbox />);
        expect(screen.getByTestId(`status-badge-${s}`)).not.toBeNull();
      }
    );
  });

  // Filters
  describe("filters", () => {
    it("renders filter bar", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("approval-filters")).not.toBeNull();
    });

    it("renders status filter dropdown", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("filter-status")).not.toBeNull();
    });

    it("renders priority filter dropdown", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("filter-priority")).not.toBeNull();
    });

    it("renders reviewer filter input", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.getByTestId("filter-reviewer")).not.toBeNull();
    });

    it("does not show clear button when no filters active", () => {
      setupMocks();
      render(<ApprovalInbox />);
      expect(screen.queryByTestId("clear-filters-btn")).toBeNull();
    });

    it("shows clear button after setting status filter", () => {
      setupMocks();
      render(<ApprovalInbox />);
      fireEvent.change(screen.getByTestId("filter-status"), {
        target: { value: "pending" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });

    it("hides clear button after clearing filters", () => {
      setupMocks();
      render(<ApprovalInbox />);
      fireEvent.change(screen.getByTestId("filter-status"), {
        target: { value: "pending" },
      });
      fireEvent.click(screen.getByTestId("clear-filters-btn"));
      expect(screen.queryByTestId("clear-filters-btn")).toBeNull();
    });

    it("shows clear button after setting priority filter", () => {
      setupMocks();
      render(<ApprovalInbox />);
      fireEvent.change(screen.getByTestId("filter-priority"), {
        target: { value: "high" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });

    it("shows clear button after setting reviewer filter", () => {
      setupMocks();
      render(<ApprovalInbox />);
      fireEvent.change(screen.getByTestId("filter-reviewer"), {
        target: { value: "some-user-id" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });
  });

  // Pagination
  describe("pagination", () => {
    it("shows next button when has_more is true", () => {
      setupMocks({
        approvals: [makeApproval()],
        approvalsHasMore: true,
        approvalsNextCursor: "cursor_tok",
      });
      render(<ApprovalInbox />);
      expect(screen.getByTestId("all-approvals-list-next-btn")).not.toBeNull();
    });

    it("does not show next button when has_more is false", () => {
      setupMocks({ approvals: [makeApproval()], approvalsHasMore: false });
      render(<ApprovalInbox />);
      expect(screen.queryByTestId("all-approvals-list-next-btn")).toBeNull();
    });

    it("does not show prev button on first page", () => {
      setupMocks({ approvals: [makeApproval()] });
      render(<ApprovalInbox />);
      expect(screen.queryByTestId("all-approvals-list-prev-btn")).toBeNull();
    });
  });

  // My reviews tab
  // userEvent.click is required for Radix UI tabs: Radix uses onPointerDown
  // internally, and fireEvent.click alone does not activate lazy-mounted panels.
  describe("my reviews tab", () => {
    it("shows my-reviews skeleton when loading", async () => {
      const user = userEvent.setup();
      setupMocks({ myReviewsLoading: true });
      render(<ApprovalInbox />);
      await user.click(screen.getByTestId("tab-my-reviews"));
      expect(screen.getByTestId("my-reviews-skeleton")).not.toBeNull();
    });

    it("shows my-reviews error", async () => {
      const user = userEvent.setup();
      setupMocks({ myReviewsError: true, myReviewsLoading: false });
      render(<ApprovalInbox />);
      await user.click(screen.getByTestId("tab-my-reviews"));
      expect(screen.getByTestId("my-reviews-error")).not.toBeNull();
    });

    it("shows empty state on my reviews tab when no items", async () => {
      const user = userEvent.setup();
      setupMocks({ myReviews: [] });
      render(<ApprovalInbox />);
      await user.click(screen.getByTestId("tab-my-reviews"));
      expect(screen.getByTestId("my-reviews-empty")).not.toBeNull();
    });

    it("shows my-reviews items", async () => {
      const user = userEvent.setup();
      setupMocks({ myReviews: [makeApproval({ id: APPROVAL_B })] });
      render(<ApprovalInbox />);
      await user.click(screen.getByTestId("tab-my-reviews"));
      expect(screen.getByTestId(`approval-row-${APPROVAL_B}`)).not.toBeNull();
    });

    it("shows next button on my reviews when has_more", async () => {
      const user = userEvent.setup();
      setupMocks({
        myReviews: [makeApproval({ id: APPROVAL_B })],
        myReviewsHasMore: true,
      });
      render(<ApprovalInbox />);
      await user.click(screen.getByTestId("tab-my-reviews"));
      expect(screen.getByTestId("my-reviews-next-btn")).not.toBeNull();
    });
  });
});
