/**
 * Shared TypeScript types for CorporateMind AI.
 *
 * Auto-generated types from FastAPI OpenAPI spec:
 *   pnpm --filter @corpmind/shared-types generate
 *
 * Hand-authored types for things not in the OpenAPI spec:
 */

export type Channel = "email" | "whatsapp" | "telegram" | "instagram" | "facebook" | "linkedin";

export type PlanTier = "starter" | "growth" | "enterprise";

export type UserRole = "OrgAdmin" | "AgencyManager" | "Trainer" | "Reviewer" | "Analyst" | "PlatformAdmin";

export type CampaignStatus =
  | "draft"
  | "pending_hitl"
  | "approved"
  | "running"
  | "paused"
  | "completed"
  | "rejected";

export type LeadStage =
  | "discovered"
  | "engaged"
  | "meeting_scheduled"
  | "meeting_completed"
  | "booked"
  | "lost";

export interface ApiError {
  code: string;
  message: string;
  request_id: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}
