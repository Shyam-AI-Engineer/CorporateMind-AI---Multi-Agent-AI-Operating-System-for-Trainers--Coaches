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
