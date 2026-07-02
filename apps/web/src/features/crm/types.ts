export interface PipelineStageCount {
  stage: string;
  count: number;
}

export interface PipelineStats {
  workspace_id: string;
  stages: PipelineStageCount[];
  total: number;
}

export interface Lead {
  id: string;
  workspace_id: string;
  contact_id: string;
  stage: string;
  score: number;
  notes: string | null;
  extra: Record<string, unknown>;
  meeting_scheduled_at: string | null;
  booked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadListOut {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

export interface StageAdvanceResponse {
  lead_id: string;
  from_stage: string;
  to_stage: string;
}

export interface LeadCreate {
  contact_id: string;
  workspace_id: string;
  score?: number;
  notes?: string;
}

// Canonical pipeline stage order (terminal stages excluded from forward flow)
export const PIPELINE_STAGES = [
  "discovered",
  "engaged",
  "meeting_scheduled",
  "meeting_completed",
  "booked",
  "lost",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export const TERMINAL_STAGES: ReadonlySet<string> = new Set(["booked", "lost"]);

// ── Activity timeline + follow-up queue (Sprint 5) ──────────────────────────

export interface Activity {
  id: string;
  workspace_id: string;
  lead_id: string | null;
  contact_id: string;
  type: string;
  summary: string;
  source_inbox_message_id: string | null;
  source_outbound_message_id: string | null;
  created_at: string;
}

export interface ActivityListOut {
  items: Activity[];
  total: number;
  limit: number;
  offset: number;
}

export interface FollowUpTask {
  id: string;
  workspace_id: string;
  lead_id: string | null;
  contact_id: string;
  type: string;
  status: string;
  scheduled_for: string | null;
  source_inbox_message_id: string;
  source_outbound_message_id: string | null;
  result_outbound_message_id: string | null;
  attempts: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowUpListOut {
  items: FollowUpTask[];
  total: number;
  limit: number;
  offset: number;
}

// ── Sprint 8C: follow-up HITL approval ──────────────────────────────────────

export interface FollowupDraftView {
  id: string;
  subject: string | null;
  body: string;
  status: string;
}

export interface FollowupReplyView {
  from_address: string | null;
  subject: string | null;
  snippet: string | null;
  received_at: string | null;
}

export interface FollowupReview {
  task: FollowUpTask;
  draft: FollowupDraftView | null;
  reply: FollowupReplyView | null;
  original_subject: string | null;
  lead_stage: string | null;
}

export interface FollowupApproveResponse {
  task_id: string;
  status: string; // "done" | "blocked"
  compliance_reason: string | null;
}

// Activity type vocabulary — mirrors crm/automation.py constants.
export const ACTIVITY_CONFIG: Record<
  string,
  { label: string; icon: "trending-up" | "trending-down" | "help-circle" | "clock" | "mail-x" | "mail" | "alert-triangle" }
> = {
  lead_engaged:             { label: "Lead engaged",        icon: "trending-up" },
  lead_cold:                { label: "Lead marked cold",    icon: "trending-down" },
  followup_required:        { label: "Follow-up required",  icon: "help-circle" },
  followup_scheduled:       { label: "Follow-up scheduled", icon: "clock" },
  contact_bounced:          { label: "Contact bounced",     icon: "mail-x" },
  auto_reply_logged:        { label: "Auto-reply received", icon: "mail" },
  unknown_intent_logged:    { label: "Reply received",      icon: "mail" },
  automation_failed:        { label: "Automation failed",   icon: "alert-triangle" },
  automation_skipped:       { label: "Automation skipped",  icon: "alert-triangle" },
  followup_approved:        { label: "Follow-up approved",  icon: "mail" },
  followup_rejected:        { label: "Follow-up rejected",  icon: "mail-x" },
  // Sprint 14 — booking webhook activities
  booking_confirmed:        { label: "Meeting auto-scheduled", icon: "trending-up" },
  meeting_rescheduled:      { label: "Meeting rescheduled",    icon: "clock" },
  // Sprint 17B — WhatsApp unsubscribe
  whatsapp_unsubscribed:    { label: "WA opt-out",             icon: "mail-x" },
};

export const FOLLOW_UP_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "warning" | "success" | "secondary" | "outline" }
> = {
  pending:           { label: "Pending",      variant: "warning" },
  awaiting_approval: { label: "Needs review", variant: "warning" },
  processing:        { label: "Processing",   variant: "outline" },
  done:              { label: "Done",         variant: "success" },
  cancelled:         { label: "Cancelled",    variant: "secondary" },
};


// ── Lead Pipeline Analytics — Sprint 40 ─────────────────────────────────────

export interface LeadPipelineSummaryOut {
  total_leads: number;
  active_leads: number;
  qualified_leads: number;
  proposal_leads: number;
  won_leads: number;
  lost_leads: number;
  overall_conversion_rate: number;
  pipeline_health_score: number;
  data_integrity_warning: boolean;
}

export interface StageAnalysisItem {
  stage: string;
  count: number;
  average_days: number;
  conversion_rate: number;
  drop_off_rate: number;
}

export interface StageAnalysisOut {
  items: StageAnalysisItem[];
}

export interface SourceAnalysisItem {
  source: string;
  lead_count: number;
  qualified: number;
  won: number;
  conversion_rate: number;
}

export interface SourceAnalysisOut {
  items: SourceAnalysisItem[];
}

export interface IndustryAnalysisItem {
  industry: string;
  lead_count: number;
  won: number;
  conversion_rate: number;
  average_pipeline_days: number;
}

export interface IndustryAnalysisOut {
  items: IndustryAnalysisItem[];
}

export interface LeadConversionOut {
  qualified_to_proposal: number;
  proposal_to_win: number;
  overall_win_rate: number;
  average_days_to_win: number;
}

export const STAGE_CONFIG: Record<
  string,
  { label: string; colorClass: string; bgClass: string; borderClass: string }
> = {
  discovered: {
    label: "Discovered",
    colorClass: "text-blue-700",
    bgClass: "bg-blue-50",
    borderClass: "border-blue-200",
  },
  engaged: {
    label: "Engaged",
    colorClass: "text-indigo-700",
    bgClass: "bg-indigo-50",
    borderClass: "border-indigo-200",
  },
  meeting_scheduled: {
    label: "Scheduled",
    colorClass: "text-violet-700",
    bgClass: "bg-violet-50",
    borderClass: "border-violet-200",
  },
  meeting_completed: {
    label: "Meeting Done",
    colorClass: "text-amber-700",
    bgClass: "bg-amber-50",
    borderClass: "border-amber-200",
  },
  booked: {
    label: "Booked",
    colorClass: "text-green-700",
    bgClass: "bg-green-50",
    borderClass: "border-green-200",
  },
  lost: {
    label: "Lost",
    colorClass: "text-red-600",
    bgClass: "bg-red-50",
    borderClass: "border-red-200",
  },
};
