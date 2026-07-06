export type HealthStatus = "healthy" | "watch" | "at_risk";
export type RiskLevel = "low" | "medium" | "high";

export interface CustomerSuccess {
  id: string;
  tenant_id: string;
  workspace_id: string;
  customer_id: string;
  health_status: HealthStatus;
  health_score: number | null;
  risk_level: RiskLevel;
  owner_user_id: string | null;
  renewal_date: string | null;
  last_contact_date: string | null;
  next_followup_date: string | null;
  expansion_opportunity: boolean;
  renewal_probability: number | null;
  notes: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerSuccessListOut {
  items: CustomerSuccess[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface CustomerSuccessCreate {
  workspace_id: string;
  customer_id: string;
  health_status?: HealthStatus;
  health_score?: number;
  risk_level?: RiskLevel;
  owner_user_id?: string;
  renewal_date?: string;
  last_contact_date?: string;
  next_followup_date?: string;
  expansion_opportunity?: boolean;
  renewal_probability?: number;
  notes?: string;
}

export interface CustomerSuccessUpdate {
  health_status?: HealthStatus;
  health_score?: number;
  risk_level?: RiskLevel;
  renewal_date?: string;
  last_contact_date?: string;
  next_followup_date?: string;
  expansion_opportunity?: boolean;
  renewal_probability?: number;
  notes?: string;
}

export interface AssignOwner {
  owner_user_id: string;
}

export interface UpdateHealth {
  health_status: HealthStatus;
  health_score?: number;
}

export interface ScheduleFollowup {
  next_followup_date: string;
}

export interface CustomerSuccessFilters {
  workspace_id: string;
  health_status?: HealthStatus;
  risk_level?: RiskLevel;
  owner_user_id?: string;
  renewal_date_from?: string;
  renewal_date_to?: string;
  followup_due_by?: string;
  expansion_opportunity?: boolean;
  search?: string;
  include_archived?: boolean;
  cursor?: string;
  limit?: number;
}

export const HEALTH_STATUSES: HealthStatus[] = ["healthy", "watch", "at_risk"];
export const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];
