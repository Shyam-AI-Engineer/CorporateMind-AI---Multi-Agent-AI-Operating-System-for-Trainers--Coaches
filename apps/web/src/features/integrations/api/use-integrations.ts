// Integration Hub API hooks — Sprint 55

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ApiKey,
  ApiKeyCreated,
  ApiKeyCreateRequest,
  ApiKeyListOut,
  Webhook,
  WebhookCreated,
  WebhookCreateRequest,
  WebhookListOut,
  WebhookUpdateRequest,
} from "@/features/integrations/types-integrations";

const BASE = "/api/v1/integrations";
const STALE_MS = 300_000; // 5 minutes — matches Redis TTL

// ── Query keys ─────────────────────────────────────────────────────────────

export const integrationKeys = {
  apiKeys: (workspaceId: string) => ["integrations", "api-keys", workspaceId] as const,
  webhooks: (workspaceId: string) => ["integrations", "webhooks", workspaceId] as const,
};

// ── API Key hooks ──────────────────────────────────────────────────────────

export function useApiKeys(workspaceId: string) {
  return useQuery<{ data: ApiKeyListOut }>({
    queryKey: integrationKeys.apiKeys(workspaceId),
    queryFn: async () => {
      const res = await fetch(`${BASE}/api-keys?workspace_id=${workspaceId}`);
      if (!res.ok) throw new Error("Failed to fetch API keys");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation<{ data: ApiKeyCreated }, Error, ApiKeyCreateRequest>({
    mutationFn: async (body) => {
      const res = await fetch(`${BASE}/api-keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("Failed to create API key");
      return res.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: integrationKeys.apiKeys(vars.workspace_id) });
    },
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  return useMutation<{ data: ApiKey }, Error, { keyId: string; workspaceId: string }>({
    mutationFn: async ({ keyId }) => {
      const res = await fetch(`${BASE}/api-keys/${keyId}/revoke`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to revoke API key");
      return res.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: integrationKeys.apiKeys(vars.workspaceId) });
    },
  });
}

// ── Webhook hooks ──────────────────────────────────────────────────────────

export function useWebhooks(workspaceId: string) {
  return useQuery<{ data: WebhookListOut }>({
    queryKey: integrationKeys.webhooks(workspaceId),
    queryFn: async () => {
      const res = await fetch(`${BASE}/webhooks?workspace_id=${workspaceId}`);
      if (!res.ok) throw new Error("Failed to fetch webhooks");
      return res.json();
    },
    staleTime: STALE_MS,
  });
}

export function useCreateWebhook() {
  const qc = useQueryClient();
  return useMutation<{ data: WebhookCreated }, Error, WebhookCreateRequest>({
    mutationFn: async (body) => {
      const res = await fetch(`${BASE}/webhooks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("Failed to create webhook");
      return res.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: integrationKeys.webhooks(vars.workspace_id) });
    },
  });
}

export function useUpdateWebhook() {
  const qc = useQueryClient();
  return useMutation<
    { data: Webhook },
    Error,
    { webhookId: string; workspaceId: string; body: WebhookUpdateRequest }
  >({
    mutationFn: async ({ webhookId, body }) => {
      const res = await fetch(`${BASE}/webhooks/${webhookId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error("Failed to update webhook");
      return res.json();
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: integrationKeys.webhooks(vars.workspaceId) });
    },
  });
}

export function useDeleteWebhook() {
  const qc = useQueryClient();
  return useMutation<void, Error, { webhookId: string; workspaceId: string }>({
    mutationFn: async ({ webhookId }) => {
      const res = await fetch(`${BASE}/webhooks/${webhookId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete webhook");
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: integrationKeys.webhooks(vars.workspaceId) });
    },
  });
}
