"use client";

import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { AlertCircle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useBusinessHealth,
  useOperationalAlerts,
  useBusinessSummary,
} from "@/features/dashboard/api/use-dashboard";
import type { OperationalAlert } from "@/features/dashboard/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 70) return "#22c55e";   // green
  if (score >= 50) return "#f59e0b";   // amber
  return "#ef4444";                    // red
}

function priorityColor(priority: OperationalAlert["priority"]): string {
  if (priority === "critical") return "text-red-600 border-red-200 bg-red-50";
  if (priority === "warning") return "text-amber-600 border-amber-200 bg-amber-50";
  return "text-blue-600 border-blue-200 bg-blue-50";
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "improving") return <TrendingUp className="h-4 w-4 text-green-600" />;
  if (trend === "declining") return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
}

// ── Section 1: Overall Health Score gauge ────────────────────────────────────

function HealthGauge({ score }: { score: number }) {
  const color = scoreColor(score);
  const data = [{ name: "Health", value: score, fill: color }];

  return (
    <section data-testid="health-score-gauge">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Overall Business Health
      </h3>
      <Card>
        <CardContent className="flex flex-col items-center pt-6 pb-4">
          <div data-testid="gauge-chart" className="relative h-48 w-48">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                cx="50%"
                cy="50%"
                innerRadius="60%"
                outerRadius="90%"
                startAngle={210}
                endAngle={-30}
                data={data}
              >
                <RadialBar dataKey="value" cornerRadius={6} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span
                data-testid="gauge-score"
                className="text-4xl font-bold tabular-nums"
                style={{ color }}
              >
                {score.toFixed(0)}
              </span>
              <span className="text-xs text-muted-foreground">/ 100</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

// ── Section 2: Health Breakdown score cards ───────────────────────────────────

function ScoreCard({
  testId,
  label,
  score,
  weight,
}: {
  testId: string;
  label: string;
  score: number;
  weight: number;
}) {
  const color = scoreColor(score);
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold tabular-nums" style={{ color }}>
          {score.toFixed(0)}
        </p>
        <p className="text-xs text-muted-foreground">{(weight * 100).toFixed(0)}% weight</p>
      </CardContent>
    </Card>
  );
}

function BreakdownSection({
  pipeline,
  revenue,
  campaign,
  recommendation,
  communication,
}: {
  pipeline: number;
  revenue: number;
  campaign: number;
  recommendation: number;
  communication: number;
}) {
  const chartData = [
    { name: "Pipeline", score: pipeline },
    { name: "Revenue", score: revenue },
    { name: "Campaign", score: campaign },
    { name: "Rec.", score: recommendation },
    { name: "Comms", score: communication },
  ];

  return (
    <section data-testid="health-breakdown">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Health Breakdown
      </h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        <ScoreCard testId="score-pipeline" label="Pipeline" score={pipeline} weight={0.20} />
        <ScoreCard testId="score-revenue" label="Revenue Conversion" score={revenue} weight={0.25} />
        <ScoreCard testId="score-campaign" label="Campaign Delivery" score={campaign} weight={0.15} />
        <ScoreCard testId="score-recommendation" label="Recommendation" score={recommendation} weight={0.20} />
        <ScoreCard testId="score-communication" label="Communication" score={communication} weight={0.20} />
      </div>
      <div data-testid="breakdown-chart" className="mt-4 h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} barSize={32}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Bar dataKey="score" radius={[4, 4, 0, 0]} fill="#6366f1" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

// ── Section 3: Operational Alerts ────────────────────────────────────────────

function AlertsSection({ alerts }: { alerts: OperationalAlert[] }) {
  return (
    <section data-testid="alerts-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Operational Alerts
      </h3>
      {alerts.length === 0 ? (
        <p data-testid="no-alerts" className="text-sm text-muted-foreground">
          No operational alerts — all systems healthy.
        </p>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <div
              key={i}
              data-testid={`alert-item-${i}`}
              className={`rounded-md border p-3 text-sm ${priorityColor(alert.priority)}`}
            >
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0">
                  <p className="font-medium">{alert.title}</p>
                  <p className="mt-0.5 text-xs opacity-80">{alert.description}</p>
                  <p className="mt-1 text-xs font-medium">
                    Action: {alert.recommended_action}
                  </p>
                </div>
                <span
                  data-testid={`alert-priority-${i}`}
                  className="ml-auto shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold uppercase"
                >
                  {alert.priority}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Section 4: Business Trend ─────────────────────────────────────────────────

function TrendSection({ trend }: { trend: string }) {
  const label =
    trend === "improving"
      ? "Outreach activity is trending up this week."
      : trend === "declining"
      ? "Outreach activity is trending down this week."
      : "Outreach activity is stable week over week.";

  return (
    <section data-testid="trend-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Business Trend
      </h3>
      <Card>
        <CardContent className="flex items-center gap-3 pt-4">
          <TrendIcon trend={trend} />
          <span data-testid="trend-label" className="text-sm font-medium">
            {label}
          </span>
          <span
            data-testid="trend-value"
            className="ml-auto rounded-full bg-muted px-3 py-1 text-xs font-semibold capitalize"
          >
            {trend}
          </span>
        </CardContent>
      </Card>
    </section>
  );
}

// ── Section 5: Top Strengths ──────────────────────────────────────────────────

function StrengthsSection({ strengths }: { strengths: string[] }) {
  return (
    <section data-testid="strengths-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Top Strengths
      </h3>
      {strengths.length === 0 ? (
        <p data-testid="strengths-empty" className="text-sm text-muted-foreground">
          No strengths above 70 yet — keep building!
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {strengths.map((s, i) => (
            <span
              key={i}
              data-testid={`strength-item-${i}`}
              className="rounded-full border border-green-200 bg-green-50 px-3 py-1 text-sm font-medium text-green-700"
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Section 6: Areas Needing Attention ────────────────────────────────────────

function AttentionSection({ areas }: { areas: string[] }) {
  return (
    <section data-testid="attention-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Areas Needing Attention
      </h3>
      {areas.length === 0 ? (
        <p data-testid="attention-empty" className="text-sm text-muted-foreground">
          No areas below 50 — keep it up!
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {areas.map((a, i) => (
            <span
              key={i}
              data-testid={`attention-item-${i}`}
              className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-sm font-medium text-orange-700"
            >
              {a}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Section 7: Business Summary ───────────────────────────────────────────────

function SummarySection({ lines }: { lines: string[] }) {
  return (
    <section data-testid="summary-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Executive Summary
      </h3>
      <Card>
        <CardContent className="pt-4">
          {lines.length === 0 ? (
            <p data-testid="summary-empty" className="text-sm text-muted-foreground">
              No summary available.
            </p>
          ) : (
            <ul data-testid="summary-lines" className="space-y-1">
              {lines.map((line, i) => (
                <li key={i} data-testid={`summary-line-${i}`} className="text-sm">
                  {line}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function BusinessHealthDashboard() {
  const { workspaceId } = useWorkspace();
  const health = useBusinessHealth(workspaceId);
  const alerts = useOperationalAlerts(workspaceId);
  const summary = useBusinessSummary(workspaceId);

  if (health.isLoading || alerts.isLoading || summary.isLoading) {
    return (
      <div data-testid="health-skeleton" className="space-y-4">
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (health.isError || alerts.isError || summary.isError) {
    return (
      <div
        data-testid="health-error"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load business health data. Try refreshing.
      </div>
    );
  }

  const h = health.data!;
  const a = alerts.data!;
  const s = summary.data!;

  return (
    <div data-testid="business-health-dashboard" className="space-y-8">
      <HealthGauge score={h.overall_score} />
      <BreakdownSection
        pipeline={h.pipeline_score}
        revenue={h.revenue_score}
        campaign={h.campaign_score}
        recommendation={h.recommendation_score}
        communication={h.communication_score}
      />
      <AlertsSection alerts={a.alerts} />
      <TrendSection trend={h.health_trend} />
      <StrengthsSection strengths={h.top_strengths} />
      <AttentionSection areas={h.areas_needing_attention} />
      <SummarySection lines={s.lines} />
    </div>
  );
}
