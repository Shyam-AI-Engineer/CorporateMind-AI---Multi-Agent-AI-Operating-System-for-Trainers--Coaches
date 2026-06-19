import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { WorkspaceBookingWebhook } from "@/features/workspace/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockMutateAsync = vi.fn();

// WhatsAppSettingsCard uses useQuery — stub it out to avoid QueryClientProvider
vi.mock("@/features/whatsapp/ui/whatsapp-settings-card", () => ({
  WhatsAppSettingsCard: () => <div data-testid="whatsapp-settings-stub" />,
}));

vi.mock("@/features/workspace/api/use-workspace-settings", () => ({
  useBookingWebhook: vi.fn(),
  useRegenerateBookingSecret: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
    isError: false,
  }),
}));

import { useBookingWebhook } from "@/features/workspace/api/use-workspace-settings";
const mockUseBookingWebhook = vi.mocked(useBookingWebhook);

const { IntegrationsPanel } = await import("./integrations-panel");

// ── Helpers ────────────────────────────────────────────────────────────────────

function mockLoaded(overrides: Partial<WorkspaceBookingWebhook> = {}) {
  mockUseBookingWebhook.mockReturnValue({
    data: {
      workspace_id: "ws-1",
      webhook_url: "http://localhost:8000/api/v1/webhooks/booking/ws-1",
      has_secret: false,
      secret: null,
      ...overrides,
    } as WorkspaceBookingWebhook,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useBookingWebhook>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("IntegrationsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton while loading", () => {
    mockUseBookingWebhook.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useBookingWebhook>);

    const { container } = render(<IntegrationsPanel />);
    // Skeleton elements present, no webhook URL
    expect(screen.queryByText(/webhook url/i)).toBeNull();
    const skeletons = container.querySelectorAll("[data-slot='skeleton'], .animate-pulse, [class*='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state on fetch failure", () => {
    mockUseBookingWebhook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useBookingWebhook>);

    render(<IntegrationsPanel />);
    expect(screen.getByText(/failed to load/i)).not.toBeNull();
  });

  it("displays the webhook URL", () => {
    mockLoaded();
    render(<IntegrationsPanel />);
    expect(screen.getByText("http://localhost:8000/api/v1/webhooks/booking/ws-1")).not.toBeNull();
  });

  it("shows 'Generate secret' button when no secret configured", () => {
    mockLoaded({ has_secret: false, secret: null });
    render(<IntegrationsPanel />);
    expect(screen.getByRole("button", { name: /generate secret/i })).not.toBeNull();
  });

  it("shows 'Regenerate secret' button when secret exists", () => {
    mockLoaded({ has_secret: true, secret: "my-secret-value" });
    render(<IntegrationsPanel />);
    expect(screen.getByRole("button", { name: /regenerate secret/i })).not.toBeNull();
  });

  it("clicking regenerate once shows confirm state", () => {
    mockLoaded();
    render(<IntegrationsPanel />);
    fireEvent.click(screen.getByRole("button", { name: /generate secret/i }));
    expect(screen.getByRole("button", { name: /confirm/i })).not.toBeNull();
  });

  it("confirms and calls mutateAsync on second click", async () => {
    mockMutateAsync.mockResolvedValueOnce({
      workspace_id: "ws-1",
      webhook_url: "http://localhost:8000/api/v1/webhooks/booking/ws-1",
      has_secret: true,
      secret: "new-secret",
    });
    mockLoaded();
    render(<IntegrationsPanel />);

    // First click → confirm state
    fireEvent.click(screen.getByRole("button", { name: /generate secret/i }));
    // Second click → actual call
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledOnce());
  });

  it("cancel button during confirm resets to initial state", () => {
    mockLoaded();
    render(<IntegrationsPanel />);

    fireEvent.click(screen.getByRole("button", { name: /generate secret/i }));
    expect(screen.getByRole("button", { name: /cancel/i })).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    expect(screen.getByRole("button", { name: /generate secret/i })).not.toBeNull();
  });
});
