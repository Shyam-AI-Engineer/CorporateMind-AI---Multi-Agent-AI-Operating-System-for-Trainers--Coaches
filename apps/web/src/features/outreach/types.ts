export type OutreachChannel = "email" | "whatsapp" | "telegram";

export interface GenerateOutreachRequest {
  contact_id: string;
  channel: OutreachChannel;
  campaign_id?: string;
  ab_variant?: string;
}

export interface OutboundMessage {
  id: string;
  contact_id: string;
  campaign_id: string | null;
  channel: string;
  subject: string | null;
  body: string;
  prompt_version: string | null;
  ab_variant: string | null;
  status: string;
  provider_message_id: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface OutboundMessageListOut {
  items: OutboundMessage[];
  total: number;
  limit: number;
  offset: number;
}

export interface SendMessageResponse {
  message_id: string;
  status: "queued" | "blocked";
  compliance_reason: string | null;
}

export const OUTREACH_CHANNELS: OutreachChannel[] = ["email", "whatsapp", "telegram"];

// Only channels with a live backend adapter. Others show as disabled in UI.
export const LIVE_OUTREACH_CHANNELS = new Set<OutreachChannel>(["email"]);

export const CHANNEL_LABELS: Record<OutreachChannel, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
};

export const CHANNEL_EMOJI: Record<OutreachChannel, string> = {
  email: "✉️",
  whatsapp: "💬",
  telegram: "📨",
};

export const MESSAGE_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  draft:   { label: "Draft",   variant: "secondary" },
  queued:  { label: "Queued",  variant: "default" },
  sent:    { label: "Sent",    variant: "default" },
  blocked: { label: "Blocked", variant: "destructive" },
  failed:  { label: "Failed",  variant: "destructive" },
};
