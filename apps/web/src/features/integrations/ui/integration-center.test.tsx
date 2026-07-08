/**
 * Frontend unit tests — Sprint 55: Integration Hub (part 1).
 * Target: 135+ tests in this file. NO jest-dom matchers.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

// ── Mock data ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-0001";

const mockKey1 = {
  id: "key-0001",
  tenant_id: "tnt-0001",
  workspace_id: WS_ID,
  name: "Production Key",
  key_prefix: "abcd1234",
  last_used_at: null,
  expires_at: null,
  is_active: true,
  created_by: "usr-0001",
  created_at: "2026-07-08T10:00:00Z",
};

const mockKey2 = {
  ...mockKey1,
  id: "key-0002",
  name: "Dev Key",
  key_prefix: "efgh5678",
  is_active: false,
};

const mockWebhook1 = {
  id: "wh-0001",
  tenant_id: "tnt-0001",
  workspace_id: WS_ID,
  name: "Slack Alerts",
  url: "https://hooks.slack.com/services/T00",
  events: ["customer.created", "invoice.paid"],
  is_active: true,
  last_delivery_at: null,
  created_by: "usr-0001",
  created_at: "2026-07-08T10:00:00Z",
};

const mockWebhook2 = {
  ...mockWebhook1,
  id: "wh-0002",
  name: "CRM Sync",
  url: "https://crm.example.com/hook",
  events: [],
  is_active: false,
};

// ── Mock hooks ────────────────────────────────────────────────────────────────

vi.mock("@/features/integrations/api/use-integrations", () => ({
  useApiKeys: vi.fn(() => ({ data: { data: { items: [mockKey1, mockKey2], total: 2 } }, isLoading: false })),
  useWebhooks: vi.fn(() => ({ data: { data: { items: [mockWebhook1, mockWebhook2], total: 2 } }, isLoading: false })),
  useCreateApiKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRevokeApiKey: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCreateWebhook: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateWebhook: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteWebhook: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

import {
  StatusBadge,
  ApiKeyTable,
  CreateApiKeyDialog,
  SecretRevealDialog,
  WebhookTable,
  WebhookDialog,
  IntegrationCenter,
} from "./integration-center";
import * as hooks from "@/features/integrations/api/use-integrations";
import { SUPPORTED_WEBHOOK_EVENTS } from "@/features/integrations/types-integrations";

// ── Default mock restore helpers ──────────────────────────────────────────────

const _defaultApiKeysMock = () => ({ data: { data: { items: [mockKey1, mockKey2], total: 2 } }, isLoading: false });
const _defaultWebhooksMock = () => ({ data: { data: { items: [mockWebhook1, mockWebhook2], total: 2 } }, isLoading: false });
const _defaultCreateKeyMock = () => ({ mutate: vi.fn(), isPending: false });
const _defaultRevokeKeyMock = () => ({ mutate: vi.fn(), isPending: false });
const _defaultCreateWebhookMock = () => ({ mutate: vi.fn(), isPending: false });
const _defaultUpdateWebhookMock = () => ({ mutate: vi.fn(), isPending: false });
const _defaultDeleteWebhookMock = () => ({ mutate: vi.fn(), isPending: false });

afterEach(() => {
  vi.mocked(hooks.useApiKeys).mockReturnValue(_defaultApiKeysMock() as any);
  vi.mocked(hooks.useWebhooks).mockReturnValue(_defaultWebhooksMock() as any);
  vi.mocked(hooks.useCreateApiKey).mockReturnValue(_defaultCreateKeyMock() as any);
  vi.mocked(hooks.useRevokeApiKey).mockReturnValue(_defaultRevokeKeyMock() as any);
  vi.mocked(hooks.useCreateWebhook).mockReturnValue(_defaultCreateWebhookMock() as any);
  vi.mocked(hooks.useUpdateWebhook).mockReturnValue(_defaultUpdateWebhookMock() as any);
  vi.mocked(hooks.useDeleteWebhook).mockReturnValue(_defaultDeleteWebhookMock() as any);
});

// ── 1. StatusBadge ────────────────────────────────────────────────────────────

describe("StatusBadge", () => {
  it("renders active state", () => {
    render(<StatusBadge active={true} />);
    expect(screen.getByTestId("status-badge")).not.toBeNull();
  });

  it("shows Active text when active", () => {
    render(<StatusBadge active={true} />);
    expect(screen.getByTestId("status-badge").textContent).toContain("Active");
  });

  it("shows Inactive text when not active", () => {
    render(<StatusBadge active={false} />);
    expect(screen.getByTestId("status-badge").textContent).toContain("Inactive");
  });

  it("data-active is 'true' when active", () => {
    render(<StatusBadge active={true} />);
    expect(screen.getByTestId("status-badge").getAttribute("data-active")).toBe("true");
  });

  it("data-active is 'false' when inactive", () => {
    render(<StatusBadge active={false} />);
    expect(screen.getByTestId("status-badge").getAttribute("data-active")).toBe("false");
  });

  it("active badge has green class", () => {
    render(<StatusBadge active={true} />);
    expect(screen.getByTestId("status-badge").className).toContain("green");
  });

  it("inactive badge has gray class", () => {
    render(<StatusBadge active={false} />);
    expect(screen.getByTestId("status-badge").className).toContain("gray");
  });

  it("has inline-flex class", () => {
    render(<StatusBadge active={true} />);
    expect(screen.getByTestId("status-badge").className).toContain("inline-flex");
  });
});

// ── 2. SecretRevealDialog ─────────────────────────────────────────────────────

describe("SecretRevealDialog", () => {
  it("renders the dialog", () => {
    render(<SecretRevealDialog title="API Key Created" secret="abc123" onClose={vi.fn()} />);
    expect(screen.getByTestId("secret-reveal-dialog")).not.toBeNull();
  });

  it("shows the title", () => {
    render(<SecretRevealDialog title="My Title" secret="s3cr3t" onClose={vi.fn()} />);
    expect(screen.getByTestId("secret-reveal-title").textContent).toContain("My Title");
  });

  it("shows the secret value", () => {
    render(<SecretRevealDialog title="T" secret="mysecretvalue" onClose={vi.fn()} />);
    expect(screen.getByTestId("secret-value").textContent).toContain("mysecretvalue");
  });

  it("shows warning message", () => {
    render(<SecretRevealDialog title="T" secret="x" onClose={vi.fn()} />);
    const warning = screen.getByTestId("secret-warning");
    expect(warning.textContent).toContain("shown only once");
  });

  it("copy button exists", () => {
    render(<SecretRevealDialog title="T" secret="x" onClose={vi.fn()} />);
    expect(screen.getByTestId("btn-copy-secret")).not.toBeNull();
  });

  it("close button exists", () => {
    render(<SecretRevealDialog title="T" secret="x" onClose={vi.fn()} />);
    expect(screen.getByTestId("btn-close-secret")).not.toBeNull();
  });

  it("close button calls onClose", () => {
    const onClose = vi.fn();
    render(<SecretRevealDialog title="T" secret="x" onClose={onClose} />);
    fireEvent.click(screen.getByTestId("btn-close-secret"));
    expect(onClose).toHaveBeenCalled();
  });

  it("copy button text is Copy initially", () => {
    render(<SecretRevealDialog title="T" secret="x" onClose={vi.fn()} />);
    expect(screen.getByTestId("btn-copy-secret").textContent).toContain("Copy");
  });
});

// ── 3. ApiKeyTable ────────────────────────────────────────────────────────────

describe("ApiKeyTable", () => {
  it("shows empty state when no keys", () => {
    render(<ApiKeyTable keys={[]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId("api-key-table-empty")).not.toBeNull();
  });

  it("renders table when keys present", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId("api-key-table")).not.toBeNull();
  });

  it("renders row for each key", () => {
    render(<ApiKeyTable keys={[mockKey1, mockKey2]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`api-key-row-${mockKey1.id}`)).not.toBeNull();
    expect(screen.getByTestId(`api-key-row-${mockKey2.id}`)).not.toBeNull();
  });

  it("shows key name", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`api-key-name-${mockKey1.id}`).textContent).toContain("Production Key");
  });

  it("shows key prefix with cm_ prefix", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`api-key-prefix-${mockKey1.id}`).textContent).toContain("cm_");
  });

  it("shows revoke button for active key", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`btn-revoke-${mockKey1.id}`)).not.toBeNull();
  });

  it("no revoke button for inactive key", () => {
    render(<ApiKeyTable keys={[mockKey2]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.queryByTestId(`btn-revoke-${mockKey2.id}`)).toBeNull();
  });

  it("revoke button calls onRevoke with key id", () => {
    const onRevoke = vi.fn();
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={onRevoke} revoking={false} />);
    fireEvent.click(screen.getByTestId(`btn-revoke-${mockKey1.id}`));
    expect(onRevoke).toHaveBeenCalledWith(mockKey1.id);
  });

  it("revoke button disabled when revoking", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={true} />);
    const btn = screen.getByTestId(`btn-revoke-${mockKey1.id}`) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("shows Never for null expires_at", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`api-key-expires-${mockKey1.id}`).textContent).toContain("Never");
  });

  it("shows Never for null last_used_at", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId(`api-key-last-used-${mockKey1.id}`).textContent).toContain("Never");
  });

  it("status badge shows active state", () => {
    render(<ApiKeyTable keys={[mockKey1]} onRevoke={vi.fn()} revoking={false} />);
    const badge = screen.getAllByTestId("status-badge")[0];
    expect(badge.getAttribute("data-active")).toBe("true");
  });

  it("inactive key shows inactive badge", () => {
    render(<ApiKeyTable keys={[mockKey2]} onRevoke={vi.fn()} revoking={false} />);
    const badge = screen.getAllByTestId("status-badge")[0];
    expect(badge.getAttribute("data-active")).toBe("false");
  });

  it("empty state message mentions creating", () => {
    render(<ApiKeyTable keys={[]} onRevoke={vi.fn()} revoking={false} />);
    expect(screen.getByTestId("api-key-table-empty").textContent).toContain("Create");
  });
});

// ── 4. CreateApiKeyDialog ─────────────────────────────────────────────────────

describe("CreateApiKeyDialog", () => {
  const defaults = {
    workspaceId: WS_ID,
    onClose: vi.fn(),
    onCreated: vi.fn(),
    saving: false,
    onSubmit: vi.fn(),
  };

  it("renders the dialog", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    expect(screen.getByTestId("create-api-key-dialog")).not.toBeNull();
  });

  it("has name input", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    expect(screen.getByTestId("input-key-name")).not.toBeNull();
  });

  it("has expires input", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    expect(screen.getByTestId("input-key-expires")).not.toBeNull();
  });

  it("has create button", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    expect(screen.getByTestId("btn-create-key")).not.toBeNull();
  });

  it("has cancel button", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    expect(screen.getByTestId("btn-cancel-key")).not.toBeNull();
  });

  it("cancel button calls onClose", () => {
    const onClose = vi.fn();
    render(<CreateApiKeyDialog {...defaults} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("btn-cancel-key"));
    expect(onClose).toHaveBeenCalled();
  });

  it("create button disabled when saving", () => {
    render(<CreateApiKeyDialog {...defaults} saving={true} />);
    const btn = screen.getByTestId("btn-create-key") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("create button disabled when name empty", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    const btn = screen.getByTestId("btn-create-key") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("create button enabled after typing name", () => {
    const onSubmit = vi.fn();
    render(<CreateApiKeyDialog {...defaults} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("input-key-name"), { target: { value: "My Key" } });
    const btn = screen.getByTestId("btn-create-key") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("submitting form calls onSubmit with name", () => {
    const onSubmit = vi.fn();
    render(<CreateApiKeyDialog {...defaults} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("input-key-name"), { target: { value: "My Key" } });
    fireEvent.submit(screen.getByTestId("create-api-key-form"));
    expect(onSubmit).toHaveBeenCalledWith("My Key", null);
  });

  it("shows Creating when saving", () => {
    render(<CreateApiKeyDialog {...defaults} saving={true} />);
    expect(screen.getByTestId("btn-create-key").textContent).toContain("Creating");
  });

  it("name input is type text", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    const input = screen.getByTestId("input-key-name") as HTMLInputElement;
    expect(input.type).toBe("text");
  });

  it("expires input is type datetime-local", () => {
    render(<CreateApiKeyDialog {...defaults} />);
    const input = screen.getByTestId("input-key-expires") as HTMLInputElement;
    expect(input.type).toBe("datetime-local");
  });
});

// ── 5. WebhookTable ───────────────────────────────────────────────────────────

describe("WebhookTable", () => {
  it("shows empty state when no webhooks", () => {
    render(<WebhookTable webhooks={[]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId("webhook-table-empty")).not.toBeNull();
  });

  it("renders table when webhooks present", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId("webhook-table")).not.toBeNull();
  });

  it("renders row for each webhook", () => {
    render(<WebhookTable webhooks={[mockWebhook1, mockWebhook2]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`webhook-row-${mockWebhook1.id}`)).not.toBeNull();
    expect(screen.getByTestId(`webhook-row-${mockWebhook2.id}`)).not.toBeNull();
  });

  it("shows webhook name", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`webhook-name-${mockWebhook1.id}`).textContent).toContain("Slack Alerts");
  });

  it("shows webhook url", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`webhook-url-${mockWebhook1.id}`).textContent).toContain("hooks.slack.com");
  });

  it("shows event count", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`webhook-events-${mockWebhook1.id}`).textContent).toContain("2");
  });

  it("shows edit button for each webhook", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`btn-edit-webhook-${mockWebhook1.id}`)).not.toBeNull();
  });

  it("shows delete button for each webhook", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`btn-delete-webhook-${mockWebhook1.id}`)).not.toBeNull();
  });

  it("edit button calls onEdit with webhook", () => {
    const onEdit = vi.fn();
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={onEdit} onDelete={vi.fn()} deleting={false} />);
    fireEvent.click(screen.getByTestId(`btn-edit-webhook-${mockWebhook1.id}`));
    expect(onEdit).toHaveBeenCalledWith(mockWebhook1);
  });

  it("delete button calls onDelete with webhook id", () => {
    const onDelete = vi.fn();
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={onDelete} deleting={false} />);
    fireEvent.click(screen.getByTestId(`btn-delete-webhook-${mockWebhook1.id}`));
    expect(onDelete).toHaveBeenCalledWith(mockWebhook1.id);
  });

  it("delete button disabled when deleting", () => {
    render(<WebhookTable webhooks={[mockWebhook1]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={true} />);
    const btn = screen.getByTestId(`btn-delete-webhook-${mockWebhook1.id}`) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("empty state mentions registering", () => {
    render(<WebhookTable webhooks={[]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId("webhook-table-empty").textContent).toContain("Register");
  });

  it("inactive webhook shows inactive badge", () => {
    render(<WebhookTable webhooks={[mockWebhook2]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    const badges = screen.getAllByTestId("status-badge");
    expect(badges[0].getAttribute("data-active")).toBe("false");
  });

  it("0 events shows correct label", () => {
    render(<WebhookTable webhooks={[mockWebhook2]} onEdit={vi.fn()} onDelete={vi.fn()} deleting={false} />);
    expect(screen.getByTestId(`webhook-events-${mockWebhook2.id}`).textContent).toContain("0");
  });
});

// ── 6. WebhookDialog ──────────────────────────────────────────────────────────

describe("WebhookDialog", () => {
  const defaults = {
    workspaceId: WS_ID,
    webhook: null,
    onClose: vi.fn(),
    saving: false,
    onSubmit: vi.fn(),
  };

  it("renders dialog", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("webhook-dialog")).not.toBeNull();
  });

  it("has name input", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("input-webhook-name")).not.toBeNull();
  });

  it("has url input", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("input-webhook-url")).not.toBeNull();
  });

  it("has events list", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("webhook-events-list")).not.toBeNull();
  });

  it("submit button exists", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("btn-submit-webhook")).not.toBeNull();
  });

  it("cancel button exists", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("btn-cancel-webhook")).not.toBeNull();
  });

  it("cancel calls onClose", () => {
    const onClose = vi.fn();
    render(<WebhookDialog {...defaults} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("btn-cancel-webhook"));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows Register when creating", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.getByTestId("btn-submit-webhook").textContent).toContain("Register");
  });

  it("shows Update when editing", () => {
    render(<WebhookDialog {...defaults} webhook={mockWebhook1} />);
    expect(screen.getByTestId("btn-submit-webhook").textContent).toContain("Update");
  });

  it("prefills name when editing", () => {
    render(<WebhookDialog {...defaults} webhook={mockWebhook1} />);
    const input = screen.getByTestId("input-webhook-name") as HTMLInputElement;
    expect(input.value).toBe("Slack Alerts");
  });

  it("prefills url when editing", () => {
    render(<WebhookDialog {...defaults} webhook={mockWebhook1} />);
    const input = screen.getByTestId("input-webhook-url") as HTMLInputElement;
    expect(input.value).toBe("https://hooks.slack.com/services/T00");
  });

  it("shows event checkboxes for all events", () => {
    render(<WebhookDialog {...defaults} />);
    SUPPORTED_WEBHOOK_EVENTS.forEach((ev) => {
      expect(screen.getByTestId(`event-checkbox-${ev}`)).not.toBeNull();
    });
  });

  it("submit disabled when name empty", () => {
    render(<WebhookDialog {...defaults} />);
    const btn = screen.getByTestId("btn-submit-webhook") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit disabled when saving", () => {
    render(<WebhookDialog {...defaults} saving={true} />);
    const btn = screen.getByTestId("btn-submit-webhook") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit calls onSubmit with form data", () => {
    const onSubmit = vi.fn();
    render(<WebhookDialog {...defaults} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("input-webhook-name"), { target: { value: "My Hook" } });
    fireEvent.change(screen.getByTestId("input-webhook-url"), { target: { value: "https://x.com" } });
    fireEvent.submit(screen.getByTestId("webhook-form"));
    expect(onSubmit).toHaveBeenCalled();
    expect(onSubmit.mock.calls[0][0]).toHaveProperty("name", "My Hook");
  });

  it("toggling event checkbox adds to events list", () => {
    const onSubmit = vi.fn();
    render(<WebhookDialog {...defaults} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("input-webhook-name"), { target: { value: "H" } });
    fireEvent.change(screen.getByTestId("input-webhook-url"), { target: { value: "https://x.com" } });
    fireEvent.click(screen.getByTestId("event-checkbox-customer.created"));
    fireEvent.submit(screen.getByTestId("webhook-form"));
    expect(onSubmit.mock.calls[0][0].events).toContain("customer.created");
  });

  it("shows active checkbox when editing", () => {
    render(<WebhookDialog {...defaults} webhook={mockWebhook1} />);
    expect(screen.getByTestId("checkbox-webhook-active")).not.toBeNull();
  });

  it("no active checkbox when creating", () => {
    render(<WebhookDialog {...defaults} />);
    expect(screen.queryByTestId("checkbox-webhook-active")).toBeNull();
  });

  it("shows Saving when saving", () => {
    render(<WebhookDialog {...defaults} saving={true} />);
    expect(screen.getByTestId("btn-submit-webhook").textContent).toContain("Saving");
  });

  it("url input type is url", () => {
    render(<WebhookDialog {...defaults} />);
    const input = screen.getByTestId("input-webhook-url") as HTMLInputElement;
    expect(input.type).toBe("url");
  });
});

// ── 7. IntegrationCenter ──────────────────────────────────────────────────────

describe("IntegrationCenter", () => {
  it("renders the center", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("integration-center")).not.toBeNull();
  });

  it("renders tab bar", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("integration-tabs")).not.toBeNull();
  });

  it("renders api-keys tab button", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("tab-api-keys")).not.toBeNull();
  });

  it("renders webhooks tab button", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("tab-webhooks")).not.toBeNull();
  });

  it("api-keys tab is active by default", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("tab-api-keys").getAttribute("data-active")).toBe("true");
  });

  it("webhooks tab is not active by default", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("tab-webhooks").getAttribute("data-active")).toBe("false");
  });

  it("shows api-keys panel by default", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("panel-api-keys")).not.toBeNull();
  });

  it("switches to webhooks panel on tab click", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.getByTestId("panel-webhooks")).not.toBeNull();
  });

  it("hides api-keys panel after switching tab", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.queryByTestId("panel-api-keys")).toBeNull();
  });

  it("shows key count in api-keys panel", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("api-key-count").textContent).toContain("2");
  });

  it("shows add api key button", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("btn-add-api-key")).not.toBeNull();
  });

  it("clicking add api key button shows create dialog", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("btn-add-api-key"));
    expect(screen.getByTestId("create-api-key-dialog")).not.toBeNull();
  });

  it("shows webhook count in webhooks panel", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.getByTestId("webhook-count").textContent).toContain("2");
  });

  it("shows add webhook button in webhooks panel", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.getByTestId("btn-add-webhook")).not.toBeNull();
  });

  it("clicking add webhook button shows webhook dialog", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId("btn-add-webhook"));
    expect(screen.getByTestId("webhook-dialog")).not.toBeNull();
  });

  it("shows security note in api-keys panel", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("api-key-security-note")).not.toBeNull();
  });

  it("shows security note in webhooks panel", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.getByTestId("webhook-security-note")).not.toBeNull();
  });

  it("cancel in create key dialog closes it", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("btn-add-api-key"));
    fireEvent.click(screen.getByTestId("btn-cancel-key"));
    expect(screen.queryByTestId("create-api-key-dialog")).toBeNull();
  });

  it("cancel in webhook dialog closes it", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId("btn-add-webhook"));
    fireEvent.click(screen.getByTestId("btn-cancel-webhook"));
    expect(screen.queryByTestId("webhook-dialog")).toBeNull();
  });

  it("revoke calls mutate with keyId", () => {
    const revokeMutate = vi.fn();
    vi.mocked(hooks.useRevokeApiKey).mockReturnValue({ mutate: revokeMutate, isPending: false } as any);
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId(`btn-revoke-${mockKey1.id}`));
    expect(revokeMutate).toHaveBeenCalledWith(
      expect.objectContaining({ keyId: mockKey1.id })
    );
  });

  it("delete webhook calls mutate", () => {
    const deleteMutate = vi.fn();
    vi.mocked(hooks.useDeleteWebhook).mockReturnValue({ mutate: deleteMutate, isPending: false } as any);
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId(`btn-delete-webhook-${mockWebhook1.id}`));
    expect(deleteMutate).toHaveBeenCalledWith(
      expect.objectContaining({ webhookId: mockWebhook1.id })
    );
  });

  it("edit webhook opens webhook dialog", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId(`btn-edit-webhook-${mockWebhook1.id}`));
    expect(screen.getByTestId("webhook-dialog")).not.toBeNull();
  });

  it("edit webhook prefills form with webhook data", () => {
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId(`btn-edit-webhook-${mockWebhook1.id}`));
    const nameInput = screen.getByTestId("input-webhook-name") as HTMLInputElement;
    expect(nameInput.value).toBe(mockWebhook1.name);
  });
});

// ── 8. Loading states ─────────────────────────────────────────────────────────

describe("Loading states", () => {
  afterEach(() => {
    vi.mocked(hooks.useApiKeys).mockReturnValue(_defaultApiKeysMock() as any);
    vi.mocked(hooks.useWebhooks).mockReturnValue(_defaultWebhooksMock() as any);
  });

  it("shows api-keys loading spinner", () => {
    vi.mocked(hooks.useApiKeys).mockReturnValue({ data: undefined, isLoading: true } as any);
    render(<IntegrationCenter workspaceId={WS_ID} />);
    expect(screen.getByTestId("api-keys-loading")).not.toBeNull();
  });

  it("shows webhooks loading spinner", () => {
    vi.mocked(hooks.useWebhooks).mockReturnValue({ data: undefined, isLoading: true } as any);
    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    expect(screen.getByTestId("webhooks-loading")).not.toBeNull();
  });
});

// ── 9. Secret reveal flow ─────────────────────────────────────────────────────

describe("Secret reveal flow", () => {
  it("secret reveal shows after successful key creation", () => {
    const createdKey = { ...mockKey1, plain_key: "cm_abc123" + "x".repeat(59) };
    let successCb: ((res: any) => void) | undefined;
    vi.mocked(hooks.useCreateApiKey).mockReturnValue({
      mutate: vi.fn((_body: unknown, opts: any) => { successCb = opts?.onSuccess; }),
      isPending: false,
    } as any);

    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("btn-add-api-key"));
    fireEvent.change(screen.getByTestId("input-key-name"), { target: { value: "K" } });
    fireEvent.submit(screen.getByTestId("create-api-key-form"));
    act(() => successCb?.({ data: createdKey }));

    expect(screen.getByTestId("secret-reveal-dialog")).not.toBeNull();
    expect(screen.getByTestId("secret-value").textContent).toContain("cm_abc123");
  });

  it("secret reveal shows after successful webhook creation", () => {
    const createdHook = { ...mockWebhook1, secret: "s3cr3t" + "x".repeat(58) };
    let successCb: ((res: any) => void) | undefined;
    vi.mocked(hooks.useCreateWebhook).mockReturnValue({
      mutate: vi.fn((_body: unknown, opts: any) => { successCb = opts?.onSuccess; }),
      isPending: false,
    } as any);

    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("tab-webhooks"));
    fireEvent.click(screen.getByTestId("btn-add-webhook"));
    fireEvent.change(screen.getByTestId("input-webhook-name"), { target: { value: "H" } });
    fireEvent.change(screen.getByTestId("input-webhook-url"), { target: { value: "https://x.com" } });
    fireEvent.submit(screen.getByTestId("webhook-form"));
    act(() => successCb?.({ data: createdHook }));

    expect(screen.getByTestId("secret-reveal-dialog")).not.toBeNull();
  });

  it("closing secret reveal hides it", () => {
    const createdKey = { ...mockKey1, plain_key: "cm_abc123" + "x".repeat(59) };
    let successCb: ((res: any) => void) | undefined;
    vi.mocked(hooks.useCreateApiKey).mockReturnValue({
      mutate: vi.fn((_body: unknown, opts: any) => { successCb = opts?.onSuccess; }),
      isPending: false,
    } as any);

    render(<IntegrationCenter workspaceId={WS_ID} />);
    fireEvent.click(screen.getByTestId("btn-add-api-key"));
    fireEvent.change(screen.getByTestId("input-key-name"), { target: { value: "K" } });
    fireEvent.submit(screen.getByTestId("create-api-key-form"));
    act(() => successCb?.({ data: createdKey }));
    fireEvent.click(screen.getByTestId("btn-close-secret"));
    expect(screen.queryByTestId("secret-reveal-dialog")).toBeNull();
  });
});
