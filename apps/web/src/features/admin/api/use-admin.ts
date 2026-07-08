"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AdminDashboard,
  AdminModuleList,
  OrganizationSettings,
  OrganizationSettingsUpdate,
  SystemStatus,
} from "@/features/admin/types-admin";

const STALE_MS = 600_000;

const ADMIN_SETTINGS_KEY = () => ["admin", "settings"] as const;
const ADMIN_DASHBOARD_KEY = () => ["admin", "dashboard"] as const;
const ADMIN_MODULES_KEY = () => ["admin", "modules"] as const;
const ADMIN_STATUS_KEY = () => ["admin", "system-status"] as const;

export function useAdminSettings() {
  return useQuery<{ data: OrganizationSettings }>({
    queryKey: ADMIN_SETTINGS_KEY(),
    queryFn: () => api.get<{ data: OrganizationSettings }>("/api/v1/admin/settings"),
    staleTime: STALE_MS,
  });
}

export function useUpdateAdminSettings() {
  const qc = useQueryClient();
  return useMutation<
    { data: OrganizationSettings },
    Error,
    OrganizationSettingsUpdate
  >({
    mutationFn: (body) =>
      api.patch<{ data: OrganizationSettings }>("/api/v1/admin/settings", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ADMIN_SETTINGS_KEY() });
      qc.invalidateQueries({ queryKey: ADMIN_DASHBOARD_KEY() });
      qc.invalidateQueries({ queryKey: ADMIN_STATUS_KEY() });
    },
  });
}

export function useAdminDashboard() {
  return useQuery<{ data: AdminDashboard }>({
    queryKey: ADMIN_DASHBOARD_KEY(),
    queryFn: () => api.get<{ data: AdminDashboard }>("/api/v1/admin/dashboard"),
    staleTime: STALE_MS,
  });
}

export function useAdminModules() {
  return useQuery<{ data: AdminModuleList }>({
    queryKey: ADMIN_MODULES_KEY(),
    queryFn: () => api.get<{ data: AdminModuleList }>("/api/v1/admin/modules"),
    staleTime: STALE_MS,
  });
}

export function useAdminSystemStatus() {
  return useQuery<{ data: SystemStatus }>({
    queryKey: ADMIN_STATUS_KEY(),
    queryFn: () => api.get<{ data: SystemStatus }>("/api/v1/admin/system-status"),
    staleTime: STALE_MS,
  });
}
