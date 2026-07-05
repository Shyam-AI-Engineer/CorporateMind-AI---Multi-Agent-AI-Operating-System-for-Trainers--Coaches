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

// ── Training Session types ─────────────────────────────────────────────────────

export type SessionStatus =
  | "planned"
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled";

export const SESSION_STATUSES: SessionStatus[] = [
  "planned",
  "scheduled",
  "in_progress",
  "completed",
  "cancelled",
];

export interface TrainingSession {
  id: string;
  tenant_id: string;
  workspace_id: string;
  engagement_id: string;
  session_name: string;
  session_number: number | null;
  status: SessionStatus;
  scheduled_start: string | null;
  scheduled_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  trainer_id: string | null;
  location: string | null;
  meeting_link: string | null;
  capacity: number | null;
  expected_attendees: number | null;
  actual_attendees: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingSessionListOut {
  items: TrainingSession[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface TrainingSessionCreate {
  workspace_id: string;
  engagement_id: string;
  session_name: string;
  session_number?: number;
  status?: SessionStatus;
  scheduled_start?: string;
  scheduled_end?: string;
  trainer_id?: string;
  location?: string;
  meeting_link?: string;
  capacity?: number;
  expected_attendees?: number;
  notes?: string;
}

export interface TrainingSessionUpdate {
  session_name?: string;
  session_number?: number;
  scheduled_start?: string;
  scheduled_end?: string;
  location?: string;
  meeting_link?: string;
  capacity?: number;
  expected_attendees?: number;
  notes?: string;
}

export interface CompleteSession {
  actual_end?: string;
  actual_attendees?: number;
  notes?: string;
}

export interface CancelSession {
  notes?: string;
}

export interface SessionTrainerAssign {
  trainer_id: string;
}

export interface TrainingSessionFilters {
  workspace_id: string;
  engagement_id?: string;
  trainer_id?: string;
  status?: SessionStatus;
  date_from?: string;
  date_to?: string;
  cursor?: string;
  limit?: number;
}

// ── Attendance types ───────────────────────────────────────────────────────────

export type AttendanceStatus =
  | "registered"
  | "present"
  | "late"
  | "absent"
  | "left_early";

export const ATTENDANCE_STATUSES: AttendanceStatus[] = [
  "registered",
  "present",
  "late",
  "absent",
  "left_early",
];

export interface TrainingAttendance {
  id: string;
  tenant_id: string;
  workspace_id: string;
  session_id: string;
  participant_name: string;
  participant_email: string | null;
  participant_phone: string | null;
  company: string | null;
  designation: string | null;
  attendance_status: AttendanceStatus;
  check_in_time: string | null;
  check_out_time: string | null;
  completion_percent: number | null;
  certificate_eligible: boolean;
  remarks: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingAttendanceListOut {
  items: TrainingAttendance[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface TrainingAttendanceCreate {
  workspace_id: string;
  session_id: string;
  participant_name: string;
  participant_email?: string;
  participant_phone?: string;
  company?: string;
  designation?: string;
  attendance_status?: AttendanceStatus;
  check_in_time?: string;
  completion_percent?: number;
  certificate_eligible?: boolean;
  remarks?: string;
}

export interface TrainingAttendanceUpdate {
  participant_name?: string;
  participant_email?: string;
  participant_phone?: string;
  company?: string;
  designation?: string;
  check_in_time?: string;
  check_out_time?: string;
  completion_percent?: number;
  certificate_eligible?: boolean;
  remarks?: string;
}

export interface CheckOutAttendance {
  check_out_time?: string;
  completion_percent?: number;
  certificate_eligible?: boolean;
}

export interface TrainingAttendanceFilters {
  workspace_id: string;
  session_id?: string;
  attendance_status?: AttendanceStatus;
  company?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}

// ── Certificate types ──────────────────────────────────────────────────────────

export type CertificateStatus = "draft" | "issued" | "revoked";

export const CERTIFICATE_STATUSES: CertificateStatus[] = [
  "draft",
  "issued",
  "revoked",
];

export interface TrainingCertificate {
  id: string;
  tenant_id: string;
  workspace_id: string;
  attendance_id: string;
  session_id: string;
  certificate_number: string | null;
  participant_name: string;
  participant_email: string | null;
  certificate_title: string | null;
  issue_date: string | null;
  issued_by: string | null;
  status: CertificateStatus;
  download_count: number;
  verification_code: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrainingCertificateListOut {
  items: TrainingCertificate[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface TrainingCertificateCreate {
  workspace_id: string;
  attendance_id: string;
  session_id: string;
  certificate_title?: string;
  notes?: string;
}

export interface TrainingCertificateUpdate {
  participant_name?: string;
  participant_email?: string;
  certificate_title?: string;
  certificate_number?: string;
  issued_by?: string;
  notes?: string;
}

export interface IssueCertificate {
  issue_date?: string;
  issued_by?: string;
  certificate_number?: string;
  certificate_title?: string;
}

export interface RevokeCertificate {
  notes?: string;
}

export interface TrainingCertificateFilters {
  workspace_id: string;
  session_id?: string;
  status?: CertificateStatus;
  issued_by?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}
