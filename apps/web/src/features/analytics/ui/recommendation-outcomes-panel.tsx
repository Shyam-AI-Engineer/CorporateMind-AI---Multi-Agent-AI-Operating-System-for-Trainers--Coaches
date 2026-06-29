"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useExecutionSummary,
  useRecommendationOutcomes,
} from "@/features/analytics/ui/../api/use-analytics";

function fmt(n: number, decimals = 1): string {
  return n.toFixed(decimals);
}

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

// ── Section 1 — Execution KPI cards ──────────────────────────────────────────

function KpiCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string | number;
  testId: string;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

// ── Section 2 — Execution funnel ──────────────────────────────────────────────

function FunnelStep({
  label,
  value,
  max,
  testId,
}: {
  label: string;
  value: number;
  max: number;
  testId: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  workspaceId: string;
}

export function RecommendationOutcomesPanel({ workspaceId }: Props) {
  const summary = useExecutionSummary(workspaceId);
  const outcomes = useRecommendationOutcomes(workspaceId);

  if (summary.isLoading || outcomes.isLoading) {
    return (
      <div data-testid="outcomes-skeleton" className="space-y-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  if (summary.isError || outcomes.isError) {
    return (
      <div
        data-testid="outcomes-error"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        Failed to load outcome analytics. Try refreshing.
      </div>
    );
  }

  const s = summary.data;
  const o = outcomes.data;

  if (!s || !o) {
    return (
      <div data-testid="outcomes-empty" className="text-sm text-muted-foreground">
        No execution history.
      </div>
    );
  }

  const funnelMax = s.accepted;

  return (
    <div data-testid="recommendation-outcomes-panel" className="space-y-6">

      {/* Section 1 — Execution KPI cards */}
      <section data-testid="kpi-section">
        <h2 className="mb-3 text-sm font-semibold">Execution Summary</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <KpiCard label="Accepted" value={s.accepted} testId="kpi-accepted" />
          <KpiCard label="Completed" value={s.completed} testId="kpi-completed" />
          <KpiCard label="Blocked" value={s.blocked} testId="kpi-blocked" />
          <KpiCard label="Cancelled" value={s.cancelled} testId="kpi-cancelled" />
          <KpiCard label="Completion Rate" value={pct(s.completion_rate)} testId="kpi-completion-rate" />
          <KpiCard label="Work In Progress" value={s.work_in_progress} testId="kpi-wip" />
        </div>
      </section>

      {/* Section 2 — Execution funnel */}
      <section data-testid="funnel-section">
        <h2 className="mb-3 text-sm font-semibold">Execution Funnel</h2>
        <Card>
          <CardContent className="space-y-3 pt-4">
            <FunnelStep label="Accepted" value={s.accepted} max={funnelMax} testId="funnel-accepted" />
            <FunnelStep label="Started" value={s.started} max={funnelMax} testId="funnel-started" />
            <FunnelStep label="Completed" value={s.completed} max={funnelMax} testId="funnel-completed" />
            <FunnelStep label="Cancelled" value={s.cancelled} max={funnelMax} testId="funnel-cancelled" />
            <FunnelStep label="Blocked" value={s.blocked} max={funnelMax} testId="funnel-blocked" />
          </CardContent>
        </Card>
      </section>

      {/* Section 3 — Recommendation type table */}
      <section data-testid="type-table-section">
        <h2 className="mb-3 text-sm font-semibold">Recommendation Type Breakdown</h2>
        {o.by_rec_type.length === 0 ? (
          <p data-testid="type-table-empty" className="text-sm text-muted-foreground">
            No type data yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table
              data-testid="type-table"
              className="w-full text-xs"
            >
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4 text-right">Accepted</th>
                  <th className="py-2 pr-4 text-right">Completed</th>
                  <th className="py-2 pr-4 text-right">Completion %</th>
                  <th className="py-2 pr-4 text-right">Avg Start (days)</th>
                  <th className="py-2 pr-4 text-right">Avg Complete (days)</th>
                  <th className="py-2 pr-4 text-right">Blocked</th>
                  <th className="py-2 text-right">Cancelled</th>
                </tr>
              </thead>
              <tbody>
                {o.by_rec_type.map((row) => (
                  <tr
                    key={row.rec_type}
                    data-testid={`type-row-${row.rec_type}`}
                    className="border-b last:border-0"
                  >
                    <td className="py-2 pr-4 font-medium">{row.rec_type}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{row.accepted}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{row.completed}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {pct(row.completion_rate)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {fmt(row.avg_days_to_start)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {fmt(row.avg_days_to_complete)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">{row.blocked}</td>
                    <td className="py-2 text-right tabular-nums">{row.cancelled}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 4 — Execution health */}
      <section data-testid="health-section">
        <h2 className="mb-3 text-sm font-semibold">Execution Health</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <KpiCard
            label="Avg Days to Start"
            value={fmt(s.avg_days_to_start)}
            testId="health-avg-start"
          />
          <KpiCard
            label="Avg Days to Complete"
            value={fmt(s.avg_days_to_complete)}
            testId="health-avg-complete"
          />
          <KpiCard
            label="Avg Days Blocked"
            value={fmt(s.avg_days_blocked)}
            testId="health-avg-blocked"
          />
          <KpiCard
            label="Overdue Work"
            value={s.overdue}
            testId="health-overdue"
          />
        </div>
      </section>

      {/* Section 5 — Warnings */}
      <section data-testid="warnings-section">
        {s.completed === 0 && (
          <p data-testid="warning-no-completed" className="text-sm text-muted-foreground">
            No completed recommendations yet.
          </p>
        )}
        {s.overdue > 0 && (
          <p data-testid="warning-overdue" className="text-sm text-amber-600">
            {s.overdue} recommendation{s.overdue !== 1 ? "s" : ""} overdue.
          </p>
        )}
        {s.blocked > 0 && (
          <p data-testid="warning-blocked" className="text-sm text-amber-600">
            {s.blocked} recommendation{s.blocked !== 1 ? "s" : ""} blocked.
          </p>
        )}
      </section>

      {/* Section 6 — Empty state when no history at all */}
      {s.accepted === 0 && (
        <section data-testid="no-history-section">
          <p data-testid="no-history-message" className="text-sm text-muted-foreground">
            No execution history.
          </p>
        </section>
      )}

    </div>
  );
}
