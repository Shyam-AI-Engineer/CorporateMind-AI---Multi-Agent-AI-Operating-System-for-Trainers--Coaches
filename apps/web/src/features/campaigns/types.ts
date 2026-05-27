export interface Campaign {
  id: string;
  workspace_id: string;
  name: string;
  channel: string;
  status: string; // draft | locked | running | paused | completed | cancelled
  recipient_count: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CampaignListOut {
  items: Campaign[];
  total: number;
  limit: number;
  offset: number;
}
