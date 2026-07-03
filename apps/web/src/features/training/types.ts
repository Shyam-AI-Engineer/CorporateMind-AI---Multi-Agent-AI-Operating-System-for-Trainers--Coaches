export interface TrainingEngagement {
  id: string;
  tenant_id: string;
  workspace_id: string;
  customer_id: string;
  program_name: string;
  description: string | null;
  training_type: string;
  delivery_mode: DeliveryMode;
  status: TrainingStatus;
  priority: TrainingPriority;
  planned_start_date: string | null;
  planned_end_date: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  estimated_participants: number | null;
  actual_participants: number | null;
  assigned_trainer_id: string | null;
  coordinator_id: string | null;
  location: string | null;
  meeting_link: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type TrainingStatus =
  | "planned"
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled";

export type DeliveryMode = "onsite" | "online" | "hybrid";

export type TrainingPriority = "low" | "medium" | "high" | "urgent";

export interface TrainingEngagementListOut {
  items: TrainingEngagement[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface TrainingEngagementCreate {
  workspace_id: string;
  customer_id: string;
  program_name: string;
  description?: string;
  training_type: string;
  delivery_mode: DeliveryMode;
  status?: TrainingStatus;
  priority?: TrainingPriority;
  planned_start_date?: string;
  planned_end_date?: string;
  estimated_participants?: number;
  assigned_trainer_id?: string;
  coordinator_id?: string;
  location?: string;
  meeting_link?: string;
  notes?: string;
}

export interface TrainingEngagementUpdate {
  program_name?: string;
  description?: string;
  training_type?: string;
  delivery_mode?: DeliveryMode;
  priority?: TrainingPriority;
  planned_start_date?: string;
  planned_end_date?: string;
  estimated_participants?: number;
  location?: string;
  meeting_link?: string;
  notes?: string;
}

export interface TrainerAssign {
  assigned_trainer_id: string;
}

export interface CoordinatorAssign {
  coordinator_id: string;
}

export interface CompleteEngagement {
  actual_end_date?: string;
  actual_participants?: number;
  notes?: string;
}

export interface CancelEngagement {
  notes?: string;
}

export interface TrainingEngagementFilters {
  workspace_id: string;
  status?: TrainingStatus;
  trainer_id?: string;
  customer_id?: string;
  delivery_mode?: DeliveryMode;
  date_from?: string;
  date_to?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}

export const TRAINING_STATUSES: TrainingStatus[] = [
  "planned",
  "scheduled",
  "in_progress",
  "completed",
  "cancelled",
];

export const DELIVERY_MODES: DeliveryMode[] = ["onsite", "online", "hybrid"];

export const TRAINING_PRIORITIES: TrainingPriority[] = [
  "low",
  "medium",
  "high",
  "urgent",
];
