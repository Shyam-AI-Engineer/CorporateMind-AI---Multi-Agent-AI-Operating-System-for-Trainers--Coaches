"use client";

import { useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { AlertTriangle, TrendingUp, Users, Layers, Activity } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useAnalyticsSummary,
  useAnalyticsTemplates,
  useAnalyticsBottlenecks,
  useAnalyticsTrends,
  useAnalyticsWorkload,
} from "@/features/workflows/api/use-workflow-analytics";

// ── Shared helpers ─────────────────────────────────────────────────────────────

function pct(rate: number) {
  return `${(rate * 100).toFixed(1)}%`;
}

function LoadingRow() {
  return (
    <div
      className="h-8 w-full animate-pulse rounded bg-muted"
      data-testid="loading-skeleton"
    />
  );
}

// ── Overview section ──────────────────────────────────────────────────────────

interface OverviewSectionProps {
  workspaceId: string;
}

function OverviewSection({ workspaceId }: OverviewSectionProps) {
  const { data, isLoading, error } = useAnalyticsSummary(workspaceId);

  return (
    <section data-testid="overview-section">
      <h2 className="mb-4 text-lg font-semibold">Overview</h2>

      {isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="overview-loading">
          {Array.from({ length: 6 }).map((_, i) => (
            <LoadingRow key={i} />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive" data-testid="overview-error">
          Failed to load summary.
        </p>
      )}

      {!isLoading && !error && !data && (
        <p className="text-sm text-muted-foreground" data-testid="overview-empty">
          No workflow data yet.
        </p>
      )}

      {data && (
        <>
          {data.data_integrity_warning && (
            <div
              className="mb-4 flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
              data-testid="integrity-warning"
            >
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>
                Data integrity warning: required steps with skipped status detected. No
                automated action taken — review manually.
              </span>
            </div>
          )}

          <div
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            data-testid="overview-cards"
          >
            <StatCard
              testid="stat-total-runs"
              label="Total Runs"
              value={data.total_runs}
            />
            <StatCard
              testid="stat-active-runs"
              label="Active Runs"
              value={data.active_runs}
            />
            <StatCard
              testid="stat-completed-runs"
              label="Completed"
              value={data.completed_runs}
            />
            <StatCard
              testid="stat-cancelled-runs"
              label="Cancelled"
              value={data.cancelled_runs}
            />
            <StatCard
              testid="stat-completion-rate"
              label="Completion Rate"
              value={pct(data.completion_rate)}
            />
            <StatCard
              testid="stat-avg-completion-days"
              label="Avg Completion (days)"
              value={data.average_completion_days.toFixed(1)}
            />
            <StatCard
              testid="stat-avg-step-days"
              label="Avg Step Completion (days)"
              value={data.average_step_completion_days.toFixed(1)}
            />
            <StatCard
              testid="stat-avg-required-steps"
              label="Avg Required Steps"
              value={data.average_required_steps.toFixed(1)}
            />
            <StatCard
              testid="stat-avg-optional-steps"
              label="Avg Optional Steps"
              value={data.average_optional_steps.toFixed(1)}
            />
          </div>
        </>
      )}
    </section>
  );
}

function StatCard({
  label,
  value,
  testid,
}: {
  label: string;
  value: string | number;
  testid: string;
}) {
  return (
    <div
      className="rounded-lg border p-4"
      data-testid={testid}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

// ── Template performance section ──────────────────────────────────────────────

interface TemplateSectionProps {
  workspaceId: string;
}

function TemplateSection({ workspaceId }: TemplateSectionProps) {
  const { data, isLoading, error } = useAnalyticsTemplates(workspaceId);

  return (
    <section data-testid="template-section">
      <h2 className="mb-4 text-lg font-semibold">Template Performance</h2>

      {isLoading && (
        <div className="space-y-2" data-testid="template-loading">
          {Array.from({ length: 3 }).map((_, i) => <LoadingRow key={i} />)}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive" data-testid="template-error">
          Failed to load template analytics.
        </p>
      )}

      {!isLoading && !error && data?.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="template-empty">
          No template data yet.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="space-y-4">
          {/* BarChart: completion rate per template */}
          <div className="rounded-lg border p-4" data-testid="template-chart">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={data.items.map((t) => ({
                  name: t.template_name,
                  rate: +(t.completion_rate * 100).toFixed(1),
                  completed: t.completed,
                }))}
                margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis unit="%" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => `${v}%`} />
                <Bar dataKey="rate" name="Completion %" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Detail table */}
          <div className="overflow-x-auto rounded-lg border" data-testid="template-table">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Template</th>
                  <th className="px-4 py-2 text-right font-medium">Runs</th>
                  <th className="px-4 py-2 text-right font-medium">Completed</th>
                  <th className="px-4 py-2 text-right font-medium">Rate</th>
                  <th className="px-4 py-2 text-right font-medium">Avg Days</th>
                  <th className="px-4 py-2 text-right font-medium">Avg Steps</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.template_id ?? item.template_name}
                    className="border-t"
                    data-testid={`template-row-${item.template_id ?? "none"}`}
                  >
                    <td className="px-4 py-2 font-medium">{item.template_name}</td>
                    <td className="px-4 py-2 text-right">{item.runs}</td>
                    <td className="px-4 py-2 text-right">{item.completed}</td>
                    <td className="px-4 py-2 text-right">{pct(item.completion_rate)}</td>
                    <td className="px-4 py-2 text-right">{item.average_completion_days.toFixed(1)}</td>
                    <td className="px-4 py-2 text-right">{item.average_steps.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Bottlenecks section ───────────────────────────────────────────────────────

interface BottleneckSectionProps {
  workspaceId: string;
}

function BottleneckSection({ workspaceId }: BottleneckSectionProps) {
  const { data, isLoading, error } = useAnalyticsBottlenecks(workspaceId);

  return (
    <section data-testid="bottleneck-section">
      <h2 className="mb-4 text-lg font-semibold">Bottlenecks</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Steps sorted by average elapsed days — slowest first.
      </p>

      {isLoading && (
        <div className="space-y-2" data-testid="bottleneck-loading">
          {Array.from({ length: 3 }).map((_, i) => <LoadingRow key={i} />)}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive" data-testid="bottleneck-error">
          Failed to load bottleneck data.
        </p>
      )}

      {!isLoading && !error && data?.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="bottleneck-empty">
          No step data yet.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border" data-testid="bottleneck-table">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Step</th>
                <th className="px-4 py-2 text-left font-medium">Template</th>
                <th className="px-4 py-2 text-right font-medium">Executions</th>
                <th className="px-4 py-2 text-right font-medium">Avg Days</th>
                <th className="px-4 py-2 text-right font-medium">Rate</th>
                <th className="px-4 py-2 text-right font-medium">Blocked</th>
                <th className="px-4 py-2 text-right font-medium">Skipped</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, idx) => (
                <tr
                  key={`${item.step_name}-${item.template_name}-${idx}`}
                  className="border-t"
                  data-testid={`bottleneck-row-${idx}`}
                >
                  <td className="px-4 py-2 font-medium">{item.step_name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{item.template_name}</td>
                  <td className="px-4 py-2 text-right">{item.times_executed}</td>
                  <td className="px-4 py-2 text-right font-medium">
                    {item.average_days.toFixed(2)}
                  </td>
                  <td className="px-4 py-2 text-right">{pct(item.completion_rate)}</td>
                  <td className="px-4 py-2 text-right">
                    {item.blocked_count > 0 ? (
                      <Badge variant="destructive" className="text-xs">
                        {item.blocked_count}
                      </Badge>
                    ) : (
                      item.blocked_count
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">{item.skip_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ── Trend section ─────────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
] as const;

interface TrendSectionProps {
  workspaceId: string;
}

function TrendSection({ workspaceId }: TrendSectionProps) {
  const [period, setPeriod] = useState<7 | 30 | 90>(30);
  const { data, isLoading, error } = useAnalyticsTrends(workspaceId, period);

  return (
    <section data-testid="trend-section">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Trend</h2>
        <div className="flex gap-1" data-testid="period-selector">
          {PERIOD_OPTIONS.map(({ label, value }) => (
            <Button
              key={value}
              size="sm"
              variant={period === value ? "default" : "outline"}
              onClick={() => setPeriod(value)}
              data-testid={`period-btn-${value}`}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="h-48 animate-pulse rounded-lg bg-muted" data-testid="trend-loading" />
      )}

      {error && (
        <p className="text-sm text-destructive" data-testid="trend-error">
          Failed to load trend data.
        </p>
      )}

      {!isLoading && !error && data?.buckets.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="trend-empty">
          No trend data for this period.
        </p>
      )}

      {data && data.buckets.length > 0 && (
        <div className="rounded-lg border p-4" data-testid="trend-chart">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart
              data={data.buckets}
              margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={(d: string) => d.slice(5)}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="runs_started"
                name="Started"
                stroke="#6366f1"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="runs_completed"
                name="Completed"
                stroke="#22c55e"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="runs_cancelled"
                name="Cancelled"
                stroke="#ef4444"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

// ── Workload section ──────────────────────────────────────────────────────────

interface WorkloadSectionProps {
  workspaceId: string;
}

function WorkloadSection({ workspaceId }: WorkloadSectionProps) {
  const { data, isLoading, error } = useAnalyticsWorkload(workspaceId);

  return (
    <section data-testid="workload-section">
      <h2 className="mb-4 text-lg font-semibold">Owner Workload</h2>

      {isLoading && (
        <div className="space-y-2" data-testid="workload-loading">
          {Array.from({ length: 3 }).map((_, i) => <LoadingRow key={i} />)}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive" data-testid="workload-error">
          Failed to load workload data.
        </p>
      )}

      {!isLoading && !error && data?.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="workload-empty">
          No workload data yet.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="space-y-4">
          {/* Horizontal BarChart — pending steps per role */}
          <div className="rounded-lg border p-4" data-testid="workload-chart">
            <ResponsiveContainer width="100%" height={Math.max(120, data.items.length * 48)}>
              <BarChart
                layout="vertical"
                data={data.items.map((w) => ({
                  name: w.owner,
                  pending: w.pending_steps,
                  completed: w.completed_steps,
                  blocked: w.blocked_steps,
                }))}
                margin={{ top: 8, right: 32, bottom: 8, left: 64 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={60} />
                <Tooltip />
                <Bar dataKey="pending" name="Pending" fill="#6366f1" stackId="a" />
                <Bar dataKey="completed" name="Completed" fill="#22c55e" stackId="a" />
                <Bar dataKey="blocked" name="Blocked" fill="#ef4444" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Detail table */}
          <div className="overflow-x-auto rounded-lg border" data-testid="workload-table">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Role</th>
                  <th className="px-4 py-2 text-right font-medium">Pending</th>
                  <th className="px-4 py-2 text-right font-medium">Completed</th>
                  <th className="px-4 py-2 text-right font-medium">Blocked</th>
                  <th className="px-4 py-2 text-right font-medium">Rate</th>
                  <th className="px-4 py-2 text-right font-medium">Avg Days</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.owner}
                    className="border-t"
                    data-testid={`workload-row-${item.owner}`}
                  >
                    <td className="px-4 py-2 font-medium capitalize">{item.owner}</td>
                    <td className="px-4 py-2 text-right">{item.pending_steps}</td>
                    <td className="px-4 py-2 text-right">{item.completed_steps}</td>
                    <td className="px-4 py-2 text-right">
                      {item.blocked_steps > 0 ? (
                        <Badge variant="destructive" className="text-xs">
                          {item.blocked_steps}
                        </Badge>
                      ) : (
                        item.blocked_steps
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">{pct(item.completion_rate)}</td>
                    <td className="px-4 py-2 text-right">
                      {item.average_completion_days.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Main WorkflowAnalyticsCenter ──────────────────────────────────────────────

interface WorkflowAnalyticsCenterProps {
  workspaceId: string;
}

export function WorkflowAnalyticsCenter({ workspaceId }: WorkflowAnalyticsCenterProps) {
  return (
    <div className="space-y-8 p-6" data-testid="workflow-analytics-center">
      <div className="flex items-center gap-3">
        <Activity className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold">Workflow Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Read-only performance intelligence. No workflows are modified.
          </p>
        </div>
      </div>

      <OverviewSection workspaceId={workspaceId} />
      <TemplateSection workspaceId={workspaceId} />
      <BottleneckSection workspaceId={workspaceId} />
      <TrendSection workspaceId={workspaceId} />
      <WorkloadSection workspaceId={workspaceId} />
    </div>
  );
}
