"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  useExecutiveDashboard,
  useExecutiveAlerts,
  useExecutiveTrends,
} from "@/features/executive/api/use-executive";
import type {
  ExecutiveAlert,
  ExecutiveDashboard,
  ExecutiveKPIs,
  ExecutiveTrend,
  TrendPeriod,
} from "@/features/executive/types-executive";

// ── KPICard ──────────────────────────────────────────────────────────────────

interface KPICardProps {
  label: string;
  value: string | number;
  sub?: string;
  testId: string;
}

export function KPICard({ label, value, sub, testId }: KPICardProps) {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border bg-white p-4 shadow-sm"
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        data-testid={`${testId}-value`}
        className="mt-1 text-2xl font-semibold"
      >
        {value}
      </p>
      {sub && (
        <p data-testid={`${testId}-sub`} className="mt-0.5 text-xs text-muted-foreground">
          {sub}
        </p>
      )}
    </div>
  );
}

// ── KPIGrid ───────────────────────────────────────────────────────────────────

export function KPIGrid({ kpis }: { kpis: ExecutiveKPIs }) {
  const trainingPct = Math.round(kpis.training_completion_rate * 100);
  const certPct = Math.round(kpis.certificate_issuance_rate * 100);
  const wfPct = Math.round(kpis.workflow_completion_rate * 100);
  const feedback = kpis.avg_feedback_rating != null
    ? `★ ${kpis.avg_feedback_rating.toFixed(1)}`
    : "—";

  return (
    <div data-testid="kpi-grid" className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <KPICard testId="kpi-total-leads" label="Total Leads" value={kpis.total_leads} />
      <KPICard
        testId="kpi-active-customers"
        label="Active Customers"
        value={kpis.active_customers}
      />
      <KPICard
        testId="kpi-renewals-due"
        label="Renewals Due (30d)"
        value={kpis.renewals_due}
      />
      <KPICard
        testId="kpi-training-completion"
        label="Training Completion"
        value={`${trainingPct}%`}
      />
      <KPICard
        testId="kpi-cert-rate"
        label="Certificate Rate"
        value={`${certPct}%`}
      />
      <KPICard
        testId="kpi-avg-feedback"
        label="Avg Feedback"
        value={feedback}
      />
      <KPICard
        testId="kpi-workflow-completion"
        label="Workflow Completion"
        value={`${wfPct}%`}
      />
      <KPICard
        testId="kpi-open-tasks"
        label="Open Tasks"
        value={kpis.open_operations_tasks}
      />
      <KPICard
        testId="kpi-health-score"
        label="Health Score"
        value={kpis.business_health_score}
        sub="out of 100"
      />
    </div>
  );
}

// ── HealthGauge ───────────────────────────────────────────────────────────────

export function HealthGauge({ score }: { score: number }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const filled = (score / 100) * circumference;
  const color =
    score >= 70 ? "#22c55e" : score >= 40 ? "#f59e0b" : "#ef4444";

  return (
    <div data-testid="health-gauge" className="flex flex-col items-center">
      <svg width={100} height={100} viewBox="0 0 100 100">
        <circle
          cx={50}
          cy={50}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={10}
        />
        <circle
          data-testid="health-gauge-arc"
          cx={50}
          cy={50}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeDasharray={`${filled} ${circumference - filled}`}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
        <text
          data-testid="health-gauge-label"
          x={50}
          y={55}
          textAnchor="middle"
          className="text-lg font-semibold"
          fontSize={18}
          fontWeight={600}
          fill={color}
        >
          {score}
        </text>
      </svg>
      <p className="text-xs text-muted-foreground">Business Health</p>
    </div>
  );
}

// ── AlertsPanel ───────────────────────────────────────────────────────────────

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-200 bg-red-50",
  warning: "border-yellow-200 bg-yellow-50",
  info: "border-blue-200 bg-blue-50",
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  warning: "bg-yellow-100 text-yellow-800",
  info: "bg-blue-100 text-blue-800",
};

export function AlertCard({ alert }: { alert: ExecutiveAlert }) {
  return (
    <div
      data-testid={`alert-card-${alert.alert_type}`}
      className={`rounded-lg border p-3 ${SEVERITY_STYLE[alert.severity] ?? ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              data-testid={`alert-severity-${alert.alert_type}`}
              className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                SEVERITY_BADGE[alert.severity] ?? ""
              }`}
            >
              {alert.severity}
            </span>
            <p className="text-sm font-medium" data-testid={`alert-title-${alert.alert_type}`}>
              {alert.title}
            </p>
          </div>
          <p
            data-testid={`alert-desc-${alert.alert_type}`}
            className="mt-1 text-xs text-muted-foreground"
          >
            {alert.description}
          </p>
        </div>
        <span
          data-testid={`alert-count-${alert.alert_type}`}
          className="flex-shrink-0 rounded-full bg-white px-2 py-0.5 text-xs font-semibold shadow-sm"
        >
          {alert.count}
        </span>
      </div>
    </div>
  );
}

export function AlertsPanel({
  alerts,
  isLoading,
  isError,
}: {
  alerts: ExecutiveAlert[];
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <div data-testid="alerts-panel" className="space-y-2">
      <p className="text-sm font-medium">Alerts</p>
      {isLoading && (
        <p data-testid="alerts-loading" className="text-xs text-muted-foreground">
          Loading alerts…
        </p>
      )}
      {isError && (
        <p data-testid="alerts-error" className="text-xs text-red-600">
          Failed to load alerts.
        </p>
      )}
      {!isLoading && !isError && alerts.length === 0 && (
        <p data-testid="alerts-empty" className="text-xs text-muted-foreground">
          No active alerts.
        </p>
      )}
      {!isLoading && !isError && alerts.length > 0 && (
        <div data-testid="alerts-list" className="space-y-2">
          {alerts.map((a) => (
            <AlertCard key={a.alert_type} alert={a} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── TrendCharts ───────────────────────────────────────────────────────────────

const TREND_LABELS: Record<TrendPeriod, string> = {
  30: "30 days",
  90: "90 days",
  365: "1 year",
};

export function TrendCharts({
  trends,
  period,
  onPeriodChange,
  isLoading,
  isError,
}: {
  trends: ExecutiveTrend[];
  period: TrendPeriod;
  onPeriodChange: (p: TrendPeriod) => void;
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <div data-testid="trend-charts" className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Trends</p>
        <div className="flex gap-1">
          {([30, 90, 365] as TrendPeriod[]).map((p) => (
            <button
              key={p}
              data-testid={`trend-period-${p}`}
              onClick={() => onPeriodChange(p)}
              className={`rounded px-2 py-0.5 text-xs ${
                period === p
                  ? "bg-blue-600 text-white"
                  : "border text-muted-foreground hover:bg-muted"
              }`}
            >
              {TREND_LABELS[p]}
            </button>
          ))}
        </div>
      </div>
      {isLoading && (
        <p data-testid="trends-loading" className="text-xs text-muted-foreground">
          Loading trends…
        </p>
      )}
      {isError && (
        <p data-testid="trends-error" className="text-xs text-red-600">
          Failed to load trends.
        </p>
      )}
      {!isLoading && !isError && trends.length === 0 && (
        <p data-testid="trends-empty" className="text-xs text-muted-foreground">
          No trend data available.
        </p>
      )}
      {!isLoading && !isError && trends.length > 0 && (
        <div data-testid="trends-chart-container" className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trends} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="leads_created"
                name="Leads"
                stroke="#6366f1"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="customers_created"
                name="Customers"
                stroke="#22c55e"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="training_completions"
                name="Trainings"
                stroke="#f59e0b"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="renewals_processed"
                name="Renewals"
                stroke="#ec4899"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── CustomerHealthSection ─────────────────────────────────────────────────────

export function CustomerHealthSection({
  distribution,
}: {
  distribution: Record<string, number>;
}) {
  const total = Object.values(distribution).reduce((s, n) => s + n, 0);
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);

  const COLOR: Record<string, string> = {
    healthy: "bg-green-500",
    watch: "bg-yellow-400",
    attention: "bg-orange-400",
    at_risk: "bg-red-500",
    inactive: "bg-gray-400",
  };

  return (
    <div data-testid="customer-health-section" className="space-y-2">
      <p className="text-sm font-medium">Customer Health</p>
      {entries.length === 0 ? (
        <p data-testid="health-empty" className="text-xs text-muted-foreground">
          No customer data.
        </p>
      ) : (
        <div data-testid="health-distribution" className="space-y-1.5">
          {entries.map(([status, count]) => (
            <div key={status} className="flex items-center gap-2">
              <span
                data-testid={`health-bar-${status}`}
                className={`h-2 rounded-full ${COLOR[status] ?? "bg-slate-400"}`}
                style={{ width: total > 0 ? `${(count / total) * 100}%` : "0%" }}
              />
              <span className="text-xs text-muted-foreground capitalize">
                {status.replace(/_/g, " ")} ({count})
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── ExecutiveDashboard ────────────────────────────────────────────────────────

interface ExecutiveDashboardProps {
  workspaceId: string;
}

export function ExecutiveDashboard({ workspaceId }: ExecutiveDashboardProps) {
  const [trendPeriod, setTrendPeriod] = useState<TrendPeriod>(30);

  const {
    data: dashboardData,
    isLoading: dashboardLoading,
    isError: dashboardError,
  } = useExecutiveDashboard(workspaceId);

  const {
    data: alertsData,
    isLoading: alertsLoading,
    isError: alertsError,
  } = useExecutiveAlerts(workspaceId);

  const {
    data: trendsData,
    isLoading: trendsLoading,
    isError: trendsError,
  } = useExecutiveTrends(workspaceId, trendPeriod);

  const dashboard = dashboardData?.data ?? null;
  const alerts = alertsData?.data ?? [];
  const trends = trendsData?.data ?? [];

  return (
    <div data-testid="executive-dashboard" className="space-y-6 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold" data-testid="dashboard-title">
          Executive Command Center
        </h1>
        {dashboard && (
          <p
            data-testid="dashboard-generated-at"
            className="text-xs text-muted-foreground"
          >
            Updated {new Date(dashboard.generated_at).toLocaleTimeString()}
          </p>
        )}
      </div>

      {/* Loading state */}
      {dashboardLoading && (
        <p
          data-testid="dashboard-loading"
          className="py-8 text-center text-sm text-muted-foreground"
        >
          Loading dashboard…
        </p>
      )}

      {/* Error state */}
      {dashboardError && (
        <p data-testid="dashboard-error" className="text-sm text-red-600">
          Failed to load dashboard.
        </p>
      )}

      {/* Content */}
      {!dashboardLoading && !dashboardError && dashboard && (
        <>
          {/* Summary row */}
          <section data-testid="summary-section">
            <div className="flex items-center gap-6">
              <HealthGauge score={dashboard.summary.business_health_score} />
              <div className="grid flex-1 grid-cols-2 gap-3 md:grid-cols-4">
                <KPICard
                  testId="summary-leads"
                  label="Total Leads"
                  value={dashboard.summary.total_leads}
                />
                <KPICard
                  testId="summary-customers"
                  label="Active Customers"
                  value={dashboard.summary.active_customers}
                />
                <KPICard
                  testId="summary-renewals"
                  label="Renewals Due"
                  value={dashboard.summary.renewals_due}
                />
                <KPICard
                  testId="summary-tasks"
                  label="Open Tasks"
                  value={dashboard.summary.open_operations_tasks}
                />
              </div>
            </div>
          </section>

          {/* KPI Grid */}
          <section data-testid="kpi-section">
            <p className="mb-2 text-sm font-medium">Key Performance Indicators</p>
            <KPIGrid kpis={dashboard.kpis} />
          </section>

          {/* Customer Health */}
          <section data-testid="health-section">
            <CustomerHealthSection
              distribution={dashboard.kpis.customer_health_distribution}
            />
          </section>
        </>
      )}

      {/* Alerts Panel — independent query */}
      <section data-testid="alerts-section">
        <AlertsPanel
          alerts={alerts}
          isLoading={alertsLoading}
          isError={alertsError}
        />
      </section>

      {/* Trend Charts — independent query */}
      <section data-testid="trends-section">
        <TrendCharts
          trends={trends}
          period={trendPeriod}
          onPeriodChange={setTrendPeriod}
          isLoading={trendsLoading}
          isError={trendsError}
        />
      </section>
    </div>
  );
}
