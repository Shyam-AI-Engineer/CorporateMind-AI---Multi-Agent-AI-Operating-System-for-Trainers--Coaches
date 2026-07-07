"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Customer360,
  CustomerRelationshipSummary,
  CustomerTimelinePage,
  TimelineEventType,
} from "@/features/customers/types-timeline";

const STALE_MS = 300_000;

const TIMELINE_KEY = (customerId: string, filters?: object) =>
  ["customer-timeline", customerId, filters ?? {}] as const;

const SUMMARY_KEY = (customerId: string) =>
  ["customer-relationship-summary", customerId] as const;

const C360_KEY = (customerId: string) =>
  ["customer-360", customerId] as const;

export function useCustomerTimeline(
  customerId: string | null | undefined,
  workspaceId: string,
  opts?: {
    event_types?: TimelineEventType[];
    cursor?: string;
    limit?: number;
  }
) {
  const eventTypes = opts?.event_types;
  const cursor = opts?.cursor;
  const limit = opts?.limit;
  return useQuery<{ data: CustomerTimelinePage }>({
    queryKey: TIMELINE_KEY(customerId ?? "", { eventTypes, cursor, limit }),
    queryFn: () => {
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (cursor) params.set("cursor", cursor);
      if (limit) params.set("limit", String(limit));
      if (eventTypes?.length) {
        eventTypes.forEach((t) => params.append("event_type", t));
      }
      return api.get<{ data: CustomerTimelinePage }>(
        `/api/v1/customer-timeline/${customerId}?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!customerId && !!workspaceId,
  });
}

export function useRelationshipSummary(
  customerId: string | null | undefined,
  workspaceId: string
) {
  return useQuery<{ data: CustomerRelationshipSummary }>({
    queryKey: SUMMARY_KEY(customerId ?? ""),
    queryFn: () =>
      api.get<{ data: CustomerRelationshipSummary }>(
        `/api/v1/customer-relationship-summary/${customerId}?workspace_id=${workspaceId}`
      ),
    staleTime: STALE_MS,
    enabled: !!customerId && !!workspaceId,
  });
}

export function useCustomer360(
  customerId: string | null | undefined,
  workspaceId: string
) {
  return useQuery<{ data: Customer360 }>({
    queryKey: C360_KEY(customerId ?? ""),
    queryFn: () =>
      api.get<{ data: Customer360 }>(
        `/api/v1/customer-360/${customerId}?workspace_id=${workspaceId}`
      ),
    staleTime: STALE_MS,
    enabled: !!customerId && !!workspaceId,
  });
}
