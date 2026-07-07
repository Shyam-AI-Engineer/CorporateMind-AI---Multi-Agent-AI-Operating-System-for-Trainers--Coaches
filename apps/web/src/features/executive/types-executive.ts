// Executive Dashboard TypeScript types — Sprint 50

export interface ExecutiveSummary {
  total_leads: number;
  active_customers: number;
  renewals_due: number;
  open_operations_tasks: number;
  business_health_score: number;
}

export interface ExecutiveKPIs {
  total_leads: number;
  active_customers: number;
  renewals_due: number;
  training_completion_rate: number;
  certificate_issuance_rate: number;
  avg_feedback_rating: number | null;
  customer_health_distribution: Record<string, number>;
  workflow_completion_rate: number;
  open_operations_tasks: number;
  business_health_score: number;
}

export type AlertSeverity = "critical" | "warning" | "info";

export type AlertType =
  | "renewals_overdue"
  | "customers_at_risk"
  | "training_overdue"
  | "workflow_backlog"
  | "operations_backlog"
  | "low_feedback_scores"
  | "health_score_drops";

export interface ExecutiveAlert {
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  count: number;
  affected_ids: string[];
}

export interface ExecutiveTrend {
  date: string;
  leads_created: number;
  customers_created: number;
  training_completions: number;
  renewals_processed: number;
}

export interface ExecutiveDashboard {
  summary: ExecutiveSummary;
  kpis: ExecutiveKPIs;
  alerts: ExecutiveAlert[];
  trends_30d: ExecutiveTrend[];
  workspace_id: string;
  generated_at: string;
}

export type TrendPeriod = 30 | 90 | 365;
