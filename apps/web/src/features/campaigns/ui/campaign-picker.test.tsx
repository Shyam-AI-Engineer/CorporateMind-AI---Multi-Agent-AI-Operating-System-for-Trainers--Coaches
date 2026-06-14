import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { Campaign } from "@/features/campaigns/types";

// mockPush is captured in the factory closure so individual tests can spy on it.
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Provide a mix of draft and non-draft campaigns to verify filtering.
const MOCK_CAMPAIGNS: Campaign[] = [
  {
    id: "camp-draft",
    workspace_id: "ws-1",
    name: "Q2 Outreach",
    channel: "email",
    status: "draft",
    recipient_count: 0,
    scheduled_at: null,
    started_at: null,
    completed_at: null,
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "camp-running",
    workspace_id: "ws-1",
    name: "Running Campaign",
    channel: "email",
    status: "running",
    recipient_count: 50,
    scheduled_at: null,
    started_at: "2024-01-10T00:00:00Z",
    completed_at: null,
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "camp-locked",
    workspace_id: "ws-1",
    name: "Locked Campaign",
    channel: "email",
    status: "locked",
    recipient_count: 10,
    scheduled_at: null,
    started_at: null,
    completed_at: null,
    created_at: "2024-01-01T00:00:00Z",
  },
];

vi.mock("@/features/campaigns/api/use-campaigns", () => ({
  useCampaigns: () => ({
    data: {
      items: MOCK_CAMPAIGNS,
      total: MOCK_CAMPAIGNS.length,
      limit: 50,
      offset: 0,
    },
    isLoading: false,
  }),
}));

// Import after mocks are registered.
const { CampaignPicker } = await import("./campaign-picker");

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("CampaignPicker", () => {
  beforeEach(() => {
    mockPush.mockClear();
  });

  it("renders only draft campaigns as selectable options", () => {
    render(
      <CampaignPicker workspaceId="ws-1" value={null} onChange={vi.fn()} />,
    );
    expect(screen.queryByText("Q2 Outreach")).not.toBeNull();
    expect(screen.queryByText("Running Campaign")).toBeNull();
    expect(screen.queryByText("Locked Campaign")).toBeNull();
  });

  it("calls onChange with the selected campaign id", () => {
    const onChange = vi.fn();
    render(
      <CampaignPicker workspaceId="ws-1" value={null} onChange={onChange} />,
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "camp-draft" },
    });
    expect(onChange).toHaveBeenCalledWith("camp-draft");
  });

  it("does not call onChange when the create option is selected", () => {
    const onChange = vi.fn();
    render(
      <CampaignPicker workspaceId="ws-1" value={null} onChange={onChange} />,
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "__create__" },
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("navigates to /campaigns?create=1 when the create option is selected", () => {
    render(
      <CampaignPicker workspaceId="ws-1" value={null} onChange={vi.fn()} />,
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "__create__" },
    });
    expect(mockPush).toHaveBeenCalledWith("/campaigns?create=1");
  });

  it("shows the create option at all times", () => {
    render(
      <CampaignPicker workspaceId="ws-1" value={null} onChange={vi.fn()} />,
    );
    expect(screen.queryByText("＋ Create new campaign")).not.toBeNull();
  });
});
