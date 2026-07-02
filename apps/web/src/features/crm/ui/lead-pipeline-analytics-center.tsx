"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  usePipelineSummary,
  usePipelineStages,
  usePipelineSources,
  usePipelineIndustries,
  usePipelineConversion,
} from "@/features/crm/api/use-lead-pipeline-analytics";
import type {
  StageAnalysisItem,
  SourceAnalysisItem,
  IndustryAnalysisItem,
} from "@/features/crm/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(v: number): string {
  return `${v.toFixed(1)}%`;
}

function healthColor(score: number): string {
  if (score >= 70) return "text-green-600";
  if (score >= 40) return "text-yellow-600";
  return "text-red-600";
}

function barColor(rate: number): string {
  if (rate >= 60) return "#22c55e";
  if (rate >= 30) return "#f59e0b";
  return "#ef4444";
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  testId,
  sub,
}: {
  label: string;
  value: string | number;
  testId?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold" data-testid={testId}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="mb-3 text-base font-semibold text-foreground">{title}</h2>
  );
}

function LoadingRow() {
  return (
    <div className="h-6 animate-pulse rounded bg-muted" />
  );
}

// ── Overview Section ──────────────────────────────────────────────────────────

function OverviewSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = usePipelineSummary(workspaceId);
  const summary = data?.data;

  if (isLoading) return <LoadingRow />;
  if (!summary) return null;

  return (
    <section data-testid="overview-section">
      <SectionHeader title="Pipeline Overview" />
      {summary.data_integrity_warning && (
        <div
          className="mb-3 rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-800"
          data-testid="integrity-warning"
        >
          Data integrity warning: some records have inconsistent timestamps.
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Total Leads"
          value={summary.total_leads}
          testId="total-leads"
        />
        <StatCard
          label="Active"
          value={summary.active_leads}
          testId="active-leads"
        />
        <StatCard
          label="Qualified"
          value={summary.qualified_leads}
          testId="qualified-leads"
        />
        <StatCard
          label="Won"
          value={summary.won_leads}
          testId="won-leads"
        />
        <StatCard
          label="Lost"
          value={summary.lost_leads}
          testId="lost-leads"
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard
          label="Proposal Leads"
          value={summary.proposal_leads}
          testId="proposal-leads"
        />
        <StatCard
          label="Conversion Rate"
          value={pct(summary.overall_conversion_rate)}
          testId="conversion-rate"
        />
        <StatCard
          label="Health Score"
          value={summary.pipeline_health_score}
          testId="health-score"
          sub={`Score out of 100`}
        />
      </div>
      <p
        className={`mt-2 text-sm font-medium ${healthColor(summary.pipeline_health_score)}`}
        data-testid="health-label"
      >
        {summary.pipeline_health_score >= 70
          ? "Healthy pipeline"
          : summary.pipeline_health_score >= 40
            ? "Pipeline needs attention"
            : "Pipeline at risk"}
      </p>
    </section>
  );
}

// ── Stage Funnel Section ──────────────────────────────────────────────────────

function StageFunnelSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = usePipelineStages(workspaceId);
  const stages = data?.data?.items ?? [];

  return (
    <section data-testid="stage-funnel-section">
      <SectionHeader title="Stage Funnel" />
      {isLoading ? (
        <LoadingRow />
      ) : (
        <>
          <div className="mb-4 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stages} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar
                  dataKey="count"
                  fill="#6366f1"
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full text-sm" data-testid="stage-table">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-1 pr-4">Stage</th>
                <th className="pb-1 pr-4">Count</th>
                <th className="pb-1 pr-4">Avg Days</th>
                <th className="pb-1 pr-4">Conversion</th>
                <th className="pb-1">Drop-off</th>
              </tr>
            </thead>
            <tbody>
              {stages.map((item: StageAnalysisItem) => (
                <tr key={item.stage} className="border-b last:border-0">
                  <td className="py-1.5 pr-4 font-medium capitalize">
                    {item.stage.replace(/_/g, " ")}
                  </td>
                  <td className="py-1.5 pr-4" data-testid={`stage-count-${item.stage}`}>
                    {item.count}
                  </td>
                  <td className="py-1.5 pr-4">{item.average_days.toFixed(1)}</td>
                  <td
                    className="py-1.5 pr-4"
                    style={{ color: barColor(item.conversion_rate) }}
                  >
                    {pct(item.conversion_rate)}
                  </td>
                  <td className="py-1.5">{pct(item.drop_off_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ── Source Performance Section ────────────────────────────────────────────────

function SourcePerformanceSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = usePipelineSources(workspaceId);
  const items = data?.data?.items ?? [];

  return (
    <section data-testid="source-performance-section">
      <SectionHeader title="Source Performance" />
      {isLoading ? (
        <LoadingRow />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No source data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="source-table">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="pb-1 pr-4">Source</th>
              <th className="pb-1 pr-4">Leads</th>
              <th className="pb-1 pr-4">Qualified</th>
              <th className="pb-1 pr-4">Won</th>
              <th className="pb-1">Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item: SourceAnalysisItem) => (
              <tr key={item.source} className="border-b last:border-0">
                <td
                  className="py-1.5 pr-4 font-medium"
                  data-testid={`source-name-${item.source}`}
                >
                  {item.source || "Unknown"}
                </td>
                <td className="py-1.5 pr-4">{item.lead_count}</td>
                <td className="py-1.5 pr-4">{item.qualified}</td>
                <td className="py-1.5 pr-4">{item.won}</td>
                <td
                  className="py-1.5"
                  style={{ color: barColor(item.conversion_rate) }}
                >
                  {pct(item.conversion_rate)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Industry Performance Section ──────────────────────────────────────────────

function IndustryPerformanceSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = usePipelineIndustries(workspaceId);
  const items = data?.data?.items ?? [];

  return (
    <section data-testid="industry-performance-section">
      <SectionHeader title="Industry Performance" />
      {isLoading ? (
        <LoadingRow />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No industry data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="industry-table">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="pb-1 pr-4">Industry</th>
              <th className="pb-1 pr-4">Leads</th>
              <th className="pb-1 pr-4">Won</th>
              <th className="pb-1 pr-4">Win Rate</th>
              <th className="pb-1">Avg Days</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item: IndustryAnalysisItem) => (
              <tr key={item.industry} className="border-b last:border-0">
                <td
                  className="py-1.5 pr-4 font-medium"
                  data-testid={`industry-name-${item.industry}`}
                >
                  {item.industry || "Unknown"}
                </td>
                <td className="py-1.5 pr-4">{item.lead_count}</td>
                <td className="py-1.5 pr-4">{item.won}</td>
                <td
                  className="py-1.5 pr-4"
                  style={{ color: barColor(item.conversion_rate) }}
                >
                  {pct(item.conversion_rate)}
                </td>
                <td className="py-1.5">{item.average_pipeline_days.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Conversion Metrics Section ────────────────────────────────────────────────

function ConversionMetricsSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = usePipelineConversion(workspaceId);
  const conv = data?.data;

  return (
    <section data-testid="conversion-metrics-section">
      <SectionHeader title="Conversion Metrics" />
      {isLoading ? (
        <LoadingRow />
      ) : !conv ? null : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="Qualified → Proposal"
            value={pct(conv.qualified_to_proposal)}
            testId="qualified-to-proposal"
          />
          <StatCard
            label="Proposal → Win"
            value={pct(conv.proposal_to_win)}
            testId="proposal-to-win"
          />
          <StatCard
            label="Overall Win Rate"
            value={pct(conv.overall_win_rate)}
            testId="overall-win-rate"
          />
          <StatCard
            label="Avg Days to Win"
            value={conv.average_days_to_win.toFixed(1)}
            testId="avg-days-to-win"
            sub="days"
          />
        </div>
      )}
    </section>
  );
}

// ── Root Export ───────────────────────────────────────────────────────────────

export function LeadPipelineAnalyticsCenter({
  workspaceId,
}: {
  workspaceId: string;
}) {
  return (
    <div className="space-y-8" data-testid="lead-pipeline-analytics-center">
      <OverviewSection workspaceId={workspaceId} />
      <StageFunnelSection workspaceId={workspaceId} />
      <SourcePerformanceSection workspaceId={workspaceId} />
      <IndustryPerformanceSection workspaceId={workspaceId} />
      <ConversionMetricsSection workspaceId={workspaceId} />
    </div>
  );
}
