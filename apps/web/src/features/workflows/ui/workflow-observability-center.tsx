"use client";

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
  Legend,
} from "recharts";
import {
  useObsBottlenecks,
  useObsStepAnalysis,
  useObsOwnerCapacity,
  useObsTemplateCapacity,
  useObsFlowHealth,
} from "@/features/workflows/api/use-workflow-observability";
import type {
  BottleneckObsItem,
  StepAnalysisItem,
  OwnerCapacityItem,
  TemplateCapacityItem,
} from "@/features/workflows/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function days(value: number): string {
  return `${value.toFixed(1)}d`;
}

function score(value: number): string {
  return value.toFixed(1);
}

function capacityColor(rating: string): string {
  if (rating === "high") return "bg-red-100 text-red-800";
  if (rating === "medium") return "bg-yellow-100 text-yellow-800";
  return "bg-green-100 text-green-800";
}

function capacityScoreColor(s: number): string {
  if (s >= 75) return "bg-green-100";
  if (s >= 40) return "bg-yellow-100";
  return "bg-red-100";
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold" data-testid={testId}>
        {value}
      </p>
    </div>
  );
}

// ── OverviewSection ───────────────────────────────────────────────────────────

function OverviewSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useObsFlowHealth(workspaceId);

  if (isLoading) {
    return <p data-testid="overview-loading">Loading overview…</p>;
  }
  if (error) {
    return <p data-testid="overview-error">Failed to load flow health.</p>;
  }

  const d = data?.data;
  return (
    <section aria-labelledby="overview-heading" data-testid="overview-section">
      <h2 id="overview-heading" className="mb-4 text-lg font-semibold">
        Flow Health Overview
      </h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label="Healthy Flows"
          value={d ? String(d.healthy_flows) : "—"}
          testId="stat-healthy-flows"
        />
        <StatCard
          label="Warning Flows"
          value={d ? String(d.warning_flows) : "—"}
          testId="stat-warning-flows"
        />
        <StatCard
          label="Critical Flows"
          value={d ? String(d.critical_flows) : "—"}
          testId="stat-critical-flows"
        />
        <StatCard
          label="Avg Step Days"
          value={d ? days(d.average_step_completion_days) : "—"}
          testId="stat-avg-step-days"
        />
        <StatCard
          label="Avg Run Days"
          value={d ? days(d.average_run_completion_days) : "—"}
          testId="stat-avg-run-days"
        />
        <StatCard
          label="Health Score"
          value={d ? score(d.flow_health_score) : "—"}
          testId="stat-health-score"
        />
      </div>
    </section>
  );
}

// ── BottleneckSection ─────────────────────────────────────────────────────────

function BottleneckSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useObsBottlenecks(workspaceId);

  if (isLoading) {
    return <p data-testid="bottleneck-loading">Loading bottlenecks…</p>;
  }
  if (error) {
    return <p data-testid="bottleneck-error">Failed to load bottlenecks.</p>;
  }

  const items: BottleneckObsItem[] = data?.data?.items ?? [];

  return (
    <section aria-labelledby="bottleneck-heading">
      <h2 id="bottleneck-heading" className="mb-4 text-lg font-semibold">
        Bottleneck Rankings
      </h2>
      {items.length === 0 ? (
        <p data-testid="bottleneck-empty">No bottleneck data available.</p>
      ) : (
        <>
          <div className="mb-6 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={items}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="template_name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="bottleneck_score" name="Bottleneck Score" fill="#f97316" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full text-sm" data-testid="bottleneck-table">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-2 pr-4">Template</th>
                <th className="pb-2 pr-4">Slowest Step</th>
                <th className="pb-2 pr-4">Avg Days</th>
                <th className="pb-2 pr-4">Max Days</th>
                <th className="pb-2 pr-4">Runs Affected</th>
                <th className="pb-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr
                  key={idx}
                  className="border-b last:border-0"
                  data-testid={`bottleneck-row-${idx}`}
                >
                  <td className="py-2 pr-4 font-medium">{item.template_name}</td>
                  <td className="py-2 pr-4">{item.slowest_step}</td>
                  <td className="py-2 pr-4">{days(item.average_days)}</td>
                  <td className="py-2 pr-4">{days(item.max_days)}</td>
                  <td className="py-2 pr-4">{item.runs_affected}</td>
                  <td className="py-2">{score(item.bottleneck_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ── StepAnalysisSection ───────────────────────────────────────────────────────

function StepAnalysisSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useObsStepAnalysis(workspaceId);

  if (isLoading) {
    return <p data-testid="step-analysis-loading">Loading step analysis…</p>;
  }
  if (error) {
    return <p data-testid="step-analysis-error">Failed to load step analysis.</p>;
  }

  const items: StepAnalysisItem[] = data?.data?.items ?? [];

  return (
    <section aria-labelledby="step-analysis-heading">
      <h2 id="step-analysis-heading" className="mb-4 text-lg font-semibold">
        Step Analysis
      </h2>
      {items.length === 0 ? (
        <p data-testid="step-analysis-empty">No step data available.</p>
      ) : (
        <>
          <div className="mb-6 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={items}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="step_name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="average_completion_days" name="Avg Days" fill="#6366f1" />
                <Bar dataKey="blocked_count" name="Blocked" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full text-sm" data-testid="step-analysis-table">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-2 pr-4">Step</th>
                <th className="pb-2 pr-4">Completed</th>
                <th className="pb-2 pr-4">Avg Days</th>
                <th className="pb-2 pr-4">Median Days</th>
                <th className="pb-2 pr-4">Blocked</th>
                <th className="pb-2 pr-4">Skip Rate</th>
                <th className="pb-2">Completion Rate</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr
                  key={idx}
                  className="border-b last:border-0"
                  data-testid={`step-row-${idx}`}
                >
                  <td className="py-2 pr-4 font-medium">{item.step_name}</td>
                  <td className="py-2 pr-4">{item.completed_count}</td>
                  <td className="py-2 pr-4">{days(item.average_completion_days)}</td>
                  <td className="py-2 pr-4">{days(item.median_completion_days)}</td>
                  <td className="py-2 pr-4">{item.blocked_count}</td>
                  <td className="py-2 pr-4">{pct(item.skip_rate)}</td>
                  <td className="py-2">{pct(item.completion_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ── OwnerCapacitySection ──────────────────────────────────────────────────────

function OwnerCapacitySection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useObsOwnerCapacity(workspaceId);

  if (isLoading) {
    return <p data-testid="owner-capacity-loading">Loading owner capacity…</p>;
  }
  if (error) {
    return <p data-testid="owner-capacity-error">Failed to load owner capacity.</p>;
  }

  const items: OwnerCapacityItem[] = data?.data?.items ?? [];

  return (
    <section aria-labelledby="owner-capacity-heading">
      <h2 id="owner-capacity-heading" className="mb-4 text-lg font-semibold">
        Owner Capacity
      </h2>
      {items.length === 0 ? (
        <p data-testid="owner-capacity-empty">No owner capacity data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="owner-capacity-table">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2 pr-4">Role</th>
              <th className="pb-2 pr-4">Assigned</th>
              <th className="pb-2 pr-4">Completed</th>
              <th className="pb-2 pr-4">Blocked</th>
              <th className="pb-2 pr-4">Avg Days</th>
              <th className="pb-2">Capacity</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr
                key={idx}
                className="border-b last:border-0"
                data-testid={`owner-row-${idx}`}
              >
                <td className="py-2 pr-4 font-medium capitalize">{item.owner_role}</td>
                <td className="py-2 pr-4">{item.assigned_steps}</td>
                <td className="py-2 pr-4">{item.completed_steps}</td>
                <td className="py-2 pr-4">{item.blocked_steps}</td>
                <td className="py-2 pr-4">{days(item.average_completion_days)}</td>
                <td className="py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-semibold ${capacityScoreColor(item.capacity_score)}`}
                    data-testid={`owner-capacity-score-${idx}`}
                  >
                    {score(item.capacity_score)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── TemplateCapacitySection ───────────────────────────────────────────────────

function TemplateCapacitySection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useObsTemplateCapacity(workspaceId);

  if (isLoading) {
    return <p data-testid="template-capacity-loading">Loading template capacity…</p>;
  }
  if (error) {
    return <p data-testid="template-capacity-error">Failed to load template capacity.</p>;
  }

  const items: TemplateCapacityItem[] = data?.data?.items ?? [];

  return (
    <section aria-labelledby="template-capacity-heading">
      <h2 id="template-capacity-heading" className="mb-4 text-lg font-semibold">
        Template Capacity
      </h2>
      {items.length === 0 ? (
        <p data-testid="template-capacity-empty">No template capacity data available.</p>
      ) : (
        <>
          <div className="mb-6 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={items}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="template_name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="average_parallel_runs"
                  name="Avg Parallel Runs"
                  stroke="#8b5cf6"
                />
                <Line
                  type="monotone"
                  dataKey="average_completion_days"
                  name="Avg Completion Days"
                  stroke="#06b6d4"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full text-sm" data-testid="template-capacity-table">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-2 pr-4">Template</th>
                <th className="pb-2 pr-4">Active</th>
                <th className="pb-2 pr-4">Completed</th>
                <th className="pb-2 pr-4">Avg Parallel</th>
                <th className="pb-2 pr-4">Avg Days</th>
                <th className="pb-2">Rating</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr
                  key={idx}
                  className="border-b last:border-0"
                  data-testid={`template-capacity-row-${idx}`}
                >
                  <td className="py-2 pr-4 font-medium">{item.template_name}</td>
                  <td className="py-2 pr-4">{item.active_runs}</td>
                  <td className="py-2 pr-4">{item.completed_runs}</td>
                  <td className="py-2 pr-4">{item.average_parallel_runs.toFixed(2)}</td>
                  <td className="py-2 pr-4">{days(item.average_completion_days)}</td>
                  <td className="py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold capitalize ${capacityColor(item.capacity_rating)}`}
                      data-testid={`template-rating-${idx}`}
                    >
                      {item.capacity_rating}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

// ── IntegritySection ──────────────────────────────────────────────────────────

function IntegritySection({ workspaceId }: { workspaceId: string }) {
  const { data } = useObsFlowHealth(workspaceId);
  const d = data?.data;

  if (!d?.data_integrity_warning) return null;

  return (
    <section data-testid="integrity-section">
      <div
        className="rounded-md border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
        data-testid="integrity-banner"
      >
        <strong>Data integrity warning:</strong> Some workflow runs have
        inconsistent timestamps (completed_at &lt; started_at). Timing metrics
        may be understated. No data has been modified.
      </div>
    </section>
  );
}

// ── Root component ────────────────────────────────────────────────────────────

export function WorkflowObservabilityCenter({
  workspaceId,
}: {
  workspaceId: string;
}) {
  return (
    <div
      className="space-y-10 p-6"
      data-testid="workflow-observability-center"
    >
      <header>
        <h1 className="text-2xl font-bold">Workflow Observability</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Where workflows spend the most time and how workload is distributed.
          Read-only. Managers act on insights.
        </p>
      </header>

      <OverviewSection workspaceId={workspaceId} />
      <BottleneckSection workspaceId={workspaceId} />
      <StepAnalysisSection workspaceId={workspaceId} />
      <OwnerCapacitySection workspaceId={workspaceId} />
      <TemplateCapacitySection workspaceId={workspaceId} />
      <IntegritySection workspaceId={workspaceId} />
    </div>
  );
}
