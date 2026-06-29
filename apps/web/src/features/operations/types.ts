// Operations module types — Sprint 29 Business Operations Center
// Mirrors corpmind.modules.operations.schemas

export type TaskPriority = "high" | "medium" | "low";
export type TaskStatus = "backlog" | "in_progress" | "blocked" | "completed";
export type TaskSourceType = "manual" | "crm" | "campaign" | "proposal" | "recommendation";

export interface BusinessTaskOut {
  id: string;
  workspace_id: string;
  source_type: TaskSourceType | null;
  source_id: string | null;
  title: string;
  description: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  assignee: string | null;
  due_date: string | null;   // ISO date "YYYY-MM-DD"
  completed_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GroupedTasksOut {
  backlog: BusinessTaskOut[];
  in_progress: BusinessTaskOut[];
  blocked: BusinessTaskOut[];
  completed: BusinessTaskOut[];
  total: number;
}

export interface WorkloadOut {
  total_open: number;
  overdue: number;
  completed_today: number;
  blocked: number;
  by_priority: Record<string, number>;
  by_assignee: Record<string, number>;
}

export interface BusinessTaskIn {
  workspace_id: string;
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  source_type?: TaskSourceType | null;
  source_id?: string | null;
  assignee?: string | null;
  due_date?: string | null;
}

export interface BusinessTaskUpdate {
  status?: TaskStatus | null;
  assignee?: string | null;
  due_date?: string | null;
}
