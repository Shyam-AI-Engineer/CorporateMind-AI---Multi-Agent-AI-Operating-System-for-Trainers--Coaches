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
  useUnreadCount: vi.fn(),
  useNotifications: vi.fn(),
  useMarkAllRead: vi.fn(),
  useMarkNotificationRead: vi.fn(),
  useDeleteNotification: vi.fn(),
  useCreateNotification: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/"),
  useParams: vi.fn(() => ({})),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useUnreadCount,
  useNotifications,
  useMarkAllRead,
} from "@/features/notifications/api/use-notifications";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseUnreadCount = vi.mocked(useUnreadCount);
const mockUseNotifications = vi.mocked(useNotifications);
const mockUseMarkAllRead = vi.mocked(useMarkAllRead);

const { NotificationBell } = await import("./notification-bell");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-bell-1";
const NOTIF_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const NOTIF_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

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
    created_at: "2026-06-28T10:00:00Z",
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
  unreadCount = 0,
  countLoading = false,
  notifications = [] as NotificationOut[],
  listLoading = false,
  listError = false,
  markAllPending = false,
}: {
  workspaceId?: string | null;
  unreadCount?: number;
  countLoading?: boolean;
  notifications?: NotificationOut[];
  listLoading?: boolean;
  listError?: boolean;
  markAllPending?: boolean;
} = {}) {
  mockUseWorkspace.mockReturnValue({
    workspaceId: workspaceId ?? null,
    orgId: "org-1",
  } as ReturnType<typeof useWorkspace>);
  mockUseUnreadCount.mockReturnValue({
    data: makeCount(unreadCount),
    isLoading: countLoading,
    isError: false,
  } as ReturnType<typeof useUnreadCount>);
  mockUseNotifications.mockReturnValue({
    data: makeListPage({ items: notifications }),
    isLoading: listLoading,
    isError: listError,
  } as ReturnType<typeof useNotifications>);
  mockUseMarkAllRead.mockReturnValue({
    mutate: vi.fn(),
    isPending: markAllPending,
  } as unknown as ReturnType<typeof useMarkAllRead>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("NotificationBell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Workspace guard
  describe("workspace guard", () => {
    it("renders nothing when workspaceId is null", () => {
      setupMocks({ workspaceId: null });
      const { container } = render(<NotificationBell />);
      expect(container.firstChild).toBeNull();
    });

    it("renders bell when workspaceId is set", () => {
      setupMocks();
      render(<NotificationBell />);
      expect(screen.getByTestId("notification-bell")).not.toBeNull();
    });
  });

  // Bell button
  describe("bell button", () => {
    it("renders bell button", () => {
      setupMocks();
      render(<NotificationBell />);
      expect(screen.getByTestId("notification-bell")).not.toBeNull();
    });

    it("renders wrapper", () => {
      setupMocks();
      render(<NotificationBell />);
      expect(screen.getByTestId("notification-bell-wrapper")).not.toBeNull();
    });

    it("does not show badge when unread count is 0", () => {
      setupMocks({ unreadCount: 0 });
      render(<NotificationBell />);
      expect(screen.queryByTestId("unread-badge")).toBeNull();
    });

    it("shows badge when unread count > 0", () => {
      setupMocks({ unreadCount: 3 });
      render(<NotificationBell />);
      expect(screen.getByTestId("unread-badge")).not.toBeNull();
    });

    it("shows badge with count number", () => {
      setupMocks({ unreadCount: 5 });
      render(<NotificationBell />);
      const badge = screen.getByTestId("unread-badge");
      expect(badge.textContent).toBe("5");
    });

    it("shows 99+ when count exceeds 99", () => {
      setupMocks({ unreadCount: 100 });
      render(<NotificationBell />);
      const badge = screen.getByTestId("unread-badge");
      expect(badge.textContent).toBe("99+");
    });

    it("does not show badge while count is loading", () => {
      setupMocks({ unreadCount: 5, countLoading: true });
      render(<NotificationBell />);
      expect(screen.queryByTestId("unread-badge")).toBeNull();
    });
  });

  // Dropdown
  describe("dropdown", () => {
    it("dropdown is not visible on mount", () => {
      setupMocks();
      render(<NotificationBell />);
      expect(screen.queryByTestId("notification-dropdown")).toBeNull();
    });

    it("dropdown opens when bell is clicked", () => {
      setupMocks();
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("notification-dropdown")).not.toBeNull();
    });

    it("dropdown closes when bell is clicked again", () => {
      setupMocks();
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.queryByTestId("notification-dropdown")).toBeNull();
    });

    it("shows view-all link in dropdown", () => {
      setupMocks();
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("view-all-link")).not.toBeNull();
    });

    it("view-all link points to /notifications", () => {
      setupMocks();
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      const link = screen.getByTestId("view-all-link");
      expect(link.getAttribute("href")).toBe("/notifications");
    });

    it("shows mark-all-read button in dropdown", () => {
      setupMocks();
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("mark-all-read-bell-btn")).not.toBeNull();
    });

    it("mark-all-read button is disabled when no unread", () => {
      setupMocks({ unreadCount: 0 });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      const btn = screen.getByTestId("mark-all-read-bell-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    it("mark-all-read button is enabled when unread > 0", () => {
      setupMocks({ unreadCount: 2 });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      const btn = screen.getByTestId("mark-all-read-bell-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
  });

  // Loading state in dropdown
  describe("dropdown loading state", () => {
    it("shows skeleton when list is loading", () => {
      setupMocks({ listLoading: true });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("notification-dropdown-skeleton")).not.toBeNull();
    });

    it("does not show error while loading", () => {
      setupMocks({ listLoading: true });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.queryByTestId("notification-dropdown-error")).toBeNull();
    });
  });

  // Error state in dropdown
  describe("dropdown error state", () => {
    it("shows error when list fetch fails", () => {
      setupMocks({ listError: true, listLoading: false });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("notification-dropdown-error")).not.toBeNull();
    });
  });

  // Empty state in dropdown
  describe("dropdown empty state", () => {
    it("shows empty message when no notifications", () => {
      setupMocks({ notifications: [] });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("notification-dropdown-empty")).not.toBeNull();
    });
  });

  // Notification preview items
  describe("notification preview items", () => {
    it("renders preview item for each notification", () => {
      const items = [
        makeNotification({ id: NOTIF_A }),
        makeNotification({ id: NOTIF_B }),
      ];
      setupMocks({ notifications: items });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId(`notification-preview-item-${NOTIF_A}`)).not.toBeNull();
      expect(screen.getByTestId(`notification-preview-item-${NOTIF_B}`)).not.toBeNull();
    });

    it("renders notification title in preview", () => {
      const items = [makeNotification({ id: NOTIF_A, title: "Test title" })];
      setupMocks({ notifications: items });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId(`notification-preview-title-${NOTIF_A}`).textContent).toBe("Test title");
    });

    it("renders priority badge in preview", () => {
      const items = [makeNotification({ priority: "urgent" })];
      setupMocks({ notifications: items });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId("notification-priority-badge-urgent")).not.toBeNull();
    });

    it("renders unread dot for unread notifications", () => {
      const items = [makeNotification({ id: NOTIF_A, is_read: false })];
      setupMocks({ notifications: items });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId(`notification-unread-dot-${NOTIF_A}`)).not.toBeNull();
    });

    it("does not render unread dot for read notifications", () => {
      const items = [makeNotification({ id: NOTIF_A, is_read: true })];
      setupMocks({ notifications: items });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.queryByTestId(`notification-unread-dot-${NOTIF_A}`)).toBeNull();
    });
  });

  // Priority badges
  describe("priority badges", () => {
    it.each(["low", "medium", "high", "urgent"] as const)("renders %s priority badge", (p) => {
      setupMocks({ notifications: [makeNotification({ priority: p })] });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      expect(screen.getByTestId(`notification-priority-badge-${p}`)).not.toBeNull();
    });
  });

  // Mark all read interaction
  describe("mark all read", () => {
    it("calls mark all read when button clicked", () => {
      const mutateFn = vi.fn();
      setupMocks({ unreadCount: 3 });
      mockUseMarkAllRead.mockReturnValue({
        mutate: mutateFn,
        isPending: false,
      } as unknown as ReturnType<typeof useMarkAllRead>);

      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      fireEvent.click(screen.getByTestId("mark-all-read-bell-btn"));
      expect(mutateFn).toHaveBeenCalledOnce();
    });

    it("disables mark-all-read when pending", () => {
      setupMocks({ unreadCount: 3, markAllPending: true });
      render(<NotificationBell />);
      fireEvent.click(screen.getByTestId("notification-bell"));
      const btn = screen.getByTestId("mark-all-read-bell-btn") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });
  });
});
