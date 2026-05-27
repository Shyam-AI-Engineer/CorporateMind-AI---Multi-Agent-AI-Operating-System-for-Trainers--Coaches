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
