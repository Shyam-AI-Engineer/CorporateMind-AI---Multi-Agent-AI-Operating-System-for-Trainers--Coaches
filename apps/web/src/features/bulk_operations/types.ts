// Bulk Operations types — Sprint 59.

export type EntityType =
  | "customers"
  | "training_engagements"
  | "business_tasks"
  | "workflow_templates";

export type OperationType =
  | "csv_import"
  | "csv_validate"
  | "bulk_archive"
  | "bulk_status_update"
  | "bulk_assignment"
  | "dry_run";

export type OperationStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface RowValidationError {
  row: number;
  field: string;
  message: string;
}

export interface ValidationRowResult {
  row: number;
  valid: boolean;
  data: Record<string, unknown>;
  errors: RowValidationError[];
}

export interface CsvValidationOut {
  entity_type: EntityType;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  dry_run: boolean;
  results: ValidationRowResult[];
}

export interface BulkOperationOut {
  id: string;
  workspace_id: string;
  operation_type: OperationType;
  entity_type: EntityType;
  status: OperationStatus;
  requested_by: string;
  total_records: number;
  processed_records: number;
  successful_records: number;
  failed_records: number;
  started_at: string;
  completed_at: string | null;
  error_summary: string | null;
  created_at: string;
}

export interface BulkOperationListOut {
  operations: BulkOperationOut[];
  total: number;
}

// ── Request payloads ────────────────────────────────────────────────────────

export interface CsvValidatePayload {
  workspace_id: string;
  entity_type: EntityType;
  rows: Record<string, unknown>[];
  dry_run?: boolean;
}

export interface CsvImportPayload {
  workspace_id: string;
  entity_type: EntityType;
  rows: Record<string, unknown>[];
  requested_by: string;
  stop_on_error?: boolean;
}

export interface BulkArchivePayload {
  workspace_id: string;
  entity_type: EntityType;
  entity_ids: string[];
  requested_by: string;
}

export interface BulkAssignPayload {
  workspace_id: string;
  entity_type: EntityType;
  entity_ids: string[];
  assignee_id: string;
  requested_by: string;
}

export interface BulkStatusUpdatePayload {
  workspace_id: string;
  entity_type: EntityType;
  entity_ids: string[];
  new_status: string;
  requested_by: string;
}

// ── Display labels ──────────────────────────────────────────────────────────

export const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  customers: "Customers",
  training_engagements: "Training Engagements",
  business_tasks: "Business Tasks",
  workflow_templates: "Workflow Templates",
};

export const OPERATION_TYPE_LABELS: Record<OperationType, string> = {
  csv_import: "CSV Import",
  csv_validate: "CSV Validation",
  bulk_archive: "Bulk Archive",
  bulk_status_update: "Bulk Status Update",
  bulk_assignment: "Bulk Assignment",
  dry_run: "Dry Run",
};

export const OPERATION_STATUS_LABELS: Record<OperationStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const SUPPORTED_ENTITY_TYPES: EntityType[] = [
  "customers",
  "training_engagements",
  "business_tasks",
  "workflow_templates",
];
