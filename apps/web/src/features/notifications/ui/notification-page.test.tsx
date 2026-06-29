import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type {
  NotificationListPage,
  NotificationOut,
  UnreadCountOut,
} from "@/features/notifications/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("@/features/notifications/api/use-notifications", () => ({
  useNotifications: vi.fn(),
  useUnreadCount: vi.fn(),
  useMarkAllRead: vi.fn(),
  useMarkNotificationRead: vi.fn(),
  useDeleteNotification: vi.fn(),
  useCreateNotification: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/notifications"),
  useParams: vi.fn(() => ({})),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useNotifications,
  useUnreadCount,
  useMarkAllRead,
  useMarkNotificationRead,
  useDeleteNotification,
} from "@/features/notifications/api/use-notifications";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseNotifications = vi.mocked(useNotifications);
const mockUseUnreadCount = vi.mocked(useUnreadCount);
const mockUseMarkAllRead = vi.mocked(useMarkAllRead);
const mockUseMarkNotificationRead = vi.mocked(useMarkNotificationRead);
const mockUseDeleteNotification = vi.mocked(useDeleteNotification);

const { NotificationPage } = await import("./notification-page");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-page-1";
const NOTIF_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const NOTIF_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

const TODAY_ISO = new Date().toISOString();
const OLD_ISO = "2026-01-01T10:00:00Z";

function makeNotification(overrides: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id: NOTIF_A,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    user_id: "user-1",
    notification_type: "approval_assigned",
    title: "New approval",
    message: "You have a new approval request",
    entity_type: null,
    entity_id: null,
    priority: "medium",
    is_read: false,
    read_at: null,
    metadata: null,
    created_at: TODAY_ISO,
    ...overrides,
  };
}

function makeListPage(overrides: Partial<NotificationListPage> = {}): NotificationListPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function makeCount(count: number): UnreadCountOut {
  return { count };
}

function setupMocks({
  workspaceId = WS_ID as string | null,
  notifications = [] as NotificationOut[],
  listLoading = false,
  listError = false,
  hasMore = false,
  nextCursor = null as string | null,
  unreadCount = 0,
  markAllPending = false,
  markReadPending = false,
  deletePending = false,
}: {
  workspaceId?: string | null;
  notifications?: NotificationOut[];
  listLoading?: boolean;
  listError?: boolean;
  hasMore?: boolean;
  nextCursor?: string | null;
  unreadCount?: number;
  markAllPending?: boolean;
  markReadPending?: boolean;
  deletePending?: boolean;
} = {}) {
  mockUseWorkspace.mockReturnValue({
    workspaceId: workspaceId ?? null,
    orgId: "org-1",
  } as ReturnType<typeof useWorkspace>);
  mockUseNotifications.mockReturnValue({
    data: makeListPage({ items: notifications, next_cursor: nextCursor, has_more: hasMore }),
    isLoading: listLoading,
    isError: listError,
  } as ReturnType<typeof useNotifications>);
  mockUseUnreadCount.mockReturnValue({
    data: makeCount(unreadCount),
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useUnreadCount>);
  mockUseMarkAllRead.mockReturnValue({
    mutate: vi.fn(),
    isPending: markAllPending,
  } as unknown as ReturnType<typeof useMarkAllRead>);
  mockUseMarkNotificationRead.mockReturnValue({
    mutate: vi.fn(),
    isPending: markReadPending,
  } as unknown as ReturnType<typeof useMarkNotificationRead>);
  mockUseDeleteNotification.mockReturnValue({
    mutate: vi.fn(),
    isPending: deletePending,
  } as unknown as ReturnType<typeof useDeleteNotification>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("NotificationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Workspace guard
  describe("workspace guard", () => {
    it("shows no-workspace message when workspaceId is null", () => {
      setupMocks({ workspaceId: null });
      render(<NotificationPage />);
      expect(screen.getByTestId("notifications-no-workspace")).not.toBeNull();
    });

    it("does not show main page when no workspace", () => {
      setupMocks({ workspaceId: null });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-page")).toBeNull();
    });

    it("shows notification page when workspace is set", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-page")).not.toBeNull();
    });
  });

  // Loading state
  describe("loading state", () => {
    it("shows skeleton when loading", () => {
      setupMocks({ listLoading: true });
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-list-skeleton")).not.toBeNull();
    });

    it("does not show notification list when loading", () => {
      setupMocks({ listLoading: true });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list")).toBeNull();
    });

    it("does not show empty state when loading", () => {
      setupMocks({ listLoading: true });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list-empty")).toBeNull();
    });
  });

  // Error state
  describe("error state", () => {
    it("shows error message when fetch fails", () => {
      setupMocks({ listError: true, listLoading: false });
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-list-error")).not.toBeNull();
    });

    it("does not show notification list on error", () => {
      setupMocks({ listError: true, listLoading: false });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list")).toBeNull();
    });
  });

  // Empty state
  describe("empty state", () => {
    it("shows empty message when no notifications", () => {
      setupMocks({ notifications: [] });
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-list-empty")).not.toBeNull();
    });

    it("does not show notification list when empty", () => {
      setupMocks({ notifications: [] });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list")).toBeNull();
    });
  });

  // Data rendering
  describe("notification items", () => {
    it("renders notification item for each notification", () => {
      const items = [
        makeNotification({ id: NOTIF_A }),
        makeNotification({ id: NOTIF_B }),
      ];
      setupMocks({ notifications: items });
      render(<NotificationPage />);
      expect(screen.getByTestId(`notification-item-${NOTIF_A}`)).not.toBeNull();
      expect(screen.getByTestId(`notification-item-${NOTIF_B}`)).not.toBeNull();
    });

    it("renders notification title", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, title: "My title" })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`notification-title-${NOTIF_A}`).textContent).toBe("My title");
    });

    it("renders entity type when present", () => {
      setupMocks({
        notifications: [makeNotification({ id: NOTIF_A, entity_type: "proposal" })],
      });
      render(<NotificationPage />);
      expect(screen.getByTestId(`notification-entity-type-${NOTIF_A}`)).not.toBeNull();
    });

    it("does not render entity type when null", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, entity_type: null })] });
      render(<NotificationPage />);
      expect(screen.queryByTestId(`notification-entity-type-${NOTIF_A}`)).toBeNull();
    });

    it("renders priority badge", () => {
      setupMocks({ notifications: [makeNotification({ priority: "high" })] });
      render(<NotificationPage />);
      expect(screen.getByTestId("priority-badge-high")).not.toBeNull();
    });
  });

  // Read/unread indicators
  describe("read state indicators", () => {
    it("shows unread indicator for unread notifications", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: false })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`notification-unread-indicator-${NOTIF_A}`)).not.toBeNull();
    });

    it("shows read indicator for read notifications", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: true })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`notification-read-indicator-${NOTIF_A}`)).not.toBeNull();
    });

    it("does not show unread indicator for read notifications", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: true })] });
      render(<NotificationPage />);
      expect(screen.queryByTestId(`notification-unread-indicator-${NOTIF_A}`)).toBeNull();
    });

    it("shows mark-read button for unread notifications", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: false })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`mark-read-btn-${NOTIF_A}`)).not.toBeNull();
    });

    it("does not show mark-read button for read notifications", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: true })] });
      render(<NotificationPage />);
      expect(screen.queryByTestId(`mark-read-btn-${NOTIF_A}`)).toBeNull();
    });
  });

  // Delete button
  describe("delete button", () => {
    it("renders delete button for each notification", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`delete-btn-${NOTIF_A}`)).not.toBeNull();
    });

    it("calls delete mutation when delete button clicked", () => {
      const deleteFn = vi.fn();
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A })] });
      mockUseDeleteNotification.mockReturnValue({
        mutate: deleteFn,
        isPending: false,
      } as unknown as ReturnType<typeof useDeleteNotification>);

      render(<NotificationPage />);
      fireEvent.click(screen.getByTestId(`delete-btn-${NOTIF_A}`));
      expect(deleteFn).toHaveBeenCalledWith(NOTIF_A);
    });

    it("disables delete button when delete is pending", () => {
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A })], deletePending: true });
      render(<NotificationPage />);
      const btn = screen.getByTestId(`delete-btn-${NOTIF_A}`) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });
  });

  // Mark read interaction
  describe("mark single read", () => {
    it("calls mark-read mutation when button clicked", () => {
      const markFn = vi.fn();
      setupMocks({ notifications: [makeNotification({ id: NOTIF_A, is_read: false })] });
      mockUseMarkNotificationRead.mockReturnValue({
        mutate: markFn,
        isPending: false,
      } as unknown as ReturnType<typeof useMarkNotificationRead>);

      render(<NotificationPage />);
      fireEvent.click(screen.getByTestId(`mark-read-btn-${NOTIF_A}`));
      expect(markFn).toHaveBeenCalledWith(NOTIF_A);
    });

    it("disables mark-read button when pending", () => {
      setupMocks({
        notifications: [makeNotification({ id: NOTIF_A, is_read: false })],
        markReadPending: true,
      });
      render(<NotificationPage />);
      const btn = screen.getByTestId(`mark-read-btn-${NOTIF_A}`) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });
  });

  // Mark all read
  describe("mark all read", () => {
    it("renders mark-all-read button", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("mark-all-read-btn")).not.toBeNull();
    });

    it("mark-all-read button is disabled when no unread", () => {
      setupMocks({ unreadCount: 0 });
      render(<NotificationPage />);
      const btn = screen.getByTestId("mark-all-read-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    it("mark-all-read button is enabled when there are unread", () => {
      setupMocks({ unreadCount: 3 });
      render(<NotificationPage />);
      const btn = screen.getByTestId("mark-all-read-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });

    it("calls mark-all-read when button clicked", () => {
      const markAllFn = vi.fn();
      setupMocks({ unreadCount: 2 });
      mockUseMarkAllRead.mockReturnValue({
        mutate: markAllFn,
        isPending: false,
      } as unknown as ReturnType<typeof useMarkAllRead>);

      render(<NotificationPage />);
      fireEvent.click(screen.getByTestId("mark-all-read-btn"));
      expect(markAllFn).toHaveBeenCalledOnce();
    });

    it("shows unread count badge when unread > 0", () => {
      setupMocks({ unreadCount: 5 });
      render(<NotificationPage />);
      expect(screen.getByTestId("page-unread-count")).not.toBeNull();
    });

    it("does not show unread count badge when 0", () => {
      setupMocks({ unreadCount: 0 });
      render(<NotificationPage />);
      expect(screen.queryByTestId("page-unread-count")).toBeNull();
    });
  });

  // Filters
  describe("filters", () => {
    it("renders filter bar", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-filters")).not.toBeNull();
    });

    it("renders is-read filter", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("filter-is-read")).not.toBeNull();
    });

    it("renders priority filter", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("filter-priority")).not.toBeNull();
    });

    it("renders entity-type filter", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.getByTestId("filter-entity-type")).not.toBeNull();
    });

    it("does not show clear button initially", () => {
      setupMocks();
      render(<NotificationPage />);
      expect(screen.queryByTestId("clear-filters-btn")).toBeNull();
    });

    it("shows clear button after setting is-read filter", () => {
      setupMocks();
      render(<NotificationPage />);
      fireEvent.change(screen.getByTestId("filter-is-read"), {
        target: { value: "false" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });

    it("shows clear button after setting priority filter", () => {
      setupMocks();
      render(<NotificationPage />);
      fireEvent.change(screen.getByTestId("filter-priority"), {
        target: { value: "urgent" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });

    it("shows clear button after typing in entity-type filter", () => {
      setupMocks();
      render(<NotificationPage />);
      fireEvent.change(screen.getByTestId("filter-entity-type"), {
        target: { value: "task" },
      });
      expect(screen.getByTestId("clear-filters-btn")).not.toBeNull();
    });

    it("clears all filters when clear button clicked", () => {
      setupMocks();
      render(<NotificationPage />);
      fireEvent.change(screen.getByTestId("filter-priority"), {
        target: { value: "high" },
      });
      fireEvent.click(screen.getByTestId("clear-filters-btn"));
      expect(screen.queryByTestId("clear-filters-btn")).toBeNull();
    });
  });

  // Section grouping
  describe("section grouping", () => {
    it("shows section-unread for unread notifications", () => {
      setupMocks({ notifications: [makeNotification({ is_read: false })] });
      render(<NotificationPage />);
      expect(screen.getByTestId("section-unread")).not.toBeNull();
    });

    it("does not show section-unread when all read", () => {
      setupMocks({ notifications: [makeNotification({ is_read: true, created_at: OLD_ISO })] });
      render(<NotificationPage />);
      expect(screen.queryByTestId("section-unread")).toBeNull();
    });

    it("shows section-today for read notifications from today", () => {
      setupMocks({
        notifications: [makeNotification({ is_read: true, created_at: TODAY_ISO })],
      });
      render(<NotificationPage />);
      expect(screen.getByTestId("section-today")).not.toBeNull();
    });

    it("shows section-earlier for read notifications from past days", () => {
      setupMocks({
        notifications: [makeNotification({ is_read: true, created_at: OLD_ISO })],
      });
      render(<NotificationPage />);
      expect(screen.getByTestId("section-earlier")).not.toBeNull();
    });

    it("does not show section-earlier when only today's items", () => {
      setupMocks({
        notifications: [makeNotification({ is_read: true, created_at: TODAY_ISO })],
      });
      render(<NotificationPage />);
      expect(screen.queryByTestId("section-earlier")).toBeNull();
    });
  });

  // Priority badges on page
  describe("priority badges", () => {
    it.each(["low", "medium", "high", "urgent"] as const)("renders %s priority badge", (p) => {
      setupMocks({ notifications: [makeNotification({ priority: p })] });
      render(<NotificationPage />);
      expect(screen.getByTestId(`priority-badge-${p}`)).not.toBeNull();
    });
  });

  // Pagination
  describe("pagination", () => {
    it("shows next button when has_more is true", () => {
      setupMocks({
        notifications: [makeNotification()],
        hasMore: true,
        nextCursor: "cursor_tok",
      });
      render(<NotificationPage />);
      expect(screen.getByTestId("notification-list-next-btn")).not.toBeNull();
    });

    it("does not show next button when has_more is false", () => {
      setupMocks({ notifications: [makeNotification()], hasMore: false });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list-next-btn")).toBeNull();
    });

    it("does not show prev button on first page", () => {
      setupMocks({ notifications: [makeNotification()] });
      render(<NotificationPage />);
      expect(screen.queryByTestId("notification-list-prev-btn")).toBeNull();
    });

    it("shows prev button after navigating next", () => {
      setupMocks({
        notifications: [makeNotification()],
        hasMore: true,
        nextCursor: "cursor_1",
      });
      render(<NotificationPage />);
      fireEvent.click(screen.getByTestId("notification-list-next-btn"));
      // After clicking next, we navigate forward; prev should appear
      expect(screen.getByTestId("notification-list-prev-btn")).not.toBeNull();
    });
  });
});
