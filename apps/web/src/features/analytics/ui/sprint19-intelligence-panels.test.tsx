import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type {
  CampaignROIListOut,
  IndustryPerformanceOut,
  PricingCalibrationOut,
  TopicPerformanceOut,
} from "@/features/analytics/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  useCampaignROI: vi.fn(),
  useTopicPerformance: vi.fn(),
  useIndustryPerformance: vi.fn(),
  usePricingCalibration: vi.fn(),
}));

import {
  useCampaignROI,
  usePricingCalibration,
  useTopicPerformance,
  useIndustryPerformance,
} from "@/features/analytics/api/use-analytics";

const mockCampaignROI = vi.mocked(useCampaignROI);
const mockTopics = vi.mocked(useTopicPerformance);
const mockIndustries = vi.mocked(useIndustryPerformance);
const mockPricing = vi.mocked(usePricingCalibration);

const WS = "ws-abc";

// ── CampaignROIPanel ──────────────────────────────────────────────────────────

const { CampaignROIPanel } = await import("./campaign-roi-panel");

describe("CampaignROIPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows skeleton while loading", () => {
    mockCampaignROI.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useCampaignROI>);
    const { container } = render(<CampaignROIPanel workspaceId={WS} />);
    expect(container.querySelector(".h-10")).not.toBeNull();
  });

  it("shows empty state when no items", () => {
    const empty: CampaignROIListOut = { items: [], total: 0, attribution_model: "all_touch" };
    mockCampaignROI.mockReturnValue({ data: empty, isLoading: false, isError: false } as ReturnType<typeof useCampaignROI>);
    render(<CampaignROIPanel workspaceId={WS} />);
    expect(screen.getByText(/no campaign data/i)).not.toBeNull();
  });

  it("renders campaign row with revenue", () => {
    const item = {
      campaign_id: "c1",
      campaign_name: "Q3 Outreach",
      channel: "whatsapp",
      campaign_status: "completed",
      recipients_count: 100,
      messages_sent: 100,
      messages_delivered: 90,
      replies_received: 20,
      leads_created: 5,
      proposals_sent: 8,
      proposals_accepted: 3,
      win_rate: 0.375,
      closed_revenue_inr: 150000,
      avg_deal_size_inr: 50000,
      avg_days_to_accept: 7.5,
      last_refreshed_at: "2026-06-22T00:00:00Z",
      sample_size: 8,
      low_confidence: false,
    };
    const roi: CampaignROIListOut = { items: [item], total: 1, attribution_model: "all_touch" };
    mockCampaignROI.mockReturnValue({ data: roi, isLoading: false, isError: false } as ReturnType<typeof useCampaignROI>);
    render(<CampaignROIPanel workspaceId={WS} />);
    expect(screen.getByText("Q3 Outreach")).not.toBeNull();
    expect(screen.getByText("37.5%")).not.toBeNull();
    expect(screen.getByText("7.5d")).not.toBeNull();
  });

  it("shows low confidence badge when sample_size < 5", () => {
    const item = {
      campaign_id: "c2",
      campaign_name: "Small Campaign",
      channel: "email",
      campaign_status: "active",
      recipients_count: 10,
      messages_sent: 10,
      messages_delivered: 8,
      replies_received: 2,
      leads_created: 1,
      proposals_sent: 3,
      proposals_accepted: 1,
      win_rate: 0.333,
      closed_revenue_inr: 50000,
      avg_deal_size_inr: 50000,
      avg_days_to_accept: null,
      last_refreshed_at: "2026-06-22T00:00:00Z",
      sample_size: 3,
      low_confidence: true,
    };
    const roi: CampaignROIListOut = { items: [item], total: 1, attribution_model: "all_touch" };
    mockCampaignROI.mockReturnValue({ data: roi, isLoading: false, isError: false } as ReturnType<typeof useCampaignROI>);
    render(<CampaignROIPanel workspaceId={WS} />);
    expect(screen.getByText("Low data")).not.toBeNull();
    // avg_days shown as dash when null (multiple dashes may appear for other null fields)
    expect(screen.getAllByText("—")[0]).not.toBeNull();
  });

  it("shows error state on failure", () => {
    mockCampaignROI.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useCampaignROI>);
    render(<CampaignROIPanel workspaceId={WS} />);
    expect(screen.getByText(/failed to load campaign roi/i)).not.toBeNull();
  });
});

// ── TopTopicsPanel ────────────────────────────────────────────────────────────

const { TopTopicsPanel } = await import("./top-topics-panel");

describe("TopTopicsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows skeleton while loading", () => {
    mockTopics.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useTopicPerformance>);
    const { container } = render(<TopTopicsPanel workspaceId={WS} />);
    expect(container.querySelector(".h-5")).not.toBeNull();
  });

  it("renders topic bar with win rate", () => {
    const data: TopicPerformanceOut = {
      items: [
        { topic: "Leadership", proposals_sent: 12, proposals_accepted: 5, win_rate: 0.417, closed_revenue_inr: 250000 },
        { topic: "Sales", proposals_sent: 8, proposals_accepted: 2, win_rate: 0.25, closed_revenue_inr: 100000 },
      ],
      workspace_id: WS,
      generated_at: "2026-06-22T00:00:00Z",
      sample_size: 20,
      low_confidence: false,
    };
    mockTopics.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useTopicPerformance>);
    render(<TopTopicsPanel workspaceId={WS} />);
    expect(screen.getByText("Leadership")).not.toBeNull();
    expect(screen.getByText("Sales")).not.toBeNull();
    expect(screen.getByText(/42%/)).not.toBeNull();
  });

  it("shows low confidence warning when sample_size < 5", () => {
    const data: TopicPerformanceOut = {
      items: [{ topic: "Wellness", proposals_sent: 2, proposals_accepted: 1, win_rate: 0.5, closed_revenue_inr: 40000 }],
      workspace_id: WS,
      generated_at: "2026-06-22T00:00:00Z",
      sample_size: 2,
      low_confidence: true,
    };
    mockTopics.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useTopicPerformance>);
    render(<TopTopicsPanel workspaceId={WS} />);
    expect(screen.getByText(/low data/i)).not.toBeNull();
  });

  it("shows empty state when no topics", () => {
    const data: TopicPerformanceOut = { items: [], workspace_id: WS, generated_at: "2026-06-22T00:00:00Z", sample_size: 0, low_confidence: true };
    mockTopics.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useTopicPerformance>);
    render(<TopTopicsPanel workspaceId={WS} />);
    expect(screen.getByText(/no topic data/i)).not.toBeNull();
  });
});

// ── TopIndustriesPanel ────────────────────────────────────────────────────────

const { TopIndustriesPanel } = await import("./top-industries-panel");

describe("TopIndustriesPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders industry rows", () => {
    const data: IndustryPerformanceOut = {
      items: [
        { industry: "IT Services", proposals_sent: 15, proposals_accepted: 6, win_rate: 0.4, closed_revenue_inr: 300000 },
        { industry: "FMCG", proposals_sent: 10, proposals_accepted: 3, win_rate: 0.3, closed_revenue_inr: 150000 },
      ],
      workspace_id: WS,
      generated_at: "2026-06-22T00:00:00Z",
      unknown_count: 0,
      sample_size: 25,
      low_confidence: false,
    };
    mockIndustries.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useIndustryPerformance>);
    render(<TopIndustriesPanel workspaceId={WS} />);
    expect(screen.getByText("IT Services")).not.toBeNull();
    expect(screen.getByText("FMCG")).not.toBeNull();
  });

  it("shows unknown count note when > 0", () => {
    const data: IndustryPerformanceOut = {
      items: [{ industry: "Unknown", proposals_sent: 5, proposals_accepted: 1, win_rate: 0.2, closed_revenue_inr: 50000 }],
      workspace_id: WS,
      generated_at: "2026-06-22T00:00:00Z",
      unknown_count: 5,
      sample_size: 5,
      low_confidence: true,
    };
    mockIndustries.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof useIndustryPerformance>);
    render(<TopIndustriesPanel workspaceId={WS} />);
    expect(screen.getByText(/5 proposal.*no industry data/i)).not.toBeNull();
  });

  it("shows error state on failure", () => {
    mockIndustries.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useIndustryPerformance>);
    render(<TopIndustriesPanel workspaceId={WS} />);
    expect(screen.getByText(/failed to load industry/i)).not.toBeNull();
  });
});

// ── PricingCalibrationCard ────────────────────────────────────────────────────

const { PricingCalibrationCard } = await import("./pricing-calibration-card");

describe("PricingCalibrationCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows skeleton while loading", () => {
    mockPricing.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof usePricingCalibration>);
    const { container } = render(<PricingCalibrationCard workspaceId={WS} />);
    expect(container.querySelector(".h-5")).not.toBeNull();
  });

  it("renders stated range and actual stats", () => {
    const data: PricingCalibrationOut = {
      workspace_id: WS,
      stated_min_inr: 50000,
      stated_max_inr: 200000,
      actual_min_inr: 60000,
      actual_max_inr: 180000,
      actual_avg_inr: 120000,
      actual_median_inr: 110000,
      avg_days_to_accept: 9.5,
      sample_size: 7,
      low_confidence: false,
      generated_at: "2026-06-22T00:00:00Z",
    };
    mockPricing.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof usePricingCalibration>);
    render(<PricingCalibrationCard workspaceId={WS} />);
    expect(screen.getByText(/9.5 days/)).not.toBeNull();
    expect(screen.getByText("Avg days to accept")).not.toBeNull();
    expect(screen.getByText(/stated range/i)).not.toBeNull();
    expect(screen.getByText(/actual accepted values/i)).not.toBeNull();
  });

  it("shows low confidence badge when sample_size < 5", () => {
    const data: PricingCalibrationOut = {
      workspace_id: WS,
      stated_min_inr: null,
      stated_max_inr: null,
      actual_min_inr: 80000,
      actual_max_inr: 80000,
      actual_avg_inr: 80000,
      actual_median_inr: 80000,
      avg_days_to_accept: null,
      sample_size: 1,
      low_confidence: true,
      generated_at: "2026-06-22T00:00:00Z",
    };
    mockPricing.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof usePricingCalibration>);
    render(<PricingCalibrationCard workspaceId={WS} />);
    expect(screen.getByText(/low data/i)).not.toBeNull();
  });

  it("shows dash for null avg_days_to_accept", () => {
    const data: PricingCalibrationOut = {
      workspace_id: WS,
      stated_min_inr: 50000,
      stated_max_inr: 150000,
      actual_min_inr: null,
      actual_max_inr: null,
      actual_avg_inr: null,
      actual_median_inr: null,
      avg_days_to_accept: null,
      sample_size: 0,
      low_confidence: true,
      generated_at: "2026-06-22T00:00:00Z",
    };
    mockPricing.mockReturnValue({ data, isLoading: false, isError: false } as ReturnType<typeof usePricingCalibration>);
    render(<PricingCalibrationCard workspaceId={WS} />);
    // The "—" dash should appear for the null avg_days_to_accept value
    expect(screen.getAllByText("—")[0]).not.toBeNull();
  });
});
