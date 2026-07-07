export type AuditSeverity = "info" | "warning" | "critical";

export const AUDIT_SEVERITIES: AuditSeverity[] = ["info", "warning", "critical"];

export interface AuditLog {
  id: string;
  workspace_id: string;
  user_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  action: string;
  module: string;
  severity: AuditSeverity;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogFilters {
  workspace_id: string;
  module?: string;
  severity?: AuditSeverity;
  user_id?: string;
  entity_type?: string;
  entity_id?: string;
  action?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}

export interface AuditLogListOut {
  items: AuditLog[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface AuditStatisticsOut {
  total_events: number;
  by_severity: Record<string, number>;
  by_module: Record<string, number>;
  by_action: Record<string, number>;
  period_days: number;
}
