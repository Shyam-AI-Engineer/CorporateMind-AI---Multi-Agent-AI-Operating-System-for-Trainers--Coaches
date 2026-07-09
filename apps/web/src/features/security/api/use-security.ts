// Security Center TanStack Query hooks — Sprint 58

import { useQuery } from "@tanstack/react-query";
import type {
  ApiKeyHealth,
  AuditSummary,
  PermissionOverview,
  RoleDistribution,
  SecurityAlerts,
  SecuritySummary,
} from "@/features/security/types";
import api from "@/lib/api";

export const securityKeys = {
  all: ["security"] as const,
  summary: () => [...securityKeys.all, "summary"] as const,
  roles: () => [...securityKeys.all, "roles"] as const,
  apiKeys: () => [...securityKeys.all, "api-keys"] as const,
  audit: () => [...securityKeys.all, "audit"] as const,
  permissions: () => [...securityKeys.all, "permissions"] as const,
  alerts: () => [...securityKeys.all, "alerts"] as const,
};

export function useSecuritySummary() {
  return useQuery<SecuritySummary>({
    queryKey: securityKeys.summary(),
    queryFn: () => api.get("/api/v1/security/summary").then((r) => r.data),
    staleTime: 300_000,
  });
}

export function useRoleDistribution() {
  return useQuery<RoleDistribution>({
    queryKey: securityKeys.roles(),
    queryFn: () => api.get("/api/v1/security/roles").then((r) => r.data),
    staleTime: 300_000,
  });
}

export function useApiKeyHealth() {
  return useQuery<ApiKeyHealth>({
    queryKey: securityKeys.apiKeys(),
    queryFn: () => api.get("/api/v1/security/api-keys").then((r) => r.data),
    staleTime: 300_000,
  });
}

export function useAuditSummary() {
  return useQuery<AuditSummary>({
    queryKey: securityKeys.audit(),
    queryFn: () => api.get("/api/v1/security/audit").then((r) => r.data),
    staleTime: 300_000,
  });
}

export function usePermissionOverview() {
  return useQuery<PermissionOverview>({
    queryKey: securityKeys.permissions(),
    queryFn: () =>
      api.get("/api/v1/security/permissions").then((r) => r.data),
    staleTime: 300_000,
  });
}

export function useSecurityAlerts() {
  return useQuery<SecurityAlerts>({
    queryKey: securityKeys.alerts(),
    queryFn: () => api.get("/api/v1/security/alerts").then((r) => r.data),
    staleTime: 300_000,
  });
}
