"use client";

/**
 * TanStack Query hooks for CRM activity timeline + follow-up queue.
 *
 * Lives alongside use-leads.ts in the existing CRM feature folder — these
 * are CRM read surfaces, not a new feature module.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ActivityListOut, FollowUpListOut } from "@/features/crm/types";

const ACTIVITIES_KEY = (params: ActivityQueryParams) =>
  ["crm", "activities", params] as const;

const FOLLOW_UPS_KEY = (params: FollowUpQueryParams) =>
  ["crm", "follow-ups", params] as const;

export interface ActivityQueryParams {
  workspace_id?: string;
  lead_id?: string;
  contact_id?: string;
  limit?: number;
  offset?: number;
}

export interface FollowUpQueryParams {
  workspace_id: string | null | undefined;
  status?: string;
  limit?: number;
  offset?: number;
}

export function useActivities(params: ActivityQueryParams) {
  const search = new URLSearchParams();
  if (params.workspace_id) search.set("workspace_id", params.workspace_id);
  if (params.lead_id) search.set("lead_id", params.lead_id);
  if (params.contact_id) search.set("contact_id", params.contact_id);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));

  const scoped = !!(params.workspace_id || params.lead_id || params.contact_id);
  return useQuery({
    queryKey: ACTIVITIES_KEY(params),
    queryFn: () => api.get<ActivityListOut>(`/api/v1/crm/activities?${search}`),
    // The endpoint rejects unscoped queries (422); we mirror that gate here
    // so React Query never fires the doomed request.
    enabled: scoped,
    staleTime: 20 * 1000,
  });
}

export function useFollowUps(params: FollowUpQueryParams) {
  const { workspace_id, status, limit, offset } = params;
  const search = new URLSearchParams();
  if (workspace_id) search.set("workspace_id", workspace_id);
  if (status) search.set("status", status);
  search.set("limit", String(limit ?? 50));
  search.set("offset", String(offset ?? 0));

  return useQuery({
    queryKey: FOLLOW_UPS_KEY(params),
    queryFn: () => api.get<FollowUpListOut>(`/api/v1/crm/follow-ups?${search}`),
    enabled: !!workspace_id,
    staleTime: 20 * 1000,
  });
}
