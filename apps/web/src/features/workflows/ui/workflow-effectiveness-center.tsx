"use client";

import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { TrendingUp, AlertTriangle, CheckCircle2, XCircle, Clock } from "lucide-react";
import {
  useEffectivenessSummary,
  useEffectivenessTemplates,
  useEffectivenessEntities,
  useEffectivenessDuration,
  useEffectivenessCompletion,
} from "@/features/workflows/api/use-workflow-effectiveness";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function days(value: number) {
  return `${value.toFixed(1)}d`;
}

function score(value: number) {
  return `${value.toFixed(1)}`;
}

// ── Overview ──────────────────────────────────────────────────────────────────

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
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold" data-testid={testId}>
        {value}
      </p>
    </div>
  );
}

function OverviewSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useEffectivenessSummary(workspaceId);

  if (isLoading) {
    return (
      <section data-testid="overview-section">
        <h2 className="mb-4 text-lg font-semibold">Overview</h2>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </section>
    );
  }
  if (error) {
    return (
      <section data-testid="overview-section">
        <h2 className="mb-4 text-lg font-semibold">Overview</h2>
        <p className="text-sm text-destructive">Failed to load overview.</p>
      </section>
    );
  }

  const d = data?.data;
  return (
    <section data-testid="overview-section">
      <h2 className="mb-4 text-lg font-semibold">Overview</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Completed Workflows"
          value={d ? String(d.total_completed) : "—"}
          testId="stat-total-completed"
        />
        <StatCard
          label="Avg. Completion"
          value={d ? days(d.average_completion_days) : "—"}
          testId="stat-avg-completion-days"
        />
        <StatCard
          label="Avg. Step Completion"
          value={d ? days(d.average_step_completion_days) : "—"}
          testId="stat-avg-step-days"
        />
        <StatCard
          label="Entity Coverage"
          value={d ? pct(d.entity_coverage) : "—"}
          testId="stat-entity-coverage"
        />
        <StatCard
          label="Fast Completion Rate"
          value={d ? pct(d.fast_completion_rate) : "—"}
          testId="stat-fast-rate"
        />
        <StatCard
          label="Slow Completion Rate"
          value={d ? pct(d.slow_completion_rate) : "—"}
          testId="stat-slow-rate"
        />
        <StatCard
          label="Effectiveness Score"
          value={d ? score(d.overall_effectiveness_score) : "—"}
          testId="stat-overall-score"
        />
      </div>
    </section>
  );
}

// ── Template Rankings ─────────────────────────────────────────────────────────

function TemplateRankingsSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useEffectivenessTemplates(workspaceId);

  if (isLoading) {
    return (
      <section data-testid="template-rankings-section">
        <h2 className="mb-4 text-lg font-semibold">Template Rankings</h2>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </section>
    );
  }
  if (error) {
    return (
      <section data-testid="template-rankings-section">
        <h2 className="mb-4 text-lg font-semibold">Template Rankings</h2>
        <p className="text-sm text-destructive">Failed to load template data.</p>
      </section>
    );
  }

  const items = data?.data?.items ?? [];
  return (
    <section data-testid="template-rankings-section">
      <h2 className="mb-4 text-lg font-semibold">Template Rankings</h2>
      {items.length > 0 && (
        <div className="mb-4 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={items} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="template_name" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="effectiveness_score" fill="#6366f1" name="Score" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No template data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="template-rankings-table">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2">Template</th>
              <th className="pb-2 text-right">Runs</th>
              <th className="pb-2 text-right">Completed</th>
              <th className="pb-2 text-right">Rate</th>
              <th className="pb-2 text-right">Avg. Duration</th>
              <th className="pb-2 text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr
                key={item.template_id ?? item.template_name}
                className="border-b"
                data-testid={`template-row-${idx}`}
              >
                <td className="py-2">{item.template_name}</td>
                <td className="py-2 text-right">{item.runs}</td>
                <td className="py-2 text-right">{item.completed}</td>
                <td className="py-2 text-right">{pct(item.completion_rate)}</td>
                <td className="py-2 text-right">{days(item.average_duration)}</td>
                <td className="py-2 text-right font-medium">{score(item.effectiveness_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Entity Effectiveness ──────────────────────────────────────────────────────

function EntityEffectivenessSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useEffectivenessEntities(workspaceId);

  if (isLoading) {
    return (
      <section data-testid="entity-effectiveness-section">
        <h2 className="mb-4 text-lg font-semibold">Entity Effectiveness</h2>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </section>
    );
  }
  if (error) {
    return (
      <section data-testid="entity-effectiveness-section">
        <h2 className="mb-4 text-lg font-semibold">Entity Effectiveness</h2>
        <p className="text-sm text-destructive">Failed to load entity data.</p>
      </section>
    );
  }

  const items = data?.data?.items ?? [];
  const chartData = items.map((i) => ({
    name: i.entity_type,
    rate: parseFloat((i.completion_rate * 100).toFixed(1)),
  }));

  return (
    <section data-testid="entity-effectiveness-section">
      <h2 className="mb-4 text-lg font-semibold">Entity Effectiveness</h2>
      {items.length > 0 && (
        <div className="mb-4 h-48" data-testid="entity-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="rate" fill="#22c55e" name="Completion %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No entity data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="entity-table">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2">Entity Type</th>
              <th className="pb-2 text-right">Workflows</th>
              <th className="pb-2 text-right">Completion Rate</th>
              <th className="pb-2 text-right">Avg. Duration</th>
              <th className="pb-2 text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={item.entity_type} className="border-b" data-testid={`entity-row-${idx}`}>
                <td className="py-2 capitalize">{item.entity_type}</td>
                <td className="py-2 text-right">{item.workflow_count}</td>
                <td className="py-2 text-right">{pct(item.completion_rate)}</td>
                <td className="py-2 text-right">{days(item.average_duration)}</td>
                <td className="py-2 text-right font-medium">{score(item.effectiveness_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Duration Analysis ─────────────────────────────────────────────────────────

function DurationAnalysisSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useEffectivenessDuration(workspaceId);

  if (isLoading) {
    return (
      <section data-testid="duration-analysis-section">
        <h2 className="mb-4 text-lg font-semibold">Duration Analysis</h2>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </section>
    );
  }
  if (error) {
    return (
      <section data-testid="duration-analysis-section">
        <h2 className="mb-4 text-lg font-semibold">Duration Analysis</h2>
        <p className="text-sm text-destructive">Failed to load duration data.</p>
      </section>
    );
  }

  const buckets = data?.data?.buckets ?? [];
  const lineData = buckets.map((b) => ({
    name: b.label,
    rate: parseFloat((b.completion_rate * 100).toFixed(1)),
  }));

  return (
    <section data-testid="duration-analysis-section">
      <h2 className="mb-4 text-lg font-semibold">Duration Analysis</h2>
      {buckets.length > 0 && (
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="h-48" data-testid="duration-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={buckets} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="completed" fill="#0ea5e9" name="Completed" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="h-48" data-testid="duration-line-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Line type="monotone" dataKey="rate" stroke="#f59e0b" name="Completion %" dot />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {buckets.length === 0 ? (
        <p className="text-sm text-muted-foreground">No duration data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="duration-table">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2">Duration Bucket</th>
              <th className="pb-2 text-right">Completed</th>
              <th className="pb-2 text-right">Completion Rate</th>
              <th className="pb-2 text-right">Avg. Steps</th>
              <th className="pb-2 text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket, idx) => (
              <tr key={bucket.label} className="border-b" data-testid={`duration-row-${idx}`}>
                <td className="py-2">{bucket.label}</td>
                <td className="py-2 text-right">{bucket.completed}</td>
                <td className="py-2 text-right">{pct(bucket.completion_rate)}</td>
                <td className="py-2 text-right">{bucket.average_steps.toFixed(1)}</td>
                <td className="py-2 text-right font-medium">{score(bucket.effectiveness_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Completion Analysis ───────────────────────────────────────────────────────

const COMPLETION_COLORS: Record<string, string> = {
  completed: "#22c55e",
  cancelled: "#ef4444",
  active: "#f59e0b",
};

const COMPLETION_ICONS: Record<string, React.ReactNode> = {
  completed: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  cancelled: <XCircle className="h-4 w-4 text-red-500" />,
  active: <Clock className="h-4 w-4 text-amber-500" />,
};

function CompletionAnalysisSection({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, error } = useEffectivenessCompletion(workspaceId);

  if (isLoading) {
    return (
      <section data-testid="completion-analysis-section">
        <h2 className="mb-4 text-lg font-semibold">Completion Analysis</h2>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </section>
    );
  }
  if (error) {
    return (
      <section data-testid="completion-analysis-section">
        <h2 className="mb-4 text-lg font-semibold">Completion Analysis</h2>
        <p className="text-sm text-destructive">Failed to load completion data.</p>
      </section>
    );
  }

  const items = data?.data?.items ?? [];
  return (
    <section data-testid="completion-analysis-section">
      <h2 className="mb-4 text-lg font-semibold">Completion Analysis</h2>
      {items.length > 0 && (
        <div className="mb-4 h-48" data-testid="completion-chart">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={items}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ status, count }) => `${status}: ${count}`}
              >
                {items.map((entry) => (
                  <Cell
                    key={entry.status}
                    fill={COMPLETION_COLORS[entry.status] ?? "#94a3b8"}
                  />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No completion data available.</p>
      ) : (
        <table className="w-full text-sm" data-testid="completion-table">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="pb-2">Status</th>
              <th className="pb-2 text-right">Count</th>
              <th className="pb-2 text-right">Avg. Duration</th>
              <th className="pb-2 text-right">Score</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={item.status} className="border-b" data-testid={`completion-row-${idx}`}>
                <td className="py-2">
                  <span className="flex items-center gap-1.5 capitalize">
                    {COMPLETION_ICONS[item.status]}
                    {item.status}
                  </span>
                </td>
                <td className="py-2 text-right">{item.count}</td>
                <td className="py-2 text-right">
                  {item.average_duration > 0 ? days(item.average_duration) : "—"}
                </td>
                <td className="py-2 text-right font-medium">{score(item.effectiveness_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ── Integrity Warning ─────────────────────────────────────────────────────────

function IntegritySection({ workspaceId }: { workspaceId: string }) {
  const { data } = useEffectivenessSummary(workspaceId);
  if (!data?.data?.data_integrity_warning) return null;

  return (
    <section data-testid="integrity-section">
      <div
        className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4"
        data-testid="integrity-banner"
      >
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="text-sm font-medium text-amber-800">Data Integrity Warning</p>
          <p className="mt-1 text-xs text-amber-700">
            Some workflows have <code>completed_at</code> earlier than{" "}
            <code>started_at</code>. These are excluded from duration averages but
            may indicate data quality issues. No automated repair is applied.
          </p>
        </div>
      </div>
    </section>
  );
}

// ── Root component ────────────────────────────────────────────────────────────

interface WorkflowEffectivenessCenterProps {
  workspaceId: string;
}

export function WorkflowEffectivenessCenter({
  workspaceId,
}: WorkflowEffectivenessCenterProps) {
  return (
    <div
      className="space-y-8 p-6"
      data-testid="workflow-effectiveness-center"
    >
      <div className="flex items-center gap-3">
        <TrendingUp className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Workflow Effectiveness</h1>
      </div>

      <IntegritySection workspaceId={workspaceId} />
      <OverviewSection workspaceId={workspaceId} />
      <TemplateRankingsSection workspaceId={workspaceId} />
      <EntityEffectivenessSection workspaceId={workspaceId} />
      <DurationAnalysisSection workspaceId={workspaceId} />
      <CompletionAnalysisSection workspaceId={workspaceId} />
    </div>
  );
}
