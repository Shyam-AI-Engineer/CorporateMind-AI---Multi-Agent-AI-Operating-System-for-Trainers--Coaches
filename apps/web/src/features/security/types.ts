// Security Center types — Sprint 58

export interface SecuritySummary {
  overall_security_score: number; // 0.0–1.0
  active_api_keys: number;
  expired_api_keys: number;
  active_workspace_members: number;
  organization_admins: number;
  audit_events_today: number;
  critical_audit_events: number;
  checked_at: string;
}

export interface RoleCount {
  role: string;
  count: number;
}

export interface RoleDistribution {
  roles: RoleCount[];
  total_members: number;
  checked_at: string;
}

export interface ApiKeyHealth {
  total_keys: number;
  active: number;
  expired: number;
  never_used: number;
  used_last_30_days: number;
  checked_at: string;
}

export interface ModuleAuditEntry {
  module: string;
  event_count: number;
}

export interface AuditSummary {
  events_today: number;
  critical_events: number;
  warning_events: number;
  top_modules: ModuleAuditEntry[];
  checked_at: string;
}

export interface WorkspacePermissionRow {
  workspace_id: string;
  owners: number;
  admins: number;
  members: number;
  viewers: number;
}

export interface PermissionOverview {
  workspaces: WorkspacePermissionRow[];
  total_workspaces: number;
  checked_at: string;
}

export interface SecurityAlert {
  alert_type: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  count: number;
}

export interface SecurityAlerts {
  alerts: SecurityAlert[];
  total: number;
  checked_at: string;
}

// ── Display constants ─────────────────────────────────────────────────────────

export const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
  viewer: "Viewer",
};

export const ALERT_SEVERITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const ALERT_TYPE_LABELS: Record<string, string> = {
  expired_api_keys: "Expired API Keys",
  unused_api_keys: "Unused API Keys",
  critical_audit_events: "Critical Audit Events",
  no_admin_user: "No Admin User",
  excessive_admins: "Excessive Admins",
  pending_invitations: "Pending Invitations",
};
