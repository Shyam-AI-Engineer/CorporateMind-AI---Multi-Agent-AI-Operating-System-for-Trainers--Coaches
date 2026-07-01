export type WorkflowCategory =
  | "new_corporate_lead"
  | "proposal_review"
  | "enterprise_sales"
  | "training_delivery"
  | "customer_followup"
  | "renewal_process"
  | "onboarding"
  | "other";

export type OwnerRole = "owner" | "admin" | "member" | "viewer";

export interface WorkflowStepOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  workflow_template_id: string;
  step_order: number;
  title: string;
  description: string | null;
  owner_role: OwnerRole;
  estimated_hours: string; // Decimal serialized as string
  required: boolean;
  created_at: string;
}

export interface WorkflowTemplateOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  category: WorkflowCategory;
  is_active: boolean;
  created_by: string;
  created_at: string;
  steps: WorkflowStepOut[];
}

export interface WorkflowTemplateListPage {
  items: WorkflowTemplateOut[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface WorkflowTemplateIn {
  workspace_id: string;
  name: string;
  description?: string | null;
  category: WorkflowCategory;
  is_active?: boolean;
}

export interface WorkflowTemplateUpdate {
  name?: string;
  description?: string | null;
  category?: WorkflowCategory;
  is_active?: boolean;
}

export interface WorkflowStepIn {
  title: string;
  description?: string | null;
  owner_role?: OwnerRole;
  estimated_hours?: string;
  required?: boolean;
}

export interface WorkflowStepUpdate {
  title?: string;
  description?: string | null;
  owner_role?: OwnerRole;
  estimated_hours?: string;
  required?: boolean;
}

export interface ReorderStepsIn {
  step_ids: string[];
}

// ── Execution Engine types — Sprint 34 ───────────────────────────────────────

export type RunStatus = "pending" | "active" | "completed" | "cancelled";
export type StepRunStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "skipped"
  | "blocked";

export interface WorkflowRunStepOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  workflow_run_id: string;
  template_step_id: string | null;
  title: string;
  description: string | null;
  owner_role: OwnerRole;
  required: boolean;
  step_order: number;
  status: StepRunStatus;
  completed_by: string | null;
  completed_at: string | null;
  notes: string | null;
}

export type EntityType =
  | "lead"
  | "proposal"
  | "campaign"
  | "customer"
  | "training"
  | "other";

export interface WorkflowRunOut {
  id: string;
  tenant_id: string;
  workspace_id: string;
  workflow_template_id: string | null;
  title: string;
  status: RunStatus;
  started_by: string;
  assigned_to: string | null;
  started_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  // Sprint 35: entity context (nullable)
  entity_type: EntityType | null;
  entity_id: string | null;
  entity_title: string | null;
  run_steps: WorkflowRunStepOut[];
}

export interface WorkflowRunListPage {
  items: WorkflowRunOut[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface WorkflowRunIn {
  workspace_id: string;
  workflow_template_id: string;
  title: string;
  assigned_to?: string | null;
}

export interface CompleteStepIn {
  notes?: string | null;
}

export interface BlockStepIn {
  notes?: string | null;
}

export interface SkipStepIn {
  notes?: string | null;
}

// ── Entity integration types — Sprint 35 ─────────────────────────────────────

export interface AttachEntityIn {
  entity_type: EntityType;
  entity_id: string;
  entity_title: string;
}

export interface EntityRunListPage {
  items: WorkflowRunOut[];
  next_cursor: string | null;
  has_more: boolean;
}

// ── Workflow Analytics types — Sprint 36 ─────────────────────────────────────

export interface AnalyticsSummaryOut {
  total_runs: number;
  active_runs: number;
  completed_runs: number;
  cancelled_runs: number;
  completion_rate: number;
  average_completion_days: number;
  average_step_completion_days: number;
  average_required_steps: number;
  average_optional_steps: number;
  data_integrity_warning: boolean;
}

export interface TemplateAnalyticsItem {
  template_id: string | null;
  template_name: string;
  runs: number;
  completed: number;
  cancelled: number;
  completion_rate: number;
  average_completion_days: number;
  average_steps: number;
  average_required_steps: number;
  average_optional_steps: number;
}

export interface TemplateAnalyticsOut {
  items: TemplateAnalyticsItem[];
}

export interface BottleneckItem {
  step_name: string;
  template_name: string;
  times_executed: number;
  average_days: number;
  completion_rate: number;
  blocked_count: number;
  skip_count: number;
}

export interface BottleneckAnalyticsOut {
  items: BottleneckItem[];
}

export interface TrendBucket {
  date: string;
  runs_started: number;
  runs_completed: number;
  runs_cancelled: number;
  completion_rate: number;
}

export interface TrendAnalyticsOut {
  period: number;
  buckets: TrendBucket[];
}

export interface WorkloadItem {
  owner: string;
  pending_steps: number;
  completed_steps: number;
  blocked_steps: number;
  completion_rate: number;
  average_completion_days: number;
}

export interface WorkloadAnalyticsOut {
  items: WorkloadItem[];
}

// ── Workflow SLA types — Sprint 37 ────────────────────────────────────────────

export interface SLASummaryOut {
  active_runs: number;
  overdue_runs: number;
  sla_compliance_rate: number;
  average_days_open: number;
  average_days_overdue: number;
  critical_overdue: number;
  warning_overdue: number;
  healthy_runs: number;
  data_integrity_warning: boolean;
}

export interface SLAOverdueItem {
  run_id: string;
  title: string;
  template_name: string | null;
  entity_type: string | null;
  entity_title: string | null;
  started_at: string;
  days_open: number;
  days_overdue: number;
  current_step: string | null;
  owner_role: string | null;
}

export interface SLAOverdueOut {
  items: SLAOverdueItem[];
}

export interface SLATemplateItem {
  template_id: string | null;
  template_name: string;
  runs: number;
  overdue: number;
  compliance_rate: number;
  average_duration_days: number;
  average_days_overdue: number;
}

export interface SLATemplateOut {
  items: SLATemplateItem[];
}

export interface SLAOwnerItem {
  owner_role: string;
  assigned_steps: number;
  completed_steps: number;
  overdue_steps: number;
  compliance_rate: number;
  average_completion_days: number;
}

export interface SLAOwnerOut {
  items: SLAOwnerItem[];
}

export interface SLATrendBucket {
  date: string;
  healthy: number;
  warning: number;
  critical: number;
  completed: number;
}

export interface SLATrendOut {
  period: number;
  buckets: SLATrendBucket[];
}

// ── Workflow Effectiveness types — Sprint 38 ──────────────────────────────────

export interface EffectivenessSummaryOut {
  total_completed: number;
  average_completion_days: number;
  average_step_completion_days: number;
  entity_coverage: number;
  fast_completion_rate: number;
  slow_completion_rate: number;
  overall_effectiveness_score: number;
  data_integrity_warning: boolean;
}

export interface EffectivenessTemplateItem {
  template_id: string | null;
  template_name: string;
  runs: number;
  completed: number;
  completion_rate: number;
  average_duration: number;
  effectiveness_score: number;
}

export interface EffectivenessTemplateOut {
  items: EffectivenessTemplateItem[];
}

export interface EffectivenessEntityItem {
  entity_type: string;
  workflow_count: number;
  completion_rate: number;
  average_duration: number;
  effectiveness_score: number;
}

export interface EffectivenessEntityOut {
  items: EffectivenessEntityItem[];
}

export interface DurationBucketItem {
  label: string;
  completed: number;
  completion_rate: number;
  average_steps: number;
  effectiveness_score: number;
}

export interface DurationImpactOut {
  buckets: DurationBucketItem[];
}

export interface CompletionImpactItem {
  status: string;
  count: number;
  average_duration: number;
  effectiveness_score: number;
}

export interface CompletionImpactOut {
  items: CompletionImpactItem[];
}

// ── Workflow Observability types — Sprint 39 ──────────────────────────────────

export interface BottleneckObsItem {
  template_name: string;
  slowest_step: string;
  average_days: number;
  max_days: number;
  runs_affected: number;
  bottleneck_score: number;
}

export interface BottleneckObsOut {
  items: BottleneckObsItem[];
}

export interface StepAnalysisItem {
  step_name: string;
  completed_count: number;
  average_completion_days: number;
  median_completion_days: number;
  blocked_count: number;
  skip_rate: number;
  completion_rate: number;
}

export interface StepAnalysisOut {
  items: StepAnalysisItem[];
}

export interface OwnerCapacityItem {
  owner_role: string;
  assigned_steps: number;
  completed_steps: number;
  blocked_steps: number;
  average_completion_days: number;
  capacity_score: number;
}

export interface OwnerCapacityOut {
  items: OwnerCapacityItem[];
}

export interface TemplateCapacityItem {
  template_name: string;
  active_runs: number;
  completed_runs: number;
  average_parallel_runs: number;
  average_completion_days: number;
  capacity_rating: string;
}

export interface TemplateCapacityOut {
  items: TemplateCapacityItem[];
}

export interface FlowHealthOut {
  healthy_flows: number;
  warning_flows: number;
  critical_flows: number;
  average_step_completion_days: number;
  average_run_completion_days: number;
  flow_health_score: number;
  data_integrity_warning: boolean;
}
