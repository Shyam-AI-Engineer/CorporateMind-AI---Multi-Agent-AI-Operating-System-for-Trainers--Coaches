export interface SocialPost {
  id: string;
  workspace_id: string;
  channel: string;
  content: string;
  hashtags: string[];
  status: string; // draft | scheduled | published | failed
  scheduled_at: string | null;
  published_at: string | null;
  created_at: string;
}

export interface SocialPostListOut {
  items: SocialPost[];
  total: number;
  limit: number;
  offset: number;
}

export interface SocialPostCreate {
  workspace_id: string;
  channel: string;
  content: string;
  hashtags?: string[];
  scheduled_at?: string;
}

export type SocialChannel = "instagram" | "facebook" | "telegram" | "linkedin";

export const SOCIAL_CHANNELS: SocialChannel[] = [
  "instagram",
  "facebook",
  "telegram",
  "linkedin",
];

export const SOCIAL_CHANNEL_CONFIG: Record<
  SocialChannel,
  { label: string; emoji: string }
> = {
  instagram: { label: "Instagram", emoji: "📸" },
  facebook:  { label: "Facebook",  emoji: "📘" },
  telegram:  { label: "Telegram",  emoji: "✈️" },
  linkedin:  { label: "LinkedIn",  emoji: "💼" },
};

export const POST_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  draft:     { label: "Draft",     variant: "secondary"   },
  scheduled: { label: "Scheduled", variant: "warning"     },
  published: { label: "Published", variant: "success"     },
  failed:    { label: "Failed",    variant: "destructive" },
};
