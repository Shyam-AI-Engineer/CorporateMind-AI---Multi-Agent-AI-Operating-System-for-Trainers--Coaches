// Approval Workflow types — Sprint 31

export type ApprovalStatus =
  | "pending"
  | "in_review"
  | "approved"
  | "rejected"
  | "cancelled";

export type ApprovalDecision = "approve" | "reject" | "none";

export type ApprovalPriority = "low" | "medium" | "high" | "urgent";

export type ApprovalEntityType =
  | "task"
  | "recommendation"
  | "campaign"
  | "proposal";

export interface ApprovalRequestOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  entity_type: ApprovalEntityType;
  entity_id: string | null;
  requested_by: string;
  assigned_reviewer: string | null;
  priority: ApprovalPriority;
  status: ApprovalStatus;
  decision: ApprovalDecision;
  comments: string | null;
  due_date: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalListPage {
  items: ApprovalRequestOut[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ApprovalRequestIn {
  workspace_id: string;
  entity_type: ApprovalEntityType;
  entity_id?: string | null;
  assigned_reviewer?: string | null;
  priority?: ApprovalPriority;
  comments?: string | null;
  due_date?: string | null;
}

export interface ApprovalAssignIn {
  assigned_reviewer: string;
}

export interface ApprovalDecisionIn {
  comments?: string | null;
}

export interface ApprovalTimelineEventOut {
  id: string;
  approval_request_id: string;
  tenant_id: string;
  event_type: string;
  actor_user_id: string;
  notes: string | null;
  occurred_at: string;
}
