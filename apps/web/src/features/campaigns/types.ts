export interface Campaign {
  id: string;
  workspace_id: string;
  name: string;
  channel: string;
  status: string; // draft | locked | running | paused | completed | cancelled | pending_hitl
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

export interface CampaignCreate {
  name: string;
  channel: string;
  settings?: Record<string, unknown>;
  scheduled_at?: string;
}

export interface CampaignLaunchResponse {
  campaign_id: string;
  status: string; // running | pending_hitl
  recipient_count: number;
  hitl_required: boolean;
}

export interface AddRecipientsResponse {
  added_count: number;
  total_recipients: number;
}

export interface CampaignRecipient {
  id: string;
  contact_id: string;
  status: string; // pending | sent | failed | bounced
  message_id: string | null;
  sent_at: string | null;
  error_code: string | null;
}

// Status display config
export const STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  draft:        { label: "Draft",        variant: "secondary"  },
  locked:       { label: "Locked",       variant: "warning"    },
  running:      { label: "Running",      variant: "success"    },
  paused:       { label: "Paused",       variant: "outline"    },
  completed:    { label: "Completed",    variant: "secondary"  },
  cancelled:    { label: "Cancelled",    variant: "destructive"},
  pending_hitl: { label: "Pending Review", variant: "warning"  },
};

export const CHANNEL_CONFIG: Record<string, { label: string; emoji: string }> = {
  email:     { label: "Email",     emoji: "✉️" },
  whatsapp:  { label: "WhatsApp",  emoji: "💬" },
  telegram:  { label: "Telegram",  emoji: "✈️" },
  instagram: { label: "Instagram", emoji: "📸" },
  facebook:  { label: "Facebook",  emoji: "📘" },
  linkedin:  { label: "LinkedIn",  emoji: "💼" },
};

export const SUPPORTED_CHANNELS = Object.keys(CHANNEL_CONFIG);
