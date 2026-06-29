// Notification Center types — Sprint 32

export type NotificationPriority = "low" | "medium" | "high" | "urgent";

export type NotificationType =
  | "approval_assigned"
  | "approval_completed"
  | "task_assigned"
  | "task_completed"
  | "recommendation_created"
  | "recommendation_accepted"
  | "recommendation_completed"
  | "campaign_launched"
  | "proposal_accepted"
  | "team_invited"
  | "comment_added";

export interface NotificationOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  user_id: string;
  notification_type: NotificationType;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  priority: NotificationPriority;
  is_read: boolean;
  read_at: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationListPage {
  items: NotificationOut[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface NotificationIn {
  workspace_id: string;
  user_id: string;
  notification_type: NotificationType;
  title: string;
  message: string;
  entity_type?: string | null;
  entity_id?: string | null;
  priority?: NotificationPriority;
  metadata?: Record<string, unknown> | null;
}

export interface UnreadCountOut {
  count: number;
}
