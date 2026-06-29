import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { WorkspaceMemberOut, ActivityFeedEntryOut, ActivityFeedPage, CommentOut } from "@/features/team/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("@/features/team/api/use-team", () => ({
  useTeamMembers: vi.fn(),
  useActivityFeed: vi.fn(),
  useTaskComments: vi.fn(),
  useInviteMember: vi.fn(),
  useAcceptInvitation: vi.fn(),
  useChangeMemberRole: vi.fn(),
  useRemoveMember: vi.fn(),
  useCreateComment: vi.fn(),
  useDeleteComment: vi.fn(),
  useAssignTask: vi.fn(),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useTeamMembers,
  useActivityFeed,
  useInviteMember,
  useChangeMemberRole,
  useRemoveMember,
} from "@/features/team/api/use-team";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseTeamMembers = vi.mocked(useTeamMembers);
const mockUseActivityFeed = vi.mocked(useActivityFeed);
const mockUseInviteMember = vi.mocked(useInviteMember);
const mockUseChangeMemberRole = vi.mocked(useChangeMemberRole);
const mockUseRemoveMember = vi.mocked(useRemoveMember);

const { TeamPage } = await import("./team-page");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-test-1";
const ORG_ID = "org-test-1";
const USER_A = "user-aaaa-aaaa";
const USER_B = "user-bbbb-bbbb";
const MEMBER_A_ID = "mem-1111-1111";
const MEMBER_B_ID = "mem-2222-2222";

function makeMember(overrides: Partial<WorkspaceMemberOut> = {}): WorkspaceMemberOut {
  return {
    id: MEMBER_A_ID,
    workspace_id: WS_ID,
    user_id: USER_A,
    role: "member",
    invited_by: USER_A,
    invited_at: "2026-06-01T10:00:00Z",
    accepted_at: "2026-06-01T10:05:00Z",
    removed_at: null,
    ...overrides,
  };
}

function makeActivity(overrides: Partial<ActivityFeedEntryOut> = {}): ActivityFeedEntryOut {
  return {
    id: "feed-aaaa-aaaa",
    workspace_id: WS_ID,
    actor_user_id: USER_A,
    entity_type: "task",
    entity_id: "task-xxxx",
    action: "task.created",
    feed_metadata: null,
    created_at: "2026-06-20T09:00:00Z",
    ...overrides,
  };
}

function makeActivityPage(overrides: Partial<ActivityFeedPage> = {}): ActivityFeedPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function setupMocks({
  workspaceId = WS_ID,
  members = [] as WorkspaceMemberOut[],
  membersLoading = false,
  membersError = false,
  activityPage = makeActivityPage(),
  activityLoading = false,
  activityError = false,
}: {
  workspaceId?: string | null;
  members?: WorkspaceMemberOut[];
  membersLoading?: boolean;
  membersError?: boolean;
  activityPage?: ActivityFeedPage;
  activityLoading?: boolean;
  activityError?: boolean;
} = {}) {
  mockUseWorkspace.mockReturnValue({ workspaceId } as ReturnType<typeof useWorkspace>);
  mockUseTeamMembers.mockReturnValue({
    data: membersLoading || membersError ? undefined : { items: members, total: members.length },
    isLoading: membersLoading,
    isError: membersError,
  } as ReturnType<typeof useTeamMembers>);
  mockUseActivityFeed.mockReturnValue({
    data: activityLoading || activityError ? undefined : activityPage,
    isLoading: activityLoading,
    isError: activityError,
  } as ReturnType<typeof useActivityFeed>);
  mockUseInviteMember.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useInviteMember>);
  mockUseChangeMemberRole.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useChangeMemberRole>);
  mockUseRemoveMember.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveMember>);
}

// ── TeamPage — top-level ───────────────────────────────────────────────────────

describe("TeamPage — workspace guard", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows no-workspace message when workspaceId is null", () => {
    setupMocks({ workspaceId: null });
    render(<TeamPage />);
    expect(screen.getByTestId("team-no-workspace")).not.toBeNull();
  });

  it("shows no-workspace message when workspaceId is undefined", () => {
    mockUseWorkspace.mockReturnValue({ workspaceId: undefined } as unknown as ReturnType<typeof useWorkspace>);
    render(<TeamPage />);
    expect(screen.getByTestId("team-no-workspace")).not.toBeNull();
  });

  it("renders team-page when workspaceId is set", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByTestId("team-page")).not.toBeNull();
  });

  it("renders team tabs container", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByTestId("team-tabs")).not.toBeNull();
  });

  it("renders Members and Activity tab triggers", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByTestId("tab-members")).not.toBeNull();
    expect(screen.getByTestId("tab-activity")).not.toBeNull();
  });

  it("Members tab is active by default", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    // MembersTab content is visible without clicking
    expect(screen.getByTestId("members-tab")).not.toBeNull();
  });
});

// ── MembersTab — loading ───────────────────────────────────────────────────────

describe("MembersTab — loading state", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows skeleton while loading", () => {
    setupMocks({ membersLoading: true });
    render(<TeamPage />);
    expect(screen.getByTestId("members-skeleton")).not.toBeNull();
  });

  it("does not show members-tab while loading", () => {
    setupMocks({ membersLoading: true });
    render(<TeamPage />);
    expect(screen.queryByTestId("members-tab")).toBeNull();
  });
});

// ── MembersTab — error ────────────────────────────────────────────────────────

describe("MembersTab — error state", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows error element when query fails", () => {
    setupMocks({ membersError: true });
    render(<TeamPage />);
    expect(screen.getByTestId("members-error")).not.toBeNull();
  });

  it("error text mentions failed to load", () => {
    setupMocks({ membersError: true });
    render(<TeamPage />);
    expect(screen.getByText(/failed to load team members/i)).not.toBeNull();
  });
});

// ── MembersTab — empty ────────────────────────────────────────────────────────

describe("MembersTab — empty state", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows empty message when no members", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByTestId("members-empty")).not.toBeNull();
  });

  it("shows invite button when empty", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByTestId("invite-btn")).not.toBeNull();
  });

  it("does not render table when empty", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.queryByTestId("members-table-container")).toBeNull();
  });

  it("shows 0 member count", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.getByText("0 member(s)")).not.toBeNull();
  });
});

// ── MembersTab — data ─────────────────────────────────────────────────────────

describe("MembersTab — data state", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders member row for each member", () => {
    const members = [
      makeMember({ id: MEMBER_A_ID, user_id: USER_A }),
      makeMember({ id: MEMBER_B_ID, user_id: USER_B }),
    ];
    setupMocks({ members });
    render(<TeamPage />);
    expect(screen.getByTestId(`member-row-${MEMBER_A_ID}`)).not.toBeNull();
    expect(screen.getByTestId(`member-row-${MEMBER_B_ID}`)).not.toBeNull();
  });

  it("renders table container when members exist", () => {
    setupMocks({ members: [makeMember()] });
    render(<TeamPage />);
    expect(screen.getByTestId("members-table-container")).not.toBeNull();
  });

  it("shows active status for accepted member", () => {
    const member = makeMember({ accepted_at: "2026-06-01T10:05:00Z" });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    expect(screen.getByTestId(`member-status-active-${MEMBER_A_ID}`)).not.toBeNull();
  });

  it("shows pending status for unaccepted member", () => {
    const member = makeMember({ id: MEMBER_B_ID, accepted_at: null });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    expect(screen.getByTestId(`member-status-pending-${MEMBER_B_ID}`)).not.toBeNull();
  });

  it("renders user_id in each row", () => {
    setupMocks({ members: [makeMember({ user_id: "user-readable-id" })] });
    render(<TeamPage />);
    expect(screen.getByText("user-readable-id")).not.toBeNull();
  });

  it("renders remove button for each member", () => {
    const members = [makeMember({ id: MEMBER_A_ID }), makeMember({ id: MEMBER_B_ID })];
    setupMocks({ members });
    render(<TeamPage />);
    expect(screen.getByTestId(`remove-btn-${MEMBER_A_ID}`)).not.toBeNull();
    expect(screen.getByTestId(`remove-btn-${MEMBER_B_ID}`)).not.toBeNull();
  });

  it("renders role selector for each member", () => {
    setupMocks({ members: [makeMember({ id: MEMBER_A_ID })] });
    render(<TeamPage />);
    expect(screen.getByTestId(`role-select-${MEMBER_A_ID}`)).not.toBeNull();
  });

  it("shows correct member count", () => {
    const members = [makeMember({ id: MEMBER_A_ID }), makeMember({ id: MEMBER_B_ID })];
    setupMocks({ members });
    render(<TeamPage />);
    expect(screen.getByText("2 member(s)")).not.toBeNull();
  });
});

// ── RoleBadge ─────────────────────────────────────────────────────────────────

describe("RoleBadge", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders owner badge", () => {
    setupMocks({ members: [makeMember({ role: "owner" })] });
    render(<TeamPage />);
    expect(screen.getByTestId("role-badge-owner")).not.toBeNull();
  });

  it("renders admin badge", () => {
    setupMocks({ members: [makeMember({ role: "admin" })] });
    render(<TeamPage />);
    expect(screen.getByTestId("role-badge-admin")).not.toBeNull();
  });

  it("renders member badge", () => {
    setupMocks({ members: [makeMember({ role: "member" })] });
    render(<TeamPage />);
    expect(screen.getByTestId("role-badge-member")).not.toBeNull();
  });

  it("renders viewer badge", () => {
    setupMocks({ members: [makeMember({ role: "viewer" })] });
    render(<TeamPage />);
    expect(screen.getByTestId("role-badge-viewer")).not.toBeNull();
  });

  it("owner badge has purple color class", () => {
    setupMocks({ members: [makeMember({ role: "owner" })] });
    render(<TeamPage />);
    const badge = screen.getByTestId("role-badge-owner");
    expect(badge.className).toContain("purple");
  });

  it("viewer badge has slate color class", () => {
    setupMocks({ members: [makeMember({ role: "viewer" })] });
    render(<TeamPage />);
    const badge = screen.getByTestId("role-badge-viewer");
    expect(badge.className).toContain("slate");
  });
});

// ── InviteDialog ──────────────────────────────────────────────────────────────

describe("InviteDialog", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("opens invite dialog when invite button clicked", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.getByTestId("invite-dialog")).not.toBeNull();
  });

  it("renders invite form inside dialog", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.getByTestId("invite-form")).not.toBeNull();
  });

  it("renders user ID input", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.getByTestId("invite-user-id-input")).not.toBeNull();
  });

  it("renders role select dropdown", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.getByTestId("invite-role-select")).not.toBeNull();
  });

  it("renders submit button", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.getByTestId("invite-submit")).not.toBeNull();
  });

  it("submit button disabled when user ID is empty", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    const submitBtn = screen.getByTestId("invite-submit") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it("submit button enabled after typing user ID", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    await user.type(screen.getByTestId("invite-user-id-input"), "some-user-uuid");
    const submitBtn = screen.getByTestId("invite-submit") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);
  });

  it("calls invite.mutate with correct data on submit", async () => {
    const mutateFn = vi.fn();
    setupMocks({ members: [] });
    mockUseInviteMember.mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useInviteMember>);

    const user = userEvent.setup();
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    await user.type(screen.getByTestId("invite-user-id-input"), "target-user-id");
    await user.selectOptions(screen.getByTestId("invite-role-select"), "admin");
    fireEvent.submit(screen.getByTestId("invite-form"));

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({ user_id: "target-user-id", role: "admin" }),
      expect.any(Object),
    );
  });

  it("does not show invite error initially", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    expect(screen.queryByTestId("invite-error")).toBeNull();
  });

  it("shows error when mutate calls onError", async () => {
    let onErrorCallback: ((err: unknown) => void) | undefined;
    const mutateFn = vi.fn().mockImplementation((_data, opts) => {
      onErrorCallback = opts?.onError;
    });
    setupMocks({ members: [] });
    mockUseInviteMember.mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useInviteMember>);

    const user = userEvent.setup();
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    await user.type(screen.getByTestId("invite-user-id-input"), "some-user");
    fireEvent.submit(screen.getByTestId("invite-form"));

    act(() => {
      onErrorCallback!(new Error("Already a member"));
    });
    expect(screen.getByTestId("invite-error")).not.toBeNull();
    expect(screen.getByText("Already a member")).not.toBeNull();
  });

  it("role select defaults to member", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [] });
    render(<TeamPage />);
    await user.click(screen.getByTestId("invite-btn"));
    const select = screen.getByTestId("invite-role-select") as HTMLSelectElement;
    expect(select.value).toBe("member");
  });

  it("invite dialog is not shown by default", () => {
    setupMocks({ members: [] });
    render(<TeamPage />);
    expect(screen.queryByTestId("invite-dialog")).toBeNull();
  });
});

// ── RemoveDialog ──────────────────────────────────────────────────────────────

describe("RemoveDialog", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("opens remove dialog when remove button clicked", async () => {
    const user = userEvent.setup();
    const member = makeMember({ id: MEMBER_A_ID, user_id: USER_A });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    await user.click(screen.getByTestId(`remove-btn-${MEMBER_A_ID}`));
    expect(screen.getByTestId("remove-dialog")).not.toBeNull();
  });

  it("shows correct user ID in remove dialog", async () => {
    const user = userEvent.setup();
    const member = makeMember({ id: MEMBER_A_ID, user_id: "specific-user-id" });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    await user.click(screen.getByTestId(`remove-btn-${MEMBER_A_ID}`));
    expect(screen.getByTestId("remove-dialog-user-id").textContent).toBe("specific-user-id");
  });

  it("renders confirm remove button", async () => {
    const user = userEvent.setup();
    const member = makeMember({ id: MEMBER_A_ID });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    await user.click(screen.getByTestId(`remove-btn-${MEMBER_A_ID}`));
    expect(screen.getByTestId("remove-confirm-btn")).not.toBeNull();
  });

  it("calls remove.mutate on confirm", async () => {
    const mutateFn = vi.fn();
    setupMocks({ members: [makeMember({ id: MEMBER_A_ID })] });
    mockUseRemoveMember.mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveMember>);

    const user = userEvent.setup();
    render(<TeamPage />);
    await user.click(screen.getByTestId(`remove-btn-${MEMBER_A_ID}`));
    await user.click(screen.getByTestId("remove-confirm-btn"));

    expect(mutateFn).toHaveBeenCalledWith(MEMBER_A_ID, expect.any(Object));
  });

  it("remove dialog not shown by default", () => {
    setupMocks({ members: [makeMember()] });
    render(<TeamPage />);
    expect(screen.queryByTestId("remove-dialog")).toBeNull();
  });
});

// ── RoleSelector ──────────────────────────────────────────────────────────────

describe("RoleSelector", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders selector with current role selected", () => {
    const member = makeMember({ id: MEMBER_A_ID, role: "admin" });
    setupMocks({ members: [member] });
    render(<TeamPage />);
    const select = screen.getByTestId(`role-select-${MEMBER_A_ID}`) as HTMLSelectElement;
    expect(select.value).toBe("admin");
  });

  it("calls changeRole.mutate when option changes", async () => {
    const mutateFn = vi.fn();
    const member = makeMember({ id: MEMBER_A_ID, role: "viewer" });
    setupMocks({ members: [member] });
    mockUseChangeMemberRole.mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useChangeMemberRole>);

    const user = userEvent.setup();
    render(<TeamPage />);
    await user.selectOptions(screen.getByTestId(`role-select-${MEMBER_A_ID}`), "member");

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({ memberId: MEMBER_A_ID, data: { role: "member" } }),
    );
  });

  it("disabled while change pending", () => {
    const member = makeMember({ id: MEMBER_A_ID });
    setupMocks({ members: [member] });
    mockUseChangeMemberRole.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
    } as unknown as ReturnType<typeof useChangeMemberRole>);
    render(<TeamPage />);

    const select = screen.getByTestId(`role-select-${MEMBER_A_ID}`) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });
});

// ── ActivityTab ───────────────────────────────────────────────────────────────

describe("ActivityTab — navigation and loading", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("switches to activity tab on click", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityPage: makeActivityPage() });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-tab")).not.toBeNull();
  });

  it("shows skeleton while loading activity", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityLoading: true });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-skeleton")).not.toBeNull();
  });

  it("shows error when activity feed fails", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityError: true });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-error")).not.toBeNull();
  });

  it("shows empty state when no activity", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityPage: makeActivityPage({ items: [] }) });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-empty")).not.toBeNull();
  });

  it("renders activity items when present", async () => {
    const user = userEvent.setup();
    const items = [
      makeActivity({ id: "entry-1" }),
      makeActivity({ id: "entry-2" }),
      makeActivity({ id: "entry-3" }),
    ];
    setupMocks({ members: [], activityPage: makeActivityPage({ items }) });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-item-0")).not.toBeNull();
    expect(screen.getByTestId("activity-item-1")).not.toBeNull();
    expect(screen.getByTestId("activity-item-2")).not.toBeNull();
  });

  it("does not show next button when has_more is false", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityPage: makeActivityPage({ has_more: false }) });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.queryByTestId("activity-next-btn")).toBeNull();
  });

  it("shows next button when has_more is true", async () => {
    const user = userEvent.setup();
    setupMocks({
      members: [],
      activityPage: makeActivityPage({
        items: [makeActivity()],
        has_more: true,
        next_cursor: "cursor-abc",
      }),
    });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByTestId("activity-next-btn")).not.toBeNull();
  });

  it("does not show prev button on first page (no cursor)", async () => {
    const user = userEvent.setup();
    setupMocks({ members: [], activityPage: makeActivityPage({ has_more: false }) });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.queryByTestId("activity-prev-btn")).toBeNull();
  });
});

// ── ActivityTab — action labels ────────────────────────────────────────────────

describe("ActivityTab — action labels", () => {
  const actions: [string, RegExp][] = [
    ["task.created", /created a task/i],
    ["task.assigned", /assigned a task/i],
    ["task.completed", /completed a task/i],
    ["task.commented", /commented on a task/i],
    ["member.invited", /invited a member/i],
    ["member.accepted", /accepted invitation/i],
    ["member.removed", /removed a member/i],
    ["member.role_changed", /changed a member's role/i],
    ["proposal.accepted", /accepted a proposal/i],
    ["campaign.launched", /launched a campaign/i],
  ];

  actions.forEach(([action, expectedLabel]) => {
    it(`renders correct label for ${action}`, async () => {
      const user = userEvent.setup();
      setupMocks({
        members: [],
        activityPage: makeActivityPage({
          items: [makeActivity({ action })],
          has_more: false,
        }),
      });
      render(<TeamPage />);
      await user.click(screen.getByTestId("tab-activity"));
      expect(screen.getByText(expectedLabel)).not.toBeNull();
    });
  });

  it("renders raw action string for unknown action", async () => {
    const user = userEvent.setup();
    setupMocks({
      members: [],
      activityPage: makeActivityPage({
        items: [makeActivity({ action: "custom.unknown.action" })],
      }),
    });
    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    expect(screen.getByText("custom.unknown.action")).not.toBeNull();
  });
});

// ── Cursor pagination ─────────────────────────────────────────────────────────

describe("Cursor pagination", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("clicking 'Load older' passes cursor to useActivityFeed", async () => {
    const user = userEvent.setup();
    // First render: has_more with a cursor
    mockUseWorkspace.mockReturnValue({ workspaceId: WS_ID } as ReturnType<typeof useWorkspace>);
    mockUseTeamMembers.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useTeamMembers>);
    mockUseActivityFeed.mockReturnValue({
      data: makeActivityPage({
        items: [makeActivity()],
        has_more: true,
        next_cursor: "cursor-page-2",
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useActivityFeed>);
    mockUseInviteMember.mockReturnValue({ mutate: vi.fn(), isPending: false } as unknown as ReturnType<typeof useInviteMember>);
    mockUseChangeMemberRole.mockReturnValue({ mutate: vi.fn(), isPending: false } as unknown as ReturnType<typeof useChangeMemberRole>);
    mockUseRemoveMember.mockReturnValue({ mutate: vi.fn(), isPending: false } as unknown as ReturnType<typeof useRemoveMember>);

    render(<TeamPage />);
    await user.click(screen.getByTestId("tab-activity"));
    await user.click(screen.getByTestId("activity-next-btn"));

    // After clicking, useActivityFeed should be called with "cursor-page-2"
    expect(mockUseActivityFeed).toHaveBeenCalledWith(WS_ID, "cursor-page-2");
  });
});
