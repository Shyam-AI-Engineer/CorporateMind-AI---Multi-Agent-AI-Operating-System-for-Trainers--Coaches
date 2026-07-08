// Integration Hub types — Sprint 55: API Keys and Webhooks

export const SUPPORTED_WEBHOOK_EVENTS = [
  "customer.created",
  "customer.updated",
  "customer.deleted",
  "invoice.created",
  "invoice.paid",
  "invoice.overdue",
  "invoice.cancelled",
  "payment.received",
  "payment.failed",
  "training.session.started",
  "training.session.completed",
  "training.certificate.issued",
  "renewal.upcoming",
  "renewal.completed",
  "workflow.started",
  "workflow.completed",
  "workflow.failed",
  "api_key.revoked",
] as const;

export type WebhookEvent = (typeof SUPPORTED_WEBHOOK_EVENTS)[number];

// ── API Key types ──────────────────────────────────────────────────────────

export interface ApiKey {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
}

/** Returned only at creation — contains the plaintext key. */
export interface ApiKeyCreated extends ApiKey {
  plain_key: string;
}

export interface ApiKeyListOut {
  items: ApiKey[];
  total: number;
}

export interface ApiKeyCreateRequest {
  workspace_id: string;
  name: string;
  expires_at?: string | null;
}

// ── Webhook types ──────────────────────────────────────────────────────────

export interface Webhook {
  id: string;
  tenant_id: string;
  workspace_id: string;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  created_by: string;
  created_at: string;
}

/** Returned only at creation — contains the signing secret. */
export interface WebhookCreated extends Webhook {
  secret: string;
}

export interface WebhookListOut {
  items: Webhook[];
  total: number;
}

export interface WebhookCreateRequest {
  workspace_id: string;
  name: string;
  url: string;
  events: string[];
}

export interface WebhookUpdateRequest {
  name?: string;
  url?: string;
  events?: string[];
  is_active?: boolean;
}
