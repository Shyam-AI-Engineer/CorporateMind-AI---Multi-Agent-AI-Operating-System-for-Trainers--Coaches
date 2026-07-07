export type TimelineEventType =
  | "customer_created"
  | "training_engagement_created"
  | "training_session_started"
  | "training_session_completed"
  | "attendance_recorded"
  | "certificate_issued"
  | "feedback_submitted"
  | "customer_health_updated"
  | "renewal_created"
  | "renewal_status_changed";

export const TIMELINE_EVENT_TYPES: TimelineEventType[] = [
  "customer_created",
  "training_engagement_created",
  "training_session_started",
  "training_session_completed",
  "attendance_recorded",
  "certificate_issued",
  "feedback_submitted",
  "customer_health_updated",
  "renewal_created",
  "renewal_status_changed",
];

export interface CustomerTimelineEvent {
  event_id: string;
  event_type: TimelineEventType;
  occurred_at: string;
  title: string;
  entity_type: string | null;
  entity_id: string | null;
  detail: Record<string, unknown>;
}

export interface CustomerTimelinePage {
  items: CustomerTimelineEvent[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface CustomerRelationshipSummary {
  customer_id: string;
  total_trainings: number;
  completed_trainings: number;
  total_certificates: number;
  avg_feedback_rating: number | null;
  current_health: string | null;
  renewal_status: string | null;
  latest_activity_at: string | null;
  days_since_last_interaction: number | null;
}

export interface Customer360 {
  customer_id: string;
  summary: CustomerRelationshipSummary;
  recent_events: CustomerTimelineEvent[];
}

export interface TimelineFilters {
  event_types?: TimelineEventType[];
  cursor?: string;
  limit?: number;
}
