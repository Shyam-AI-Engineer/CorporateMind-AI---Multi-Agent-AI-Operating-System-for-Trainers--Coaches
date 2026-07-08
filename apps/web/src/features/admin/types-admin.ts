/** Organization administration types — Sprint 54. */

export type AdminCurrency = "INR" | "USD" | "EUR" | "GBP" | "SGD" | "AED";
export type AdminLanguage = "en" | "hi" | "ta" | "bn" | "mr" | "te" | "kn" | "gu";
export type AdminDateFormat = "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYY-MM-DD";

export const ADMIN_CURRENCIES: AdminCurrency[] = ["INR", "USD", "EUR", "GBP", "SGD", "AED"];
export const ADMIN_LANGUAGES: AdminLanguage[] = ["en", "hi", "ta", "bn", "mr", "te", "kn", "gu"];
export const ADMIN_DATE_FORMATS: AdminDateFormat[] = ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"];

export const MODULE_NAMES = [
  "customers",
  "training",
  "billing",
  "payments",
  "notifications",
  "audit",
  "workflow",
  "team",
] as const;

export type ModuleName = (typeof MODULE_NAMES)[number];

export interface OrganizationSettings {
  id: string;
  tenant_id: string;
  organization_name: string;
  timezone: string;
  currency: string;
  date_format: string;
  language: string;
  default_workflow_id: string | null;
  default_training_duration_days: number;
  default_invoice_due_days: number;
  logo_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationSettingsUpdate {
  organization_name?: string;
  timezone?: string;
  currency?: string;
  date_format?: string;
  language?: string;
  default_workflow_id?: string | null;
  default_training_duration_days?: number;
  default_invoice_due_days?: number;
  logo_url?: string | null;
}

export interface ModuleStatus {
  name: string;
  enabled: boolean;
  healthy: boolean;
  record_count: number;
}

export interface SystemStatus {
  modules: ModuleStatus[];
  overall_healthy: boolean;
  checked_at: string;
}

export interface AdminDashboard {
  organization_name: string;
  tenant_id: string;
  is_active: boolean;
  module_count: number;
  healthy_module_count: number;
  total_records: number;
  settings_last_updated: string;
  system_status: SystemStatus;
}

export interface AdminModuleList {
  modules: string[];
  total: number;
}
