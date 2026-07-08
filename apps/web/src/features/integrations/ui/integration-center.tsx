"use client";

import React, { useState } from "react";
import {
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
} from "@/features/integrations/api/use-integrations";
import type { ApiKey, ApiKeyCreated, Webhook, WebhookCreated } from "@/features/integrations/types-integrations";
import { SUPPORTED_WEBHOOK_EVENTS } from "@/features/integrations/types-integrations";

// ── StatusBadge ───────────────────────────────────────────────────────────────

interface StatusBadgeProps {
  active: boolean;
}

export function StatusBadge({ active }: StatusBadgeProps) {
  const cls = active
    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  return (
    <span
      data-testid="status-badge"
      data-active={String(active)}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ── SecretRevealDialog ────────────────────────────────────────────────────────

interface SecretRevealDialogProps {
  title: string;
  secret: string;
  onClose: () => void;
}

export function SecretRevealDialog({ title, secret, onClose }: SecretRevealDialogProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard?.writeText(secret).then(() => {
      setCopied(true);
    });
  };

  return (
    <div data-testid="secret-reveal-dialog" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 data-testid="secret-reveal-title" className="mb-2 text-lg font-semibold">
          {title}
        </h2>
        <p className="mb-4 text-sm text-yellow-700 dark:text-yellow-400" data-testid="secret-warning">
          This value is shown only once. Copy it now — it cannot be retrieved later.
        </p>
        <div className="mb-4 rounded bg-gray-100 p-3 font-mono text-sm break-all dark:bg-gray-800">
          <span data-testid="secret-value">{secret}</span>
        </div>
        <div className="flex gap-3">
          <button
            data-testid="btn-copy-secret"
            onClick={handleCopy}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          <button
            data-testid="btn-close-secret"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm dark:border-gray-600"
          >
            I've saved it
          </button>
        </div>
      </div>
    </div>
  );
}

// ── ApiKeyTable ───────────────────────────────────────────────────────────────

interface ApiKeyTableProps {
  keys: ApiKey[];
  onRevoke: (keyId: string) => void;
  revoking: boolean;
}

export function ApiKeyTable({ keys, onRevoke, revoking }: ApiKeyTableProps) {
  if (keys.length === 0) {
    return (
      <div data-testid="api-key-table-empty" className="py-8 text-center text-sm text-gray-500">
        No API keys yet. Create one to get started.
      </div>
    );
  }

  return (
    <div data-testid="api-key-table" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-gray-500 dark:border-gray-700">
            <th className="pb-2 pr-4">Name</th>
            <th className="pb-2 pr-4">Prefix</th>
            <th className="pb-2 pr-4">Status</th>
            <th className="pb-2 pr-4">Expires</th>
            <th className="pb-2 pr-4">Last used</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id} data-testid={`api-key-row-${k.id}`} className="border-b dark:border-gray-700">
              <td className="py-3 pr-4 font-medium" data-testid={`api-key-name-${k.id}`}>
                {k.name}
              </td>
              <td className="py-3 pr-4 font-mono text-xs" data-testid={`api-key-prefix-${k.id}`}>
                cm_{k.key_prefix}…
              </td>
              <td className="py-3 pr-4">
                <StatusBadge active={k.is_active} />
              </td>
              <td className="py-3 pr-4 text-gray-500" data-testid={`api-key-expires-${k.id}`}>
                {k.expires_at ? new Date(k.expires_at).toLocaleDateString() : "Never"}
              </td>
              <td className="py-3 pr-4 text-gray-500" data-testid={`api-key-last-used-${k.id}`}>
                {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "Never"}
              </td>
              <td className="py-3">
                {k.is_active && (
                  <button
                    data-testid={`btn-revoke-${k.id}`}
                    onClick={() => onRevoke(k.id)}
                    disabled={revoking}
                    className="text-xs text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
                  >
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── CreateApiKeyDialog ────────────────────────────────────────────────────────

interface CreateApiKeyDialogProps {
  workspaceId: string;
  onClose: () => void;
  onCreated: (key: ApiKeyCreated) => void;
  saving: boolean;
  onSubmit: (name: string, expiresAt: string | null) => void;
}

export function CreateApiKeyDialog({
  onClose,
  onCreated: _onCreated,
  saving,
  onSubmit,
}: CreateApiKeyDialogProps) {
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(name, expiresAt || null);
  };

  return (
    <div data-testid="create-api-key-dialog" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-gray-900">
        <h2 className="mb-4 text-lg font-semibold">Create API Key</h2>
        <form data-testid="create-api-key-form" onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input
              data-testid="input-key-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Production webhook consumer"
              className="w-full rounded border px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Expires at (optional)</label>
            <input
              data-testid="input-key-expires"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <button
              data-testid="btn-create-key"
              type="submit"
              disabled={saving || !name.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create Key"}
            </button>
            <button
              data-testid="btn-cancel-key"
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm dark:border-gray-600"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── WebhookTable ──────────────────────────────────────────────────────────────

interface WebhookTableProps {
  webhooks: Webhook[];
  onEdit: (webhook: Webhook) => void;
  onDelete: (webhookId: string) => void;
  deleting: boolean;
}

export function WebhookTable({ webhooks, onEdit, onDelete, deleting }: WebhookTableProps) {
  if (webhooks.length === 0) {
    return (
      <div data-testid="webhook-table-empty" className="py-8 text-center text-sm text-gray-500">
        No webhooks yet. Register one to get started.
      </div>
    );
  }

  return (
    <div data-testid="webhook-table" className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-gray-500 dark:border-gray-700">
            <th className="pb-2 pr-4">Name</th>
            <th className="pb-2 pr-4">URL</th>
            <th className="pb-2 pr-4">Events</th>
            <th className="pb-2 pr-4">Status</th>
            <th className="pb-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {webhooks.map((w) => (
            <tr key={w.id} data-testid={`webhook-row-${w.id}`} className="border-b dark:border-gray-700">
              <td className="py-3 pr-4 font-medium" data-testid={`webhook-name-${w.id}`}>
                {w.name}
              </td>
              <td className="py-3 pr-4 max-w-xs truncate text-gray-500" data-testid={`webhook-url-${w.id}`}>
                {w.url}
              </td>
              <td className="py-3 pr-4" data-testid={`webhook-events-${w.id}`}>
                <span className="text-xs text-gray-500">{w.events.length} event{w.events.length !== 1 ? "s" : ""}</span>
              </td>
              <td className="py-3 pr-4">
                <StatusBadge active={w.is_active} />
              </td>
              <td className="py-3 flex gap-3">
                <button
                  data-testid={`btn-edit-webhook-${w.id}`}
                  onClick={() => onEdit(w)}
                  className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                >
                  Edit
                </button>
                <button
                  data-testid={`btn-delete-webhook-${w.id}`}
                  onClick={() => onDelete(w.id)}
                  disabled={deleting}
                  className="text-xs text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── WebhookDialog ─────────────────────────────────────────────────────────────

interface WebhookDialogProps {
  workspaceId: string;
  webhook?: Webhook | null;
  onClose: () => void;
  saving: boolean;
  onSubmit: (data: { name: string; url: string; events: string[]; is_active?: boolean }) => void;
}

export function WebhookDialog({ webhook, onClose, saving, onSubmit }: WebhookDialogProps) {
  const [name, setName] = useState(webhook?.name ?? "");
  const [url, setUrl] = useState(webhook?.url ?? "");
  const [selectedEvents, setSelectedEvents] = useState<string[]>(webhook?.events ?? []);
  const [isActive, setIsActive] = useState(webhook?.is_active ?? true);

  const isEdit = !!webhook;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name, url, events: selectedEvents, is_active: isActive });
  };

  const toggleEvent = (ev: string) => {
    setSelectedEvents((prev) =>
      prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]
    );
  };

  return (
    <div data-testid="webhook-dialog" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl dark:bg-gray-900 overflow-y-auto max-h-[90vh]">
        <h2 className="mb-4 text-lg font-semibold">
          {isEdit ? "Edit Webhook" : "Register Webhook"}
        </h2>
        <form data-testid="webhook-form" onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <input
              data-testid="input-webhook-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Slack notifications"
              className="w-full rounded border px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">URL</label>
            <input
              data-testid="input-webhook-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://your-server.com/webhook"
              className="w-full rounded border px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              required
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium">Events</label>
            <div data-testid="webhook-events-list" className="grid grid-cols-2 gap-1 max-h-40 overflow-y-auto rounded border p-2 dark:border-gray-600">
              {SUPPORTED_WEBHOOK_EVENTS.map((ev) => (
                <label key={ev} className="flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    data-testid={`event-checkbox-${ev}`}
                    checked={selectedEvents.includes(ev)}
                    onChange={() => toggleEvent(ev)}
                  />
                  {ev}
                </label>
              ))}
            </div>
          </div>
          {isEdit && (
            <div className="flex items-center gap-2">
              <input
                data-testid="checkbox-webhook-active"
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <label className="text-sm">Active</label>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button
              data-testid="btn-submit-webhook"
              type="submit"
              disabled={saving || !name.trim() || !url.trim()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : isEdit ? "Update" : "Register"}
            </button>
            <button
              data-testid="btn-cancel-webhook"
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm dark:border-gray-600"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── IntegrationCenter ─────────────────────────────────────────────────────────

const TABS = ["api-keys", "webhooks"] as const;
type Tab = (typeof TABS)[number];

interface IntegrationCenterProps {
  workspaceId: string;
}

export function IntegrationCenter({ workspaceId }: IntegrationCenterProps) {
  const [activeTab, setActiveTab] = useState<Tab>("api-keys");
  const [showCreateKey, setShowCreateKey] = useState(false);
  const [revealedKey, setRevealedKey] = useState<ApiKeyCreated | null>(null);
  const [showWebhookDialog, setShowWebhookDialog] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<Webhook | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<WebhookCreated | null>(null);

  const { data: apiKeysData, isLoading: keysLoading } = useApiKeys(workspaceId);
  const { data: webhooksData, isLoading: hooksLoading } = useWebhooks(workspaceId);

  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const createWebhook = useCreateWebhook();
  const updateWebhook = useUpdateWebhook();
  const deleteWebhook = useDeleteWebhook();

  const apiKeys = apiKeysData?.data?.items ?? [];
  const webhooks = webhooksData?.data?.items ?? [];

  const handleCreateKey = (name: string, expiresAt: string | null) => {
    createKey.mutate(
      { workspace_id: workspaceId, name, expires_at: expiresAt },
      {
        onSuccess: (res) => {
          setShowCreateKey(false);
          setRevealedKey(res.data);
        },
      }
    );
  };

  const handleRevokeKey = (keyId: string) => {
    revokeKey.mutate({ keyId, workspaceId });
  };

  const handleCreateWebhook = (data: { name: string; url: string; events: string[] }) => {
    createWebhook.mutate(
      { workspace_id: workspaceId, ...data },
      {
        onSuccess: (res) => {
          setShowWebhookDialog(false);
          setRevealedSecret(res.data);
        },
      }
    );
  };

  const handleUpdateWebhook = (data: {
    name: string;
    url: string;
    events: string[];
    is_active?: boolean;
  }) => {
    if (!editingWebhook) return;
    updateWebhook.mutate(
      { webhookId: editingWebhook.id, workspaceId, body: data },
      { onSuccess: () => setEditingWebhook(null) }
    );
  };

  const handleDeleteWebhook = (webhookId: string) => {
    deleteWebhook.mutate({ webhookId, workspaceId });
  };

  return (
    <div data-testid="integration-center" className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Integration Hub</h1>
        <p className="mt-1 text-sm text-gray-500">Manage API keys and outbound webhooks.</p>
      </div>

      {/* Tabs */}
      <div data-testid="integration-tabs" className="mb-6 flex gap-4 border-b dark:border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab}
            data-testid={`tab-${tab}`}
            data-active={String(activeTab === tab)}
            onClick={() => setActiveTab(tab)}
            className={`pb-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab === "api-keys" ? "API Keys" : "Webhooks"}
          </button>
        ))}
      </div>

      {/* API Keys panel */}
      {activeTab === "api-keys" && (
        <div data-testid="panel-api-keys">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              API Keys{" "}
              <span data-testid="api-key-count" className="text-sm font-normal text-gray-500">
                ({apiKeys.length} total)
              </span>
            </h2>
            <button
              data-testid="btn-add-api-key"
              onClick={() => setShowCreateKey(true)}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
            >
              + New Key
            </button>
          </div>

          {keysLoading ? (
            <div data-testid="api-keys-loading" className="py-8 text-center text-sm text-gray-500">
              Loading…
            </div>
          ) : (
            <ApiKeyTable
              keys={apiKeys}
              onRevoke={handleRevokeKey}
              revoking={revokeKey.isPending}
            />
          )}

          {/* Security note */}
          <div
            data-testid="api-key-security-note"
            className="mt-6 rounded border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-950 dark:text-yellow-200"
          >
            API keys grant full access to your workspace. Keep them secret and rotate regularly.
          </div>
        </div>
      )}

      {/* Webhooks panel */}
      {activeTab === "webhooks" && (
        <div data-testid="panel-webhooks">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Webhooks{" "}
              <span data-testid="webhook-count" className="text-sm font-normal text-gray-500">
                ({webhooks.length} total)
              </span>
            </h2>
            <button
              data-testid="btn-add-webhook"
              onClick={() => setShowWebhookDialog(true)}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
            >
              + Register Webhook
            </button>
          </div>

          {hooksLoading ? (
            <div data-testid="webhooks-loading" className="py-8 text-center text-sm text-gray-500">
              Loading…
            </div>
          ) : (
            <WebhookTable
              webhooks={webhooks}
              onEdit={(w) => setEditingWebhook(w)}
              onDelete={handleDeleteWebhook}
              deleting={deleteWebhook.isPending}
            />
          )}

          {/* Security note */}
          <div
            data-testid="webhook-security-note"
            className="mt-6 rounded border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200"
          >
            Webhook signing secrets are shown once. Use them to verify HMAC-SHA256 signatures on incoming payloads.
          </div>
        </div>
      )}

      {/* Dialogs */}
      {showCreateKey && (
        <CreateApiKeyDialog
          workspaceId={workspaceId}
          onClose={() => setShowCreateKey(false)}
          onCreated={setRevealedKey}
          saving={createKey.isPending}
          onSubmit={handleCreateKey}
        />
      )}

      {revealedKey && (
        <SecretRevealDialog
          title="API Key Created"
          secret={revealedKey.plain_key}
          onClose={() => setRevealedKey(null)}
        />
      )}

      {(showWebhookDialog || editingWebhook) && (
        <WebhookDialog
          workspaceId={workspaceId}
          webhook={editingWebhook}
          onClose={() => {
            setShowWebhookDialog(false);
            setEditingWebhook(null);
          }}
          saving={createWebhook.isPending || updateWebhook.isPending}
          onSubmit={editingWebhook ? handleUpdateWebhook : handleCreateWebhook}
        />
      )}

      {revealedSecret && (
        <SecretRevealDialog
          title="Webhook Registered"
          secret={revealedSecret.secret}
          onClose={() => setRevealedSecret(null)}
        />
      )}
    </div>
  );
}
