/**
 * Tests for executive-dashboard.tsx — Sprint 50
 * Pattern: no jest-dom; use .not.toBeNull() / .toBeNull() / .textContent.toContain()
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type {
  ExecutiveAlert,
  ExecutiveDashboard,
  ExecutiveKPIs,
  ExecutiveSummary,
  ExecutiveTrend,
} from "@/features/executive/types-executive";

// ── Mocks must be declared before await import ────────────────────────────────

vi.mock("@/features/executive/api/use-executive", () => ({
  useExecutiveDashboard: vi.fn(),
  useExecutiveAlerts: vi.fn(),
  useExecutiveTrends: vi.fn(),
  useExecutiveKPIs: vi.fn(),
}));

vi.mock("recharts", () => ({
  LineChart: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  Legend: () => null,
}));

const {
  KPICard,
  KPIGrid,
  HealthGauge,
  AlertCard,
  AlertsPanel,
  CustomerHealthSection,
  TrendCharts,
  ExecutiveDashboard,
} = await import("./executive-dashboard");

const {
  useExecutiveDashboard,
  useExecutiveAlerts,
  useExecutiveTrends,
} = await import("@/features/executive/api/use-executive");

const mockUseDashboard = vi.mocked(useExecutiveDashboard);
const mockUseAlerts = vi.mocked(useExecutiveAlerts);
const mockUseTrends = vi.mocked(useExecutiveTrends);

// ── Helpers ───────────────────────────────────────────────────────────────────

type QueryResult = { data?: unknown; isLoading: boolean; isError: boolean };

function idleQuery<T>(data: T): QueryResult {
  return { data: { data }, isLoading: false, isError: false };
}
function loadingQuery(): QueryResult {
  return { data: undefined, isLoading: true, isError: false };
}
function errorQuery(): QueryResult {
  return { data: undefined, isLoading: false, isError: true };
}

function makeKPIs(overrides: Partial<ExecutiveKPIs> = {}): ExecutiveKPIs {
  return {
    total_leads: 20,
    active_customers: 10,
    renewals_due: 3,
    training_completion_rate: 0.75,
    certificate_issuance_rate: 0.8,
    avg_feedback_rating: 4.2,
    customer_health_distribution: { healthy: 7, at_risk: 2, watch: 1 },
    workflow_completion_rate: 0.6,
    open_operations_tasks: 5,
    business_health_score: 72,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<ExecutiveSummary> = {}): ExecutiveSummary {
  return {
    total_leads: 20,
    active_customers: 10,
    renewals_due: 3,
    open_operations_tasks: 5,
    business_health_score: 72,
    ...overrides,
  };
}

function makeAlert(overrides: Partial<ExecutiveAlert> = {}): ExecutiveAlert {
  return {
    alert_type: "renewals_overdue",
    severity: "critical",
    title: "Renewals Overdue",
    description: "3 renewal(s) past due.",
    count: 3,
    affected_ids: ["id1", "id2"],
    ...overrides,
  };
}

function makeTrend(date: string = "2026-07-01"): ExecutiveTrend {
  return {
    date,
    leads_created: 2,
    customers_created: 1,
    training_completions: 3,
    renewals_processed: 0,
  };
}

function makeDashboard(overrides: Partial<ExecutiveDashboard> = {}): ExecutiveDashboard {
  return {
    summary: makeSummary(),
    kpis: makeKPIs(),
    alerts: [],
    trends_30d: [makeTrend()],
    workspace_id: "ws-1",
    generated_at: "2026-07-07T10:00:00+00:00",
    ...overrides,
  };
}

function setupDashboard(
  dashboard: ExecutiveDashboard | null = makeDashboard(),
  alerts: ExecutiveAlert[] = [],
  trends: ExecutiveTrend[] = [makeTrend()],
) {
  mockUseDashboard.mockReturnValue(
    dashboard ? idleQuery(dashboard) as ReturnType<typeof useExecutiveDashboard> : loadingQuery() as ReturnType<typeof useExecutiveDashboard>
  );
  mockUseAlerts.mockReturnValue(idleQuery(alerts) as ReturnType<typeof useExecutiveAlerts>);
  mockUseTrends.mockReturnValue(idleQuery(trends) as ReturnType<typeof useExecutiveTrends>);
}

// ══════════════════════════════════════════════════════════════════════════════
// describe KPICard
// ══════════════════════════════════════════════════════════════════════════════

describe("KPICard", () => {
  it("renders with the given testId", () => {
    render(<KPICard label="Leads" value={42} testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test")).not.toBeNull();
  });

  it("renders value testId", () => {
    render(<KPICard label="Leads" value={42} testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value")).not.toBeNull();
  });

  it("displays the value", () => {
    render(<KPICard label="Leads" value={42} testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value").textContent).toContain("42");
  });

  it("displays the label", () => {
    render(<KPICard label="Total Leads" value={10} testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test").textContent).toContain("Total Leads");
  });

  it("shows sub text when provided", () => {
    render(<KPICard label="Score" value={75} sub="out of 100" testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-sub")).not.toBeNull();
    expect(screen.getByTestId("kpi-test-sub").textContent).toContain("out of 100");
  });

  it("does not render sub testId when sub is absent", () => {
    render(<KPICard label="Score" value={75} testId="kpi-test" />);
    expect(screen.queryByTestId("kpi-test-sub")).toBeNull();
  });

  it("renders string value", () => {
    render(<KPICard label="Rate" value="75%" testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value").textContent).toContain("75%");
  });

  it("renders zero value", () => {
    render(<KPICard label="Leads" value={0} testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value").textContent).toContain("0");
  });

  it("renders em-dash value", () => {
    render(<KPICard label="Feedback" value="—" testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value").textContent).toContain("—");
  });

  it("renders star rating format", () => {
    render(<KPICard label="Feedback" value="★ 4.2" testId="kpi-test" />);
    expect(screen.getByTestId("kpi-test-value").textContent).toContain("4.2");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe KPIGrid
// ══════════════════════════════════════════════════════════════════════════════

describe("KPIGrid", () => {
  const kpis = makeKPIs();

  it("renders kpi-grid container", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-grid")).not.toBeNull();
  });

  it("renders total-leads card", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-total-leads")).not.toBeNull();
  });

  it("shows correct total leads value", () => {
    render(<KPIGrid kpis={makeKPIs({ total_leads: 99 })} />);
    expect(screen.getByTestId("kpi-total-leads-value").textContent).toContain("99");
  });

  it("renders active-customers card", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-active-customers")).not.toBeNull();
  });

  it("renders renewals-due card", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-renewals-due")).not.toBeNull();
  });

  it("renders training completion as percentage", () => {
    render(<KPIGrid kpis={makeKPIs({ training_completion_rate: 0.75 })} />);
    expect(screen.getByTestId("kpi-training-completion-value").textContent).toContain("75%");
  });

  it("renders zero training completion as 0%", () => {
    render(<KPIGrid kpis={makeKPIs({ training_completion_rate: 0 })} />);
    expect(screen.getByTestId("kpi-training-completion-value").textContent).toContain("0%");
  });

  it("renders cert rate as percentage", () => {
    render(<KPIGrid kpis={makeKPIs({ certificate_issuance_rate: 0.8 })} />);
    expect(screen.getByTestId("kpi-cert-rate-value").textContent).toContain("80%");
  });

  it("renders null avg feedback as em-dash", () => {
    render(<KPIGrid kpis={makeKPIs({ avg_feedback_rating: null })} />);
    expect(screen.getByTestId("kpi-avg-feedback-value").textContent).toContain("—");
  });

  it("renders avg feedback with star prefix", () => {
    render(<KPIGrid kpis={makeKPIs({ avg_feedback_rating: 4.2 })} />);
    expect(screen.getByTestId("kpi-avg-feedback-value").textContent).toContain("4.2");
  });

  it("renders workflow completion as percentage", () => {
    render(<KPIGrid kpis={makeKPIs({ workflow_completion_rate: 0.6 })} />);
    expect(screen.getByTestId("kpi-workflow-completion-value").textContent).toContain("60%");
  });

  it("renders open tasks", () => {
    render(<KPIGrid kpis={makeKPIs({ open_operations_tasks: 7 })} />);
    expect(screen.getByTestId("kpi-open-tasks-value").textContent).toContain("7");
  });

  it("renders health score card", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-health-score")).not.toBeNull();
  });

  it("renders health score sub text", () => {
    render(<KPIGrid kpis={kpis} />);
    expect(screen.getByTestId("kpi-health-score-sub").textContent).toContain("out of 100");
  });

  it("renders health score value in range", () => {
    render(<KPIGrid kpis={makeKPIs({ business_health_score: 72 })} />);
    expect(screen.getByTestId("kpi-health-score-value").textContent).toContain("72");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe HealthGauge
// ══════════════════════════════════════════════════════════════════════════════

describe("HealthGauge", () => {
  it("renders health-gauge container", () => {
    render(<HealthGauge score={75} />);
    expect(screen.getByTestId("health-gauge")).not.toBeNull();
  });

  it("renders gauge arc element", () => {
    render(<HealthGauge score={75} />);
    expect(screen.getByTestId("health-gauge-arc")).not.toBeNull();
  });

  it("renders gauge label with score", () => {
    render(<HealthGauge score={75} />);
    expect(screen.getByTestId("health-gauge-label").textContent).toContain("75");
  });

  it("renders score 0", () => {
    render(<HealthGauge score={0} />);
    expect(screen.getByTestId("health-gauge-label").textContent).toContain("0");
  });

  it("renders score 100", () => {
    render(<HealthGauge score={100} />);
    expect(screen.getByTestId("health-gauge-label").textContent).toContain("100");
  });

  it("renders score 50", () => {
    render(<HealthGauge score={50} />);
    expect(screen.getByTestId("health-gauge-label").textContent).toContain("50");
  });

  it("uses green fill for high score (>= 70)", () => {
    render(<HealthGauge score={80} />);
    const arc = screen.getByTestId("health-gauge-arc");
    expect(arc.getAttribute("stroke")).toBe("#22c55e");
  });

  it("uses amber fill for mid score (40-69)", () => {
    render(<HealthGauge score={55} />);
    const arc = screen.getByTestId("health-gauge-arc");
    expect(arc.getAttribute("stroke")).toBe("#f59e0b");
  });

  it("uses red fill for low score (< 40)", () => {
    render(<HealthGauge score={30} />);
    const arc = screen.getByTestId("health-gauge-arc");
    expect(arc.getAttribute("stroke")).toBe("#ef4444");
  });

  it("renders Business Health label text", () => {
    render(<HealthGauge score={75} />);
    expect(screen.getByTestId("health-gauge").textContent).toContain("Business Health");
  });

  it("arc has stroke-dasharray attribute set", () => {
    render(<HealthGauge score={75} />);
    const arc = screen.getByTestId("health-gauge-arc");
    expect(arc.getAttribute("stroke-dasharray")).not.toBeNull();
  });

  it("exactly at 70 uses green", () => {
    render(<HealthGauge score={70} />);
    const arc = screen.getByTestId("health-gauge-arc");
    expect(arc.getAttribute("stroke")).toBe("#22c55e");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe AlertCard
// ══════════════════════════════════════════════════════════════════════════════

describe("AlertCard", () => {
  const alert = makeAlert();

  it("renders with correct testid", () => {
    render(<AlertCard alert={alert} />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
  });

  it("shows alert title", () => {
    render(<AlertCard alert={alert} />);
    expect(screen.getByTestId("alert-title-renewals_overdue").textContent).toContain(
      "Renewals Overdue"
    );
  });

  it("shows alert description", () => {
    render(<AlertCard alert={alert} />);
    expect(screen.getByTestId("alert-desc-renewals_overdue").textContent).toContain(
      "3 renewal"
    );
  });

  it("shows alert count", () => {
    render(<AlertCard alert={alert} />);
    expect(screen.getByTestId("alert-count-renewals_overdue").textContent).toContain("3");
  });

  it("shows severity badge", () => {
    render(<AlertCard alert={alert} />);
    expect(screen.getByTestId("alert-severity-renewals_overdue")).not.toBeNull();
  });

  it("severity badge shows severity text", () => {
    render(<AlertCard alert={alert} />);
    expect(
      screen.getByTestId("alert-severity-renewals_overdue").textContent
    ).toContain("critical");
  });

  it("renders warning severity", () => {
    const warn = makeAlert({ alert_type: "training_overdue", severity: "warning", title: "Training" });
    render(<AlertCard alert={warn} />);
    expect(screen.getByTestId("alert-severity-training_overdue").textContent).toContain("warning");
  });

  it("renders info severity", () => {
    const info = makeAlert({ alert_type: "low_feedback_scores", severity: "info", title: "Feedback" });
    render(<AlertCard alert={info} />);
    expect(screen.getByTestId("alert-severity-low_feedback_scores").textContent).toContain("info");
  });

  it("renders different alert types", () => {
    const wf = makeAlert({ alert_type: "workflow_backlog", severity: "warning", title: "Workflow" });
    render(<AlertCard alert={wf} />);
    expect(screen.getByTestId("alert-card-workflow_backlog")).not.toBeNull();
  });

  it("count 0 renders zero", () => {
    const zeroAlert = makeAlert({ count: 0 });
    render(<AlertCard alert={zeroAlert} />);
    expect(screen.getByTestId("alert-count-renewals_overdue").textContent).toContain("0");
  });

  it("large count renders", () => {
    const bigAlert = makeAlert({ count: 99 });
    render(<AlertCard alert={bigAlert} />);
    expect(screen.getByTestId("alert-count-renewals_overdue").textContent).toContain("99");
  });

  it("renders customers_at_risk card", () => {
    const risk = makeAlert({ alert_type: "customers_at_risk", severity: "critical", title: "At Risk" });
    render(<AlertCard alert={risk} />);
    expect(screen.getByTestId("alert-card-customers_at_risk")).not.toBeNull();
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe AlertsPanel
// ══════════════════════════════════════════════════════════════════════════════

describe("AlertsPanel", () => {
  it("renders alerts-panel container", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alerts-panel")).not.toBeNull();
  });

  it("shows loading indicator", () => {
    render(<AlertsPanel alerts={[]} isLoading={true} isError={false} />);
    expect(screen.getByTestId("alerts-loading")).not.toBeNull();
  });

  it("loading message has text", () => {
    render(<AlertsPanel alerts={[]} isLoading={true} isError={false} />);
    expect(screen.getByTestId("alerts-loading").textContent).toContain("Loading");
  });

  it("shows error indicator", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={true} />);
    expect(screen.getByTestId("alerts-error")).not.toBeNull();
  });

  it("error message has text", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={true} />);
    expect(screen.getByTestId("alerts-error").textContent).toContain("Failed");
  });

  it("shows empty state when no alerts", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alerts-empty")).not.toBeNull();
  });

  it("empty message has text", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alerts-empty").textContent).toContain("No active alerts");
  });

  it("hides alerts-list when empty", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={false} />);
    expect(screen.queryByTestId("alerts-list")).toBeNull();
  });

  it("shows alerts-list when alerts present", () => {
    render(<AlertsPanel alerts={[makeAlert()]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alerts-list")).not.toBeNull();
  });

  it("renders one alert card", () => {
    render(<AlertsPanel alerts={[makeAlert()]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
  });

  it("renders multiple alert cards", () => {
    const alerts = [
      makeAlert(),
      makeAlert({ alert_type: "customers_at_risk", severity: "critical", title: "At Risk" }),
    ];
    render(<AlertsPanel alerts={alerts} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
    expect(screen.getByTestId("alert-card-customers_at_risk")).not.toBeNull();
  });

  it("hides empty state when alerts present", () => {
    render(<AlertsPanel alerts={[makeAlert()]} isLoading={false} isError={false} />);
    expect(screen.queryByTestId("alerts-empty")).toBeNull();
  });

  it("loading hides alerts-list", () => {
    render(<AlertsPanel alerts={[makeAlert()]} isLoading={true} isError={false} />);
    expect(screen.queryByTestId("alerts-list")).toBeNull();
  });

  it("error hides alerts-list", () => {
    render(<AlertsPanel alerts={[makeAlert()]} isLoading={false} isError={true} />);
    expect(screen.queryByTestId("alerts-list")).toBeNull();
  });

  it("panel header shows Alerts label", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alerts-panel").textContent).toContain("Alerts");
  });

  it("loading hides empty state", () => {
    render(<AlertsPanel alerts={[]} isLoading={true} isError={false} />);
    expect(screen.queryByTestId("alerts-empty")).toBeNull();
  });

  it("error hides empty state", () => {
    render(<AlertsPanel alerts={[]} isLoading={false} isError={true} />);
    expect(screen.queryByTestId("alerts-empty")).toBeNull();
  });

  it("6 alerts all rendered", () => {
    const alerts = [
      makeAlert({ alert_type: "renewals_overdue" }),
      makeAlert({ alert_type: "customers_at_risk" }),
      makeAlert({ alert_type: "training_overdue" }),
      makeAlert({ alert_type: "workflow_backlog" }),
      makeAlert({ alert_type: "operations_backlog" }),
      makeAlert({ alert_type: "low_feedback_scores" }),
    ];
    render(<AlertsPanel alerts={alerts} isLoading={false} isError={false} />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
    expect(screen.getByTestId("alert-card-low_feedback_scores")).not.toBeNull();
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe CustomerHealthSection
// ══════════════════════════════════════════════════════════════════════════════

describe("CustomerHealthSection", () => {
  it("renders container", () => {
    render(<CustomerHealthSection distribution={{}} />);
    expect(screen.getByTestId("customer-health-section")).not.toBeNull();
  });

  it("shows section title", () => {
    render(<CustomerHealthSection distribution={{}} />);
    expect(screen.getByTestId("customer-health-section").textContent).toContain(
      "Customer Health"
    );
  });

  it("shows empty message when no data", () => {
    render(<CustomerHealthSection distribution={{}} />);
    expect(screen.getByTestId("health-empty")).not.toBeNull();
  });

  it("empty message has text", () => {
    render(<CustomerHealthSection distribution={{}} />);
    expect(screen.getByTestId("health-empty").textContent).toContain("No customer data");
  });

  it("hides empty when distribution present", () => {
    render(<CustomerHealthSection distribution={{ healthy: 5 }} />);
    expect(screen.queryByTestId("health-empty")).toBeNull();
  });

  it("renders distribution container", () => {
    render(<CustomerHealthSection distribution={{ healthy: 5 }} />);
    expect(screen.getByTestId("health-distribution")).not.toBeNull();
  });

  it("renders healthy bar", () => {
    render(<CustomerHealthSection distribution={{ healthy: 5 }} />);
    expect(screen.getByTestId("health-bar-healthy")).not.toBeNull();
  });

  it("renders at_risk bar", () => {
    render(<CustomerHealthSection distribution={{ healthy: 5, at_risk: 2 }} />);
    expect(screen.getByTestId("health-bar-at_risk")).not.toBeNull();
  });

  it("renders watch bar", () => {
    render(<CustomerHealthSection distribution={{ watch: 3 }} />);
    expect(screen.getByTestId("health-bar-watch")).not.toBeNull();
  });

  it("shows count in label text", () => {
    render(<CustomerHealthSection distribution={{ healthy: 7 }} />);
    expect(screen.getByTestId("health-distribution").textContent).toContain("7");
  });

  it("shows multiple statuses", () => {
    render(
      <CustomerHealthSection distribution={{ healthy: 5, at_risk: 2, watch: 3 }} />
    );
    expect(screen.getByTestId("health-bar-healthy")).not.toBeNull();
    expect(screen.getByTestId("health-bar-at_risk")).not.toBeNull();
    expect(screen.getByTestId("health-bar-watch")).not.toBeNull();
  });

  it("bar has inline width style", () => {
    render(<CustomerHealthSection distribution={{ healthy: 10 }} />);
    const bar = screen.getByTestId("health-bar-healthy");
    const style = bar.getAttribute("style") ?? "";
    expect(style).toContain("width");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe TrendCharts
// ══════════════════════════════════════════════════════════════════════════════

describe("TrendCharts", () => {
  const trends = [makeTrend("2026-07-01"), makeTrend("2026-07-02")];
  const onPeriodChange = vi.fn();

  beforeEach(() => { onPeriodChange.mockClear(); });

  it("renders trend-charts container", () => {
    render(
      <TrendCharts trends={trends} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-charts")).not.toBeNull();
  });

  it("renders 30d period button", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-period-30")).not.toBeNull();
  });

  it("renders 90d period button", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-period-90")).not.toBeNull();
  });

  it("renders 365d period button", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-period-365")).not.toBeNull();
  });

  it("active period button has different class", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    const btn = screen.getByTestId("trend-period-30");
    expect(btn.className).toContain("bg-blue-600");
  });

  it("inactive period button does not have active class", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    const btn = screen.getByTestId("trend-period-90");
    expect(btn.className).not.toContain("bg-blue-600");
  });

  it("clicking period calls onPeriodChange with 90", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    fireEvent.click(screen.getByTestId("trend-period-90"));
    expect(onPeriodChange).toHaveBeenCalledWith(90);
  });

  it("clicking 365 calls onPeriodChange with 365", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    fireEvent.click(screen.getByTestId("trend-period-365"));
    expect(onPeriodChange).toHaveBeenCalledWith(365);
  });

  it("shows loading state", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={true} isError={false} />
    );
    expect(screen.getByTestId("trends-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={true} />
    );
    expect(screen.getByTestId("trends-error")).not.toBeNull();
  });

  it("shows empty state", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trends-empty")).not.toBeNull();
  });

  it("shows chart container when data present", () => {
    render(
      <TrendCharts trends={trends} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trends-chart-container")).not.toBeNull();
  });

  it("loading hides chart container", () => {
    render(
      <TrendCharts trends={trends} period={30} onPeriodChange={onPeriodChange} isLoading={true} isError={false} />
    );
    expect(screen.queryByTestId("trends-chart-container")).toBeNull();
  });

  it("error hides chart container", () => {
    render(
      <TrendCharts trends={trends} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={true} />
    );
    expect(screen.queryByTestId("trends-chart-container")).toBeNull();
  });

  it("empty hides chart container", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.queryByTestId("trends-chart-container")).toBeNull();
  });

  it("chart container renders recharts", () => {
    render(
      <TrendCharts trends={trends} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("recharts-container")).not.toBeNull();
  });

  it("Trends label shown", () => {
    render(
      <TrendCharts trends={[]} period={30} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-charts").textContent).toContain("Trends");
  });

  it("period 90 shows active when selected", () => {
    render(
      <TrendCharts trends={[]} period={90} onPeriodChange={onPeriodChange} isLoading={false} isError={false} />
    );
    expect(screen.getByTestId("trend-period-90").className).toContain("bg-blue-600");
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// describe ExecutiveDashboard
// ══════════════════════════════════════════════════════════════════════════════

describe("ExecutiveDashboard", () => {
  beforeEach(() => {
    mockUseDashboard.mockReset();
    mockUseAlerts.mockReset();
    mockUseTrends.mockReset();
  });

  it("renders executive-dashboard container", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("executive-dashboard")).not.toBeNull();
  });

  it("shows dashboard title", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("dashboard-title")).not.toBeNull();
  });

  it("title text is Executive Command Center", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("dashboard-title").textContent).toContain("Executive");
  });

  it("shows loading state when dashboard loading", () => {
    mockUseDashboard.mockReturnValue(loadingQuery() as ReturnType<typeof useExecutiveDashboard>);
    mockUseAlerts.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveAlerts>);
    mockUseTrends.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("dashboard-loading")).not.toBeNull();
  });

  it("loading hides summary section", () => {
    mockUseDashboard.mockReturnValue(loadingQuery() as ReturnType<typeof useExecutiveDashboard>);
    mockUseAlerts.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveAlerts>);
    mockUseTrends.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.queryByTestId("summary-section")).toBeNull();
  });

  it("shows error state when dashboard errors", () => {
    mockUseDashboard.mockReturnValue(errorQuery() as ReturnType<typeof useExecutiveDashboard>);
    mockUseAlerts.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveAlerts>);
    mockUseTrends.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("dashboard-error")).not.toBeNull();
  });

  it("shows summary section on data", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-section")).not.toBeNull();
  });

  it("shows health gauge in summary", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("health-gauge")).not.toBeNull();
  });

  it("summary-leads shows correct value", () => {
    setupDashboard(makeDashboard({ summary: makeSummary({ total_leads: 33 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-leads-value").textContent).toContain("33");
  });

  it("summary-customers shows value", () => {
    setupDashboard(makeDashboard({ summary: makeSummary({ active_customers: 12 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-customers-value").textContent).toContain("12");
  });

  it("summary-renewals shows value", () => {
    setupDashboard(makeDashboard({ summary: makeSummary({ renewals_due: 5 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-renewals-value").textContent).toContain("5");
  });

  it("summary-tasks shows value", () => {
    setupDashboard(makeDashboard({ summary: makeSummary({ open_operations_tasks: 8 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-tasks-value").textContent).toContain("8");
  });

  it("shows kpi-section", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("kpi-section")).not.toBeNull();
  });

  it("kpi-grid rendered inside kpi-section", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("kpi-grid")).not.toBeNull();
  });

  it("shows health-section", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("health-section")).not.toBeNull();
  });

  it("customer-health-section rendered", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("customer-health-section")).not.toBeNull();
  });

  it("shows alerts-section always", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alerts-section")).not.toBeNull();
  });

  it("shows trends-section always", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trends-section")).not.toBeNull();
  });

  it("alerts-panel inside alerts-section", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alerts-panel")).not.toBeNull();
  });

  it("trend-charts inside trends-section", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trend-charts")).not.toBeNull();
  });

  it("trend period buttons rendered", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trend-period-30")).not.toBeNull();
    expect(screen.getByTestId("trend-period-90")).not.toBeNull();
    expect(screen.getByTestId("trend-period-365")).not.toBeNull();
  });

  it("shows generated_at when data present", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("dashboard-generated-at")).not.toBeNull();
  });

  it("hides generated_at when loading", () => {
    mockUseDashboard.mockReturnValue(loadingQuery() as ReturnType<typeof useExecutiveDashboard>);
    mockUseAlerts.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveAlerts>);
    mockUseTrends.mockReturnValue(idleQuery([]) as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.queryByTestId("dashboard-generated-at")).toBeNull();
  });

  it("alerts loading state shown correctly", () => {
    setupDashboard();
    mockUseAlerts.mockReturnValue(loadingQuery() as ReturnType<typeof useExecutiveAlerts>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alerts-loading")).not.toBeNull();
  });

  it("alerts error state shown correctly", () => {
    setupDashboard();
    mockUseAlerts.mockReturnValue(errorQuery() as ReturnType<typeof useExecutiveAlerts>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alerts-error")).not.toBeNull();
  });

  it("empty alerts message shown", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alerts-empty")).not.toBeNull();
  });

  it("alerts rendered when present", () => {
    setupDashboard(makeDashboard(), [makeAlert()]);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
  });

  it("trends loading state shown", () => {
    setupDashboard();
    mockUseTrends.mockReturnValue(loadingQuery() as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trends-loading")).not.toBeNull();
  });

  it("trends error state shown", () => {
    setupDashboard();
    mockUseTrends.mockReturnValue(errorQuery() as ReturnType<typeof useExecutiveTrends>);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trends-error")).not.toBeNull();
  });

  it("trends empty message shown when empty", () => {
    setupDashboard(makeDashboard(), [], []);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trends-empty")).not.toBeNull();
  });

  it("trends chart shown when data present", () => {
    setupDashboard(makeDashboard(), [], [makeTrend()]);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("trends-chart-container")).not.toBeNull();
  });

  it("clicking 90d trend period re-renders with period 90 active", () => {
    setupDashboard(makeDashboard(), [], [makeTrend()]);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("trend-period-90"));
    expect(screen.getByTestId("trend-period-90").className).toContain("bg-blue-600");
  });

  it("clicking 365d trend period activates it", () => {
    setupDashboard(makeDashboard(), [], [makeTrend()]);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("trend-period-365"));
    expect(screen.getByTestId("trend-period-365").className).toContain("bg-blue-600");
  });

  it("kpi total leads value shown", () => {
    setupDashboard(makeDashboard({ kpis: makeKPIs({ total_leads: 77 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("kpi-total-leads-value").textContent).toContain("77");
  });

  it("kpi active customers value shown", () => {
    setupDashboard(makeDashboard({ kpis: makeKPIs({ active_customers: 15 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("kpi-active-customers-value").textContent).toContain("15");
  });

  it("health gauge score matches summary", () => {
    setupDashboard(makeDashboard({ summary: makeSummary({ business_health_score: 88 }) }));
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("health-gauge-label").textContent).toContain("88");
  });

  it("health distribution bars rendered", () => {
    setupDashboard(
      makeDashboard({
        kpis: makeKPIs({ customer_health_distribution: { healthy: 5, at_risk: 2 } }),
      })
    );
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("health-bar-healthy")).not.toBeNull();
    expect(screen.getByTestId("health-bar-at_risk")).not.toBeNull();
  });

  it("multiple alerts all rendered", () => {
    const alerts = [
      makeAlert({ alert_type: "renewals_overdue" }),
      makeAlert({ alert_type: "workflow_backlog", severity: "warning", title: "WF" }),
    ];
    setupDashboard(makeDashboard(), alerts);
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("alert-card-renewals_overdue")).not.toBeNull();
    expect(screen.getByTestId("alert-card-workflow_backlog")).not.toBeNull();
  });

  it("KPI section has label text", () => {
    setupDashboard();
    render(<ExecutiveDashboard workspaceId="ws-1" />);
    expect(screen.getByTestId("kpi-section").textContent).toContain("Key Performance Indicators");
  });
});
