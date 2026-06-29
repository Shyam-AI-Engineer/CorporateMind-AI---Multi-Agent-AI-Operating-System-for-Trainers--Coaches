/**
 * Inbox feature types — mirrors the backend Pydantic DTOs.
 *
 * Keep this file in sync with apps/api/src/corpmind/modules/inbox/schemas.py.
 * The seven reply intents are duplicated as a TypeScript literal union so the
 * IntentBadge component can exhaustively pattern-match without `string` casts.
 */

export interface InboxConnection {
  id: string;
  workspace_id: string;
  provider: string;
  email_address: string;
  scopes: string;
  token_expiry_at: string | null;
  status: string;
  last_sync_at: string | null;
  last_error: string | null;
  connected_by: string;
  created_at: string;
  updated_at: string;
}

export interface InboxConnectionListOut {
  items: InboxConnection[];
  total: number;
  limit: number;
  offset: number;
}

export interface ConnectionHealth {
  healthy: boolean;
  reason: string | null;
  status: string;
}

export interface InboxMessage {
  id: string;
  connection_id: string;
  provider_message_id: string;
  provider_thread_id: string | null;
  smtp_message_id: string | null;
  in_reply_to: string | null;
  outbound_message_id: string | null;
  match_method: string | null;
  from_address: string;
  subject: string | null;
  received_at: string;
  body_snippet: string | null;
  body_truncated: boolean;
  reply_intent: ReplyIntent | null;
  confidence: number | null;
  classified_at: string | null;
  classification_model: string | null;
  synced_at: string;
}

export interface InboxMessageListOut {
  items: InboxMessage[];
  total: number;
  limit: number;
  offset: number;
}

// Canonical reply-intent vocabulary — mirrors the Python Literal in
// agents/reply_classifier.py.  Any drift here will surface as a TS error
// in IntentBadge's exhaustive switch.
export const REPLY_INTENTS = [
  "interested",
  "not_interested",
  "question",
  "out_of_office",
  "bounce",
  "auto_reply",
  "unsubscribe",
  "unknown",
] as const;

export type ReplyIntent = (typeof REPLY_INTENTS)[number];

// Configuration for the IntentBadge component.  Reuses the BadgeVariant
// vocabulary already defined by `@/components/ui/badge`.
export const INTENT_CONFIG: Record<
  ReplyIntent,
  { label: string; variant: "success" | "warning" | "destructive" | "secondary" | "outline" }
> = {
  interested:     { label: "Interested",      variant: "success" },
  not_interested: { label: "Not interested",  variant: "destructive" },
  question:       { label: "Question",        variant: "warning" },
  out_of_office:  { label: "Out of office",   variant: "secondary" },
  bounce:         { label: "Bounce",          variant: "destructive" },
  auto_reply:     { label: "Auto-reply",      variant: "secondary" },
  unsubscribe:    { label: "Unsubscribe",     variant: "destructive" },
  unknown:        { label: "Unknown",         variant: "outline" },
};

// Connection status vocabulary (mirrors inbox/models.py:status).
export const CONNECTION_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "success" | "warning" | "destructive" | "outline" }
> = {
  active:        { label: "Active",        variant: "success" },
  needs_reauth:  { label: "Needs reauth",  variant: "warning" },
  revoked:       { label: "Revoked",       variant: "destructive" },
  error:         { label: "Error",         variant: "destructive" },
};
