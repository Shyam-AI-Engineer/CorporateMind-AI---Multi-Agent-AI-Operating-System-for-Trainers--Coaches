"use client";

import { useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { AlertTriangle, ShieldCheck, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useSLASummary,
  useSLAOverdue,
  useSLATemplates,
  useSLAOwner,
  useSLATrend,
} from "@/features/workflows/api/use-workflow-sla";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function days(value: number) {
  return `${value.toFixed(1)}d`;
}

const PERIOD_OPTIONS = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
] as const;

// ── Overview section ──────────────────────────────────────────────────────────

function OverviewSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useSLASummary(workspaceId);

  return (
    <section data-testid="overview-section">
      <h2 className="mb-4 text-lg font-semibold">SLA Overview</h2>
      {isLoading && (
        <p className="text-sm text-muted-foreground" data-testid="overview-loading">
          Loading…
        </p>
      )}
      {error && !isLoading && (
        <p className="text-sm text-destructive" data-testid="overview-error">
          Failed to load SLA summary.
        </p>
      )}
      {!isLoading && !error && !data && (
        <p className="text-sm text-muted-foreground" data-testid="overview-empty">
          No data available.
        </p>
      )}
      {data && (
        <div data-testid="overview-cards">
          {data.data_integrity_warning && (
            <div
              className="mb-4 flex items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-800"
              data-testid="integrity-warning"
            >
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>
                Data integrity issue detected: one or more runs have{" "}
                <strong>completed_at &lt; started_at</strong>. No data has been
                modified — this is a read-only report.
              </span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              testId="stat-active-runs"
              label="Active Runs"
              value={String(data.active_runs)}
            />
            <StatCard
              testId="stat-overdue-runs"
              label="Overdue Runs"
              value={String(data.overdue_runs)}
              highlight={data.overdue_runs > 0}
            />
            <StatCard
              testId="stat-compliance-rate"
              label="SLA Compliance"
              value={pct(data.sla_compliance_rate)}
            />
            <StatCard
              testId="stat-avg-days-open"
              label="Avg Days Open"
              value={days(data.average_days_open)}
            />
            <StatCard
              testId="stat-healthy-runs"
              label="Healthy"
              value={String(data.healthy_runs)}
            />
            <StatCard
              testId="stat-warning-overdue"
              label="Warning (30–60d)"
              value={String(data.warning_overdue)}
              highlight={data.warning_overdue > 0}
            />
            <StatCard
              testId="stat-critical-overdue"
              label="Critical (>60d)"
              value={String(data.critical_overdue)}
              highlight={data.critical_overdue > 0}
            />
            <StatCard
              testId="stat-avg-days-overdue"
              label="Avg Days Overdue"
              value={days(data.average_days_overdue)}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function StatCard({
  testId,
  label,
  value,
  highlight = false,
}: {
  testId: string;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${highlight ? "border-destructive/40 bg-destructive/5" : ""}`}
      data-testid={testId}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${highlight ? "text-destructive" : ""}`}>
        {value}
      </p>
    </div>
  );
}

// ── Overdue table section ─────────────────────────────────────────────────────

function OverdueSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useSLAOverdue(workspaceId);

  return (
    <section data-testid="overdue-section">
      <h2 className="mb-4 text-lg font-semibold">Overdue Runs</h2>
      {isLoading && (
        <p className="text-sm text-muted-foreground" data-testid="overdue-loading">
          Loading…
        </p>
      )}
      {error && !isLoading && (
        <p className="text-sm text-destructive" data-testid="overdue-error">
          Failed to load overdue runs.
        </p>
      )}
      {!isLoading && !error && data && data.items.length === 0 && (
        <div
          className="flex items-center gap-2 rounded-md border border-green-300 bg-green-50 p-4 text-sm text-green-800"
          data-testid="overdue-empty"
        >
          <ShieldCheck className="h-4 w-4 shrink-0" />
          <span>All active runs are within SLA — no overdue workflows.</span>
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-md border" data-testid="overdue-table">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Run</th>
                <th className="px-4 py-2 text-left font-medium">Template</th>
                <th className="px-4 py-2 text-left font-medium">Entity</th>
                <th className="px-4 py-2 text-right font-medium">Days Open</th>
                <th className="px-4 py-2 text-right font-medium">Days Overdue</th>
                <th className="px-4 py-2 text-left font-medium">Current Step</th>
                <th className="px-4 py-2 text-left font-medium">Owner</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, idx) => (
                <tr
                  key={item.run_id}
                  className="border-b last:border-0 hover:bg-muted/30"
                  data-testid={`overdue-row-${idx}`}
                >
                  <td className="px-4 py-2 font-medium">{item.title}</td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {item.template_name ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {item.entity_title ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-right">{days(item.days_open)}</td>
                  <td className="px-4 py-2 text-right">
                    <Badge
                      variant="destructive"
                      className="text-xs"
                      data-testid={`overdue-badge-${idx}`}
                    >
                      +{days(item.days_overdue)}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {item.current_step ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    {item.owner_role ? (
                      <Badge variant="secondary" className="text-xs">
                        {item.owner_role}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ── Template SLA section ──────────────────────────────────────────────────────

function TemplateSLASection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useSLATemplates(workspaceId);

  return (
    <section data-testid="template-sla-section">
      <h2 className="mb-4 text-lg font-semibold">SLA by Template</h2>
      {isLoading && (
        <p className="text-sm text-muted-foreground" data-testid="template-sla-loading">
          Loading…
        </p>
      )}
      {error && !isLoading && (
        <p className="text-sm text-destructive" data-testid="template-sla-error">
          Failed to load template SLA data.
        </p>
      )}
      {!isLoading && !error && data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="template-sla-empty">
          No active runs to analyse.
        </p>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-md border" data-testid="template-sla-table">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Template</th>
                <th className="px-4 py-2 text-right font-medium">Runs</th>
                <th className="px-4 py-2 text-right font-medium">Overdue</th>
                <th className="px-4 py-2 text-right font-medium">Compliance</th>
                <th className="px-4 py-2 text-right font-medium">Avg Duration</th>
                <th className="px-4 py-2 text-right font-medium">Avg Overdue</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, idx) => (
                <tr
                  key={item.template_id ?? "none"}
                  className="border-b last:border-0 hover:bg-muted/30"
                  data-testid={`template-sla-row-${idx}`}
                >
                  <td className="px-4 py-2 font-medium">{item.template_name}</td>
                  <td className="px-4 py-2 text-right">{item.runs}</td>
                  <td className="px-4 py-2 text-right">{item.overdue}</td>
                  <td className="px-4 py-2 text-right">{pct(item.compliance_rate)}</td>
                  <td className="px-4 py-2 text-right">{days(item.average_duration_days)}</td>
                  <td className="px-4 py-2 text-right">{days(item.average_days_overdue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ── Owner SLA section ─────────────────────────────────────────────────────────

function OwnerSLASection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useSLAOwner(workspaceId);
  const chartData = data?.items.map((item) => ({
    name: item.owner_role,
    assigned: item.assigned_steps,
    completed: item.completed_steps,
    overdue: item.overdue_steps,
  }));

  return (
    <section data-testid="owner-sla-section">
      <h2 className="mb-4 text-lg font-semibold">SLA by Owner Role</h2>
      {isLoading && (
        <p className="text-sm text-muted-foreground" data-testid="owner-sla-loading">
          Loading…
        </p>
      )}
      {error && !isLoading && (
        <p className="text-sm text-destructive" data-testid="owner-sla-error">
          Failed to load owner SLA data.
        </p>
      )}
      {!isLoading && !error && data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="owner-sla-empty">
          No step data available.
        </p>
      )}
      {data && data.items.length > 0 && (
        <div className="space-y-4">
          <div className="h-56" data-testid="owner-sla-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={80} />
                <Tooltip />
                <Bar dataKey="completed" fill="#22c55e" name="Completed" />
                <Bar dataKey="overdue" fill="#ef4444" name="Overdue" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="overflow-x-auto rounded-md border" data-testid="owner-sla-table">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Owner Role</th>
                  <th className="px-4 py-2 text-right font-medium">Assigned</th>
                  <th className="px-4 py-2 text-right font-medium">Completed</th>
                  <th className="px-4 py-2 text-right font-medium">Overdue</th>
                  <th className="px-4 py-2 text-right font-medium">Compliance</th>
                  <th className="px-4 py-2 text-right font-medium">Avg Days</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item, idx) => (
                  <tr
                    key={item.owner_role}
                    className="border-b last:border-0 hover:bg-muted/30"
                    data-testid={`owner-sla-row-${idx}`}
                  >
                    <td className="px-4 py-2 font-medium">
                      <Badge variant="outline" className="text-xs">
                        {item.owner_role}
                      </Badge>
                    </td>
                    <td className="px-4 py-2 text-right">{item.assigned_steps}</td>
                    <td className="px-4 py-2 text-right">{item.completed_steps}</td>
                    <td className="px-4 py-2 text-right">{item.overdue_steps}</td>
                    <td className="px-4 py-2 text-right">{pct(item.compliance_rate)}</td>
                    <td className="px-4 py-2 text-right">
                      {days(item.average_completion_days)}
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

// ── SLA Trend section ─────────────────────────────────────────────────────────

function TrendSection({ workspaceId }: { workspaceId: string }) {
  const [period, setPeriod] = useState<7 | 30 | 90>(30);
  const { data, isLoading, error } = useSLATrend(workspaceId, period);

  return (
    <section data-testid="trend-section">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">SLA Health Trend</h2>
        <div className="flex gap-1" data-testid="period-selector">
          {PERIOD_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={period === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => setPeriod(opt.value)}
              data-testid={`period-btn-${opt.value}`}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>
      {isLoading && (
        <p className="text-sm text-muted-foreground" data-testid="trend-loading">
          Loading…
        </p>
      )}
      {error && !isLoading && (
        <p className="text-sm text-destructive" data-testid="trend-error">
          Failed to load trend data.
        </p>
      )}
      {!isLoading && !error && data && data.buckets.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="trend-empty">
          No trend data for this period.
        </p>
      )}
      {data && data.buckets.length > 0 && (
        <div className="h-64" data-testid="trend-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.buckets}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="healthy"
                stackId="1"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.6}
                name="Healthy"
              />
              <Area
                type="monotone"
                dataKey="warning"
                stackId="1"
                stroke="#f59e0b"
                fill="#f59e0b"
                fillOpacity={0.6}
                name="Warning"
              />
              <Area
                type="monotone"
                dataKey="critical"
                stackId="1"
                stroke="#ef4444"
                fill="#ef4444"
                fillOpacity={0.6}
                name="Critical"
              />
              <Area
                type="monotone"
                dataKey="completed"
                stackId="2"
                stroke="#6366f1"
                fill="#6366f1"
                fillOpacity={0.4}
                name="Completed"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

// ── Integrity warning section (standalone) ────────────────────────────────────

function IntegritySection({ workspaceId }: { workspaceId: string }) {
  const { data } = useSLASummary(workspaceId);

  if (!data?.data_integrity_warning) return null;

  return (
    <section data-testid="integrity-section">
      <div
        className="flex items-start gap-3 rounded-md border border-yellow-300 bg-yellow-50 p-4 text-sm text-yellow-800"
        data-testid="integrity-banner"
      >
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">Data Integrity Warning</p>
          <p className="mt-1">
            One or more workflow runs have <code>completed_at</code> earlier than{" "}
            <code>started_at</code>, producing negative durations. SLA calculations
            exclude these values but SLA totals may be understated. No data has
            been modified.
          </p>
        </div>
      </div>
    </section>
  );
}

// ── Root component ────────────────────────────────────────────────────────────

export function WorkflowSLACenter({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="space-y-8 p-6" data-testid="workflow-sla-center">
      <div>
        <h1 className="text-2xl font-bold">Workflow SLA Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Read-only SLA compliance reporting. Default workflow SLA: 30 days.
          Default step SLA: 7 days. Nothing is escalated automatically.
        </p>
      </div>
      <OverviewSection workspaceId={workspaceId} />
      <OverdueSection workspaceId={workspaceId} />
      <TemplateSLASection workspaceId={workspaceId} />
      <OwnerSLASection workspaceId={workspaceId} />
      <TrendSection workspaceId={workspaceId} />
      <IntegritySection workspaceId={workspaceId} />
    </div>
  );
}
