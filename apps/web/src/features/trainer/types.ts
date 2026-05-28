export interface TrainerProfile {
  id: string;
  workspace_id: string;
  niche: string | null;
  topics: string[];
  tone: string | null;
  pricing_min_inr: number | null;
  pricing_max_inr: number | null;
  bio: string | null;
  usp: string | null;
  target_industries: string[];
  languages: string[];
  is_locked: boolean;
  created_at: string;
}

export interface ExtractFromTextRequest {
  content: string; // 20–20,000 chars
}

export interface TrainerProfileUpdate {
  niche?: string | null;
  tone?: string | null;
  usp?: string | null;
  pricing_min_inr?: number | null;
  pricing_max_inr?: number | null;
}
