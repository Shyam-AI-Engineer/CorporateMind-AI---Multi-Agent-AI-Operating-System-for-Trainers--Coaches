// Observability & Diagnostics Center types — Sprint 57

export type HealthStatus = "healthy" | "degraded" | "down";
export type ResponseBucket = "fast" | "moderate" | "slow";

export interface PlatformSummary {
  overall_health_score: number;
  api_health: HealthStatus;
  database_health: HealthStatus;
  cache_health: HealthStatus;
  storage_health: HealthStatus;
  active_modules: number;
  healthy_modules: number;
  warning_modules: number;
  checked_at: string;
}

export interface CacheHealth {
  redis_available: boolean;
  estimated_hit_ratio: number;
  estimated_miss_ratio: number;
  ttl_configuration: Record<string, number>;
  checked_at: string;
}

export interface DatabaseHealth {
  connection_ok: boolean;
  estimated_latency_ms: number;
  table_count: number;
  migration_version: string;
  checked_at: string;
}

export interface ApiHealth {
  registered_routes: number;
  average_response_bucket: ResponseBucket;
  error_rate: number;
  checked_at: string;
}

export interface ModuleHealthItem {
  module: string;
  healthy: boolean;
  enabled: boolean;
  record_count: number;
  cache_enabled: boolean;
  checked_at: string;
}

export interface ModuleHealth {
  modules: ModuleHealthItem[];
  total: number;
  healthy: number;
  warning: number;
}

export interface RecentErrorItem {
  source: string;
  message: string;
  severity: "warning" | "critical";
  occurred_at: string;
}

export interface RecentErrors {
  errors: RecentErrorItem[];
  total: number;
  checked_at: string;
}

// ── Display labels ─────────────────────────────────────────────────────────────

export const HEALTH_STATUS_LABELS: Record<HealthStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
};

export const MODULE_DISPLAY_NAMES: Record<string, string> = {
  customers: "Customers",
  training: "Training",
  billing: "Billing",
  payments: "Payments",
  workflows: "Workflows",
  approvals: "Approvals",
  notifications: "Notifications",
  audit: "Audit",
  admin: "Admin",
  integrations: "Integrations",
  reporting: "Reporting",
  executive_dashboard: "Executive Dashboard",
};

export const SEVERITY_LABELS: Record<string, string> = {
  warning: "Warning",
  critical: "Critical",
};
