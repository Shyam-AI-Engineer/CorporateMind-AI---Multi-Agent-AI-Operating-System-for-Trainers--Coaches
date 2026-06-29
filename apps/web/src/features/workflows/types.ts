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
