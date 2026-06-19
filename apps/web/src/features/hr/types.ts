export interface HRContact {
  id: string;
  company_id: string;
  full_name: string;
  title: string;
  email: string;
  email_deliverable: boolean;
  phone: string | null;
  phone_e164: string | null;
  phone_deliverable: boolean;
  whatsapp_opt_in_at: string | null;
  preferred_language: string | null;
  source_type: string;
  is_contactable: boolean;
  opted_in_at: string | null;
  created_at: string;
}

export interface ContactListResponse {
  items: HRContact[];
  total: number;
  limit: number;
  offset: number;
}

export type SourceType =
  | "webinar_registration"
  | "company_website"
  | "public_directory"
  | "referral"
  | "event_badge";

export const SOURCE_TYPES: SourceType[] = [
  "webinar_registration",
  "company_website",
  "public_directory",
  "referral",
  "event_badge",
];

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  webinar_registration: "Webinar Registration",
  company_website:      "Company Website",
  public_directory:     "Public Directory",
  referral:             "Referral",
  event_badge:          "Event Badge",
};

export interface ContactImportItem {
  raw_data: string;
  source: string;
  source_type: SourceType;
  opted_in_at: string | null;
  opt_in_evidence: string | null;
  phone_e164?: string | null;
  whatsapp_opt_in_at?: string | null;
  company_name: string;
  company_industry: string | null;
  company_city: string | null;
  company_country: string | null;
}

export interface ContactBatchImportRequest {
  contacts: ContactImportItem[];
}

export interface ContactBatchImportResponse {
  imported: number;
  non_contactable: number;
  failed: number;
  contact_ids: string[];
}

export interface RankContactsRequest {
  contact_ids: string[];
  trainer_niche: string;
  trainer_topics: string[];
  trainer_target_industries: string[];
}

export interface RankedContact {
  contact_id: string;
  score: number;
  reason: string;
  contact: HRContact;
}

export interface RankContactsResponse {
  rankings: RankedContact[];
}
