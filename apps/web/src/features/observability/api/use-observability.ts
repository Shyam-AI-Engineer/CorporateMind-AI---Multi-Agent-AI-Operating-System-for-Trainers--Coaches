// Observability & Diagnostics Center API hooks — Sprint 57

import { useQuery } from "@tanstack/react-query";
import type {
  ApiHealth,
  CacheHealth,
  DatabaseHealth,
  ModuleHealth,
  PlatformSummary,
  RecentErrors,
} from "@/features/observability/types";

const BASE = "/api/v1/observability";
const STALE_MS = 300_000; // 5 minutes — matches Redis TTL

// ── Query keys ─────────────────────────────────────────────────────────────────

export const observabilityKeys = {
  summary: () => ["observability", "summary"] as const,
  cache: () => ["observability", "cache"] as const,
  database: () => ["observability", "database"] as const,
  api: () => ["observability", "api"] as const,
  modules: () => ["observability", "modules"] as const,
  errors: () => ["observability", "errors"] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function usePlatformSummary() {
  return useQuery<PlatformSummary>({
    queryKey: observabilityKeys.summary(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/summary`);
      if (!res.ok) throw new Error("Failed to fetch platform summary");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useCacheHealth() {
  return useQuery<CacheHealth>({
    queryKey: observabilityKeys.cache(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/cache`);
      if (!res.ok) throw new Error("Failed to fetch cache health");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useDatabaseHealth() {
  return useQuery<DatabaseHealth>({
    queryKey: observabilityKeys.database(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/database`);
      if (!res.ok) throw new Error("Failed to fetch database health");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useApiHealth() {
  return useQuery<ApiHealth>({
    queryKey: observabilityKeys.api(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/api`);
      if (!res.ok) throw new Error("Failed to fetch API health");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useModuleHealth() {
  return useQuery<ModuleHealth>({
    queryKey: observabilityKeys.modules(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/modules`);
      if (!res.ok) throw new Error("Failed to fetch module health");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useRecentErrors() {
  return useQuery<RecentErrors>({
    queryKey: observabilityKeys.errors(),
    queryFn: async () => {
      const res = await fetch(`${BASE}/errors`);
      if (!res.ok) throw new Error("Failed to fetch recent errors");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}
