import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { AnalyticsChannelSummary } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useWhatsAppAnalytics: vi.fn(),
}));

import { useWhatsAppAnalytics } from "@/features/analytics/api/use-analytics";
const mockHook = vi.mocked(useWhatsAppAnalytics);

const { WhatsAppMetricsCard } = await import("./whatsapp-metrics-card");

// ── Helpers ────────────────────────────────────────────────────────────────────

const emptyData: AnalyticsChannelSummary = {
  channel: "whatsapp",
  period_days: 30,
  sent: 0,
  delivered: 0,
  opened: 0,
  failed: 0,
  compliance_blocks: 0,
  delivery_rate: 0,
  read_rate: 0,
};

function mockLoaded(overrides: Partial<AnalyticsChannelSummary> = {}) {
  mockHook.mockReturnValue({
    data: { ...emptyData, ...overrides },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useWhatsAppAnalytics>);
}

function mockLoading() {
  mockHook.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useWhatsAppAnalytics>);
}

function mockError(refetch = vi.fn()) {
  mockHook.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
    refetch,
  } as unknown as ReturnType<typeof useWhatsAppAnalytics>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("WhatsAppMetricsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton cards while loading", () => {
    mockLoading();
    const { container } = render(<WhatsAppMetricsCard />);
    const skeletons = container.querySelectorAll(".h-8");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state with retry button", () => {
    const refetch = vi.fn();
    mockError(refetch);
    render(<WhatsAppMetricsCard />);
    expect(screen.getByText(/failed to load whatsapp analytics/i)).not.toBeNull();
    const retryBtn = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryBtn);
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("renders section heading with days", () => {
    mockLoaded();
    render(<WhatsAppMetricsCard days={30} />);
    expect(screen.getByText("WhatsApp Delivery (30d)")).not.toBeNull();
  });

  it("renders all five KPI labels", () => {
    mockLoaded();
    render(<WhatsAppMetricsCard />);
    expect(screen.getByText("Sent")).not.toBeNull();
    expect(screen.getByText("Delivery Rate")).not.toBeNull();
    expect(screen.getByText("Read Rate")).not.toBeNull();
    expect(screen.getByText("Failed Sends")).not.toBeNull();
    expect(screen.getByText("Compliance Blocks")).not.toBeNull();
  });

  it("formats delivery rate as percentage", () => {
    mockLoaded({ delivery_rate: 0.856 });
    render(<WhatsAppMetricsCard />);
    expect(screen.getByText("85.6%")).not.toBeNull();
  });

  it("formats read rate as percentage", () => {
    mockLoaded({ read_rate: 0.4 });
    render(<WhatsAppMetricsCard />);
    expect(screen.getByText("40.0%")).not.toBeNull();
  });

  it("formats sent count with locale separators", () => {
    mockLoaded({ sent: 12500 });
    render(<WhatsAppMetricsCard />);
    // toLocaleString may produce "12,500" or "12 500" depending on locale
    expect(screen.getByText(/12.?500/)).not.toBeNull();
  });

  it("shows dash when data is not yet loaded (empty state placeholder)", () => {
    // Edge case: data could be undefined without isLoading (stale refetch)
    mockHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useWhatsAppAnalytics>);

    render(<WhatsAppMetricsCard />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("renders zero rates as 0.0% not NaN", () => {
    mockLoaded({ sent: 0, delivered: 0, opened: 0 });
    render(<WhatsAppMetricsCard />);
    const percentages = screen.getAllByText("0.0%");
    expect(percentages.length).toBeGreaterThanOrEqual(2);
  });
});
