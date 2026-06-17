"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AlertCircle, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useAnalyticsFunnel,
  useAnalyticsSummary,
  useAnalyticsTrend,
} from "@/features/analytics/api/use-analytics";

// ── KPI card ──────────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sub,
  isLoading,
}: {
  label: string;
  value: string | number;
  sub?: string;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <>
            <p className="text-2xl font-bold">{value}</p>
            {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Funnel bar ────────────────────────────────────────────────────────────────

function FunnelRow({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value.toLocaleString()}</span>
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

// ── Main panel ────────────────────────────────────────────────────────────────

export function AnalyticsPanel() {
  const { workspaceId } = useWorkspace();

  const summary = useAnalyticsSummary(30);
  const trend = useAnalyticsTrend(30);
  const funnel = useAnalyticsFunnel(workspaceId);

  const s = summary.data;
  const f = funnel.data;
  const trendRows = trend.data ?? [];

  // Reverse so chart goes oldest → newest left-to-right
  const chartData = [...trendRows].reverse().map((r) => ({
    date: r.rollup_date.slice(5), // MM-DD
    sent: r.outreach_sent,
    replied: r.outreach_replied,
    booked: r.leads_booked,
  }));

  const summaryLoading = summary.isLoading;
  const summaryError = summary.isError;

  if (summaryError) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load analytics. Try refreshing.
      </div>
    );
  }

  const funnelMax = f?.contacts ?? 0;

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KpiCard
          label="Reply Rate (30d)"
          value={s ? `${(s.reply_rate * 100).toFixed(1)}%` : "—"}
          sub={`${s?.total_replied ?? 0} of ${s?.total_sent ?? 0} sent`}
          isLoading={summaryLoading}
        />
        <KpiCard
          label="Meetings (30d)"
          value={s?.meetings_scheduled ?? "—"}
          sub={`${s?.meetings_completed ?? 0} completed`}
          isLoading={summaryLoading}
        />
        <KpiCard
          label="Proposals Sent (30d)"
          value={s?.proposals_sent ?? "—"}
          sub={`${s ? (s.proposal_approval_rate * 100).toFixed(0) : 0}% approval rate`}
          isLoading={summaryLoading}
        />
        <KpiCard
          label="Bookings (30d)"
          value={s?.leads_booked ?? "—"}
          sub={`${s ? (s.booking_rate * 100).toFixed(1) : 0}% close rate`}
          isLoading={summaryLoading}
        />
      </div>

      {/* Trend chart */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 pb-2">
          <TrendingUp className="h-4 w-4 text-primary" />
          <CardTitle className="text-sm">30-Day Outreach Trend</CardTitle>
        </CardHeader>
        <CardContent>
          {trend.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : chartData.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              No trend data yet — check back after your first campaign completes.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={chartData}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  width={28}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12 }}
                  labelStyle={{ fontWeight: 600 }}
                />
                <Line
                  type="monotone"
                  dataKey="sent"
                  name="Sent"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="replied"
                  name="Replied"
                  stroke="#22c55e"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Revenue funnel */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Revenue Funnel</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {funnel.isLoading || !f ? (
            Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))
          ) : (
            <>
              <FunnelRow label="HR Contacts" value={f.contacts} max={funnelMax} />
              <FunnelRow label="Outreach Sent" value={f.outreach_sent} max={funnelMax} />
              <FunnelRow label="Interested Replies" value={f.replies} max={funnelMax} />
              <FunnelRow label="Meetings" value={f.meetings} max={funnelMax} />
              <FunnelRow label="Proposals" value={f.proposals} max={funnelMax} />
              <FunnelRow label="Bookings" value={f.bookings} max={funnelMax} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
