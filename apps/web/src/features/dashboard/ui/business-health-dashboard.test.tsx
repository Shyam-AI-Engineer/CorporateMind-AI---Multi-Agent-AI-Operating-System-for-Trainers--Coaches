import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type {
  BusinessHealthOut,
  BusinessSummaryOut,
  OperationalAlertsOut,
} from "@/features/dashboard/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-test-1" }),
}));

const mockUseBusinessHealth = vi.fn();
const mockUseOperationalAlerts = vi.fn();
const mockUseBusinessSummary = vi.fn();

vi.mock("@/features/dashboard/api/use-dashboard", () => ({
  useBusinessHealth: (...args: unknown[]) => mockUseBusinessHealth(...args),
  useOperationalAlerts: (...args: unknown[]) => mockUseOperationalAlerts(...args),
  useBusinessSummary: (...args: unknown[]) => mockUseBusinessSummary(...args),
}));

// Recharts doesn't work in jsdom — stub to avoid SVG errors
vi.mock("recharts", () => ({
  RadialBarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-radial">{children}</div>
  ),
  RadialBar: () => null,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-bar">{children}</div>
  ),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

// ── Data builders ─────────────────────────────────────────────────────────────

function makeHealth(overrides: Partial<BusinessHealthOut> = {}): BusinessHealthOut {
  return {
    generated_at: "2026-06-27T12:00:00Z",
    overall_score: 75.0,
    pipeline_score: 80.0,
    revenue_score: 70.0,
    campaign_score: 78.0,
    recommendation_score: 72.0,
    communication_score: 76.0,
    components: [
      { name: "Pipeline", score: 80.0, weight: 0.20 },
      { name: "Revenue Conversion", score: 70.0, weight: 0.25 },
      { name: "Campaign Delivery", score: 78.0, weight: 0.15 },
      { name: "Recommendation Adoption", score: 72.0, weight: 0.20 },
      { name: "Communication", score: 76.0, weight: 0.20 },
    ],
    top_alerts: [],
    top_strengths: ["Pipeline", "Campaign Delivery"],
    areas_needing_attention: [],
    health_trend: "stable",
    ...overrides,
  };
}

function makeAlerts(
  alerts: OperationalAlertsOut["alerts"] = [],
): OperationalAlertsOut {
  return { alerts, total: alerts.length };
}

function makeSummary(overrides: Partial<BusinessSummaryOut> = {}): BusinessSummaryOut {
  return {
    generated_at: "2026-06-27T12:00:00Z",
    lines: ["Business health is good at 75/100.", "Pipeline performance is strong."],
    overall_assessment: "good",
    ...overrides,
  };
}

function makeAlert(
  priority: "critical" | "warning" | "info" = "warning",
  title = "Low reply rate",
): OperationalAlertsOut["alerts"][number] {
  return {
    priority,
    category: "pipeline",
    title,
    description: "Reply rate is below target.",
    recommended_action: "Review outreach copy.",
    created_at: "2026-06-27T12:00:00Z",
  };
}

function setAllSuccess(
  health: BusinessHealthOut = makeHealth(),
  alerts: OperationalAlertsOut = makeAlerts(),
  summary: BusinessSummaryOut = makeSummary(),
) {
  mockUseBusinessHealth.mockReturnValue({ data: health, isLoading: false, isError: false });
  mockUseOperationalAlerts.mockReturnValue({ data: alerts, isLoading: false, isError: false });
  mockUseBusinessSummary.mockReturnValue({ data: summary, isLoading: false, isError: false });
}

function setAllLoading() {
  const loading = { data: undefined, isLoading: true, isError: false };
  mockUseBusinessHealth.mockReturnValue(loading);
  mockUseOperationalAlerts.mockReturnValue(loading);
  mockUseBusinessSummary.mockReturnValue(loading);
}

function setAllError() {
  const errored = { data: undefined, isLoading: false, isError: true };
  mockUseBusinessHealth.mockReturnValue(errored);
  mockUseOperationalAlerts.mockReturnValue(errored);
  mockUseBusinessSummary.mockReturnValue(errored);
}

// ── Import component ──────────────────────────────────────────────────────────

import { BusinessHealthDashboard } from "./business-health-dashboard";

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BusinessHealthDashboard — loading state", () => {
  it("renders skeleton when loading", () => {
    setAllLoading();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("health-skeleton")).toBeTruthy();
  });

  it("does not render main dashboard while loading", () => {
    setAllLoading();
    render(<BusinessHealthDashboard />);
    expect(screen.queryByTestId("business-health-dashboard")).toBeNull();
  });
});

describe("BusinessHealthDashboard — error state", () => {
  it("renders error element when any query fails", () => {
    setAllError();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("health-error")).toBeTruthy();
  });

  it("shows error message text", () => {
    setAllError();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("health-error").textContent).toContain("Failed to load");
  });

  it("does not render main dashboard on error", () => {
    setAllError();
    render(<BusinessHealthDashboard />);
    expect(screen.queryByTestId("business-health-dashboard")).toBeNull();
  });
});

describe("BusinessHealthDashboard — success state root", () => {
  it("renders main panel with correct test id", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("business-health-dashboard")).toBeTruthy();
  });

  it("passes workspace id to hooks", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(mockUseBusinessHealth).toHaveBeenCalledWith("ws-test-1");
    expect(mockUseOperationalAlerts).toHaveBeenCalledWith("ws-test-1");
    expect(mockUseBusinessSummary).toHaveBeenCalledWith("ws-test-1");
  });
});

// Section 1 — Health Score Gauge

describe("BusinessHealthDashboard — Section 1: Health Score Gauge", () => {
  it("renders health score gauge section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("health-score-gauge")).toBeTruthy();
  });

  it("displays overall score value", () => {
    setAllSuccess(makeHealth({ overall_score: 82.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("gauge-score").textContent).toContain("82");
  });

  it("renders recharts gauge chart", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("gauge-chart")).toBeTruthy();
  });

  it("score of 0 displays 0", () => {
    setAllSuccess(makeHealth({ overall_score: 0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("gauge-score").textContent).toContain("0");
  });

  it("score of 100 displays 100", () => {
    setAllSuccess(makeHealth({ overall_score: 100 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("gauge-score").textContent).toContain("100");
  });
});

// Section 2 — Health Breakdown

describe("BusinessHealthDashboard — Section 2: Health Breakdown", () => {
  it("renders breakdown section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("health-breakdown")).toBeTruthy();
  });

  it("renders all 5 score cards", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-pipeline")).toBeTruthy();
    expect(screen.getByTestId("score-revenue")).toBeTruthy();
    expect(screen.getByTestId("score-campaign")).toBeTruthy();
    expect(screen.getByTestId("score-recommendation")).toBeTruthy();
    expect(screen.getByTestId("score-communication")).toBeTruthy();
  });

  it("pipeline score card shows correct value", () => {
    setAllSuccess(makeHealth({ pipeline_score: 88.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-pipeline").textContent).toContain("88");
  });

  it("revenue score card shows correct value", () => {
    setAllSuccess(makeHealth({ revenue_score: 65.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-revenue").textContent).toContain("65");
  });

  it("campaign score card shows correct value", () => {
    setAllSuccess(makeHealth({ campaign_score: 91.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-campaign").textContent).toContain("91");
  });

  it("recommendation score card shows correct value", () => {
    setAllSuccess(makeHealth({ recommendation_score: 50.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-recommendation").textContent).toContain("50");
  });

  it("communication score card shows correct value", () => {
    setAllSuccess(makeHealth({ communication_score: 73.0 }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("score-communication").textContent).toContain("73");
  });

  it("renders bar chart", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("breakdown-chart")).toBeTruthy();
  });
});

// Section 3 — Operational Alerts

describe("BusinessHealthDashboard — Section 3: Operational Alerts", () => {
  it("renders alerts section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("alerts-section")).toBeTruthy();
  });

  it("shows no-alerts message when empty", () => {
    setAllSuccess(makeHealth(), makeAlerts([]));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("no-alerts")).toBeTruthy();
  });

  it("renders alert items when present", () => {
    const alerts = [makeAlert("critical", "Critically low reply rate")];
    setAllSuccess(makeHealth(), makeAlerts(alerts));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("alert-item-0")).toBeTruthy();
  });

  it("renders multiple alert items", () => {
    const alerts = [
      makeAlert("critical", "Critical 1"),
      makeAlert("warning", "Warning 1"),
      makeAlert("info", "Info 1"),
    ];
    setAllSuccess(makeHealth(), makeAlerts(alerts));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("alert-item-0")).toBeTruthy();
    expect(screen.getByTestId("alert-item-1")).toBeTruthy();
    expect(screen.getByTestId("alert-item-2")).toBeTruthy();
  });

  it("shows priority badge for each alert", () => {
    const alerts = [makeAlert("critical", "Critical alert")];
    setAllSuccess(makeHealth(), makeAlerts(alerts));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("alert-priority-0").textContent?.toLowerCase()).toContain("critical");
  });

  it("shows alert title text", () => {
    const alerts = [makeAlert("warning", "Low reply rate detected")];
    setAllSuccess(makeHealth(), makeAlerts(alerts));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("alert-item-0").textContent).toContain("Low reply rate detected");
  });
});

// Section 4 — Business Trend

describe("BusinessHealthDashboard — Section 4: Business Trend", () => {
  it("renders trend section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-section")).toBeTruthy();
  });

  it("shows 'stable' trend value", () => {
    setAllSuccess(makeHealth({ health_trend: "stable" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-value").textContent?.toLowerCase()).toContain("stable");
  });

  it("shows 'improving' trend value", () => {
    setAllSuccess(makeHealth({ health_trend: "improving" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-value").textContent?.toLowerCase()).toContain("improving");
  });

  it("shows 'declining' trend value", () => {
    setAllSuccess(makeHealth({ health_trend: "declining" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-value").textContent?.toLowerCase()).toContain("declining");
  });

  it("improving trend shows upward label text", () => {
    setAllSuccess(makeHealth({ health_trend: "improving" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-label").textContent).toContain("trending up");
  });

  it("declining trend shows downward label text", () => {
    setAllSuccess(makeHealth({ health_trend: "declining" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-label").textContent).toContain("trending down");
  });

  it("stable trend shows stable label text", () => {
    setAllSuccess(makeHealth({ health_trend: "stable" }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("trend-label").textContent).toContain("stable");
  });
});

// Section 5 — Top Strengths

describe("BusinessHealthDashboard — Section 5: Top Strengths", () => {
  it("renders strengths section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("strengths-section")).toBeTruthy();
  });

  it("shows empty message when no strengths", () => {
    setAllSuccess(makeHealth({ top_strengths: [] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("strengths-empty")).toBeTruthy();
  });

  it("renders strength items", () => {
    setAllSuccess(makeHealth({ top_strengths: ["Pipeline", "Revenue Conversion"] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("strength-item-0")).toBeTruthy();
    expect(screen.getByTestId("strength-item-1")).toBeTruthy();
  });

  it("strength item shows correct text", () => {
    setAllSuccess(makeHealth({ top_strengths: ["Communication"] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("strength-item-0").textContent).toContain("Communication");
  });
});

// Section 6 — Areas Needing Attention

describe("BusinessHealthDashboard — Section 6: Areas Needing Attention", () => {
  it("renders attention section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("attention-section")).toBeTruthy();
  });

  it("shows empty message when no areas", () => {
    setAllSuccess(makeHealth({ areas_needing_attention: [] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("attention-empty")).toBeTruthy();
  });

  it("renders attention items", () => {
    setAllSuccess(makeHealth({ areas_needing_attention: ["Campaign Delivery", "Pipeline"] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("attention-item-0")).toBeTruthy();
    expect(screen.getByTestId("attention-item-1")).toBeTruthy();
  });

  it("attention item shows correct text", () => {
    setAllSuccess(makeHealth({ areas_needing_attention: ["Revenue Conversion"] }));
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("attention-item-0").textContent).toContain("Revenue Conversion");
  });
});

// Section 7 — Executive Summary

describe("BusinessHealthDashboard — Section 7: Executive Summary", () => {
  it("renders summary section", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("summary-section")).toBeTruthy();
  });

  it("renders summary lines container", () => {
    setAllSuccess();
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("summary-lines")).toBeTruthy();
  });

  it("renders correct number of summary lines", () => {
    const summary = makeSummary({ lines: ["Line 1", "Line 2", "Line 3"] });
    setAllSuccess(makeHealth(), makeAlerts(), summary);
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("summary-line-0").textContent).toBe("Line 1");
    expect(screen.getByTestId("summary-line-1").textContent).toBe("Line 2");
    expect(screen.getByTestId("summary-line-2").textContent).toBe("Line 3");
  });

  it("shows empty state when no lines", () => {
    const summary = makeSummary({ lines: [] });
    setAllSuccess(makeHealth(), makeAlerts(), summary);
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("summary-empty")).toBeTruthy();
  });

  it("shows first summary line text", () => {
    const summary = makeSummary({ lines: ["Business health is excellent at 85/100."] });
    setAllSuccess(makeHealth(), makeAlerts(), summary);
    render(<BusinessHealthDashboard />);
    expect(screen.getByTestId("summary-line-0").textContent).toContain("excellent");
  });
});
