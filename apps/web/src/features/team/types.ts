// Team module types — Sprint 30

export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";

export interface WorkspaceMemberOut {
  id: string;
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  invited_by: string;
  invited_at: string;
  accepted_at: string | null;
  removed_at: string | null;
}

export interface MemberListOut {
  items: WorkspaceMemberOut[];
  total: number;
}

export interface MemberInviteIn {
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
}

export interface MemberAcceptIn {
  member_id: string;
  workspace_id: string;
}

export interface MemberRoleUpdate {
  role: WorkspaceRole;
}

export interface ActivityFeedEntryOut {
  id: string;
  workspace_id: string;
  actor_user_id: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  feed_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityFeedPage {
  items: ActivityFeedEntryOut[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommentOut {
  id: string;
  task_id: string;
  workspace_id: string;
  author_user_id: string;
  body: string;
  created_at: string;
}

export interface CommentIn {
  body: string;
}

export interface TaskAssignIn {
  workspace_id: string;
  assigned_user_id: string | null;
}
