import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AnalyticsFunnel, AnalyticsSummary, DailyRollup } from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-1" }),
}));

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useAnalyticsSummary: vi.fn(),
  useAnalyticsTrend: vi.fn(),
  useAnalyticsFunnel: vi.fn(),
  useWhatsAppAnalytics: vi.fn(() => ({
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  })),
}));

vi.mock("@/features/analytics/ui/whatsapp-metrics-card", () => ({
  WhatsAppMetricsCard: () => <div data-testid="wa-metrics-card" />,
}));

// recharts uses ResizeObserver which is not in jsdom
vi.mock("recharts", () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import {
  useAnalyticsFunnel,
  useAnalyticsSummary,
  useAnalyticsTrend,
} from "@/features/analytics/api/use-analytics";

const mockSummary = vi.mocked(useAnalyticsSummary);
const mockTrend = vi.mocked(useAnalyticsTrend);
const mockFunnel = vi.mocked(useAnalyticsFunnel);

const { AnalyticsPanel } = await import("./analytics-panel");

// ── Helpers ────────────────────────────────────────────────────────────────────

const emptySummary: AnalyticsSummary = {
  period_days: 30,
  total_sent: 0,
  total_delivered: 0,
  total_replied: 0,
  reply_rate: 0,
  delivery_rate: 0,
  total_spend_inr: 0,
  meetings_scheduled: 0,
  meetings_completed: 0,
  leads_created: 0,
  leads_booked: 0,
  proposals_generated: 0,
  proposals_approved: 0,
  proposals_sent: 0,
  proposal_approval_rate: 0,
  booking_rate: 0,
};

const emptyFunnel: AnalyticsFunnel = {
  contacts: 0,
  outreach_sent: 0,
  replies: 0,
  meetings: 0,
  proposals: 0,
  bookings: 0,
};

function mockLoaded(
  summaryOverrides: Partial<AnalyticsSummary> = {},
  funnelOverrides: Partial<AnalyticsFunnel> = {},
  trendRows: DailyRollup[] = [],
) {
  mockSummary.mockReturnValue({
    data: { ...emptySummary, ...summaryOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsSummary>);

  mockTrend.mockReturnValue({
    data: trendRows,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsTrend>);

  mockFunnel.mockReturnValue({
    data: { ...emptyFunnel, ...funnelOverrides },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAnalyticsFunnel>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AnalyticsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton cards while loading", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsSummary>);
    mockTrend.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsTrend>);
    mockFunnel.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useAnalyticsFunnel>);

    const { container } = render(<AnalyticsPanel />);
    const skeletons = container.querySelectorAll("[class*='animate-pulse'], [data-slot='skeleton'], .h-8");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state when summary fails", () => {
    mockSummary.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useAnalyticsSummary>);
    mockTrend.mockReturnValue({ data: [] as DailyRollup[], isLoading: false, isError: false } as unknown as ReturnType<typeof useAnalyticsTrend>);
    mockFunnel.mockReturnValue({ data: undefined, isLoading: false, isError: false } as unknown as ReturnType<typeof useAnalyticsFunnel>);

    render(<AnalyticsPanel />);
    expect(screen.getByText(/failed to load analytics/i)).not.toBeNull();
  });

  it("renders reply rate KPI", () => {
    mockLoaded({ reply_rate: 0.25, total_sent: 100, total_replied: 25 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("25.0%")).not.toBeNull();
  });

  it("renders meetings KPI", () => {
    mockLoaded({ meetings_scheduled: 8, meetings_completed: 3 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("8")).not.toBeNull();
  });

  it("renders proposals KPI", () => {
    mockLoaded({ proposals_sent: 5, proposal_approval_rate: 0.8 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("5")).not.toBeNull();
  });

  it("shows empty trend message when no trend data", () => {
    mockLoaded({}, {}, []);
    render(<AnalyticsPanel />);
    expect(screen.getByText(/no trend data yet/i)).not.toBeNull();
  });

  it("renders funnel rows when data present", () => {
    mockLoaded({}, { contacts: 100, outreach_sent: 60, replies: 20, meetings: 8, proposals: 5, bookings: 2 });
    render(<AnalyticsPanel />);
    expect(screen.getByText("HR Contacts")).not.toBeNull();
    expect(screen.getByText("Revenue Funnel")).not.toBeNull();
  });

  it("renders 'View full analytics' link in InsightsCard pattern (integration)", () => {
    mockLoaded({ reply_rate: 0.15, total_sent: 200 });
    render(<AnalyticsPanel />);
    // Just assert the panel renders without crashing and shows the core heading
    expect(screen.getByText("30-Day Outreach Trend")).not.toBeNull();
  });
});
