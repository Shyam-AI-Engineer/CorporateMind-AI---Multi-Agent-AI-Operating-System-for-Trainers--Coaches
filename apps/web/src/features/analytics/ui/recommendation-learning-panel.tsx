"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useRecommendationLearning,
  useRecommendationVersionHistory,
} from "@/features/analytics/api/use-analytics";
import type { LearningVersionOut, LearningComparisonOut } from "@/features/analytics/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtDelta(value: number | null | undefined, unit = "pts"): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)} ${unit}`;
}

function deltaClass(value: number | null | undefined): string {
  if (value == null) return "";
  if (value > 0) return "text-green-600";
  if (value < 0) return "text-red-500";
  return "text-muted-foreground";
}

// ── Section 1: Version Comparison cards ──────────────────────────────────────

function ComparisonSection({
  currentVersion,
  previousVersion,
  comparison,
}: {
  currentVersion: string | null;
  previousVersion: string | null;
  comparison: LearningComparisonOut | null;
}) {
  return (
    <section data-testid="comparison-section">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Version Comparison
      </h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        <Card data-testid="card-current-version">
          <CardHeader className="pb-1">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Current Version
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-bold tabular-nums">
              {currentVersion ?? "—"}
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-previous-version">
          <CardHeader className="pb-1">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Previous Version
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-bold tabular-nums">
              {previousVersion ?? "—"}
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-quality-delta">
          <CardHeader className="pb-1">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Quality Δ
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-lg font-bold tabular-nums ${deltaClass(comparison?.quality_delta)}`}>
              {fmtDelta(comparison?.quality_delta)}
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-success-delta">
          <CardHeader className="pb-1">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Success Δ
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-lg font-bold tabular-nums ${deltaClass(comparison?.success_delta)}`}>
              {fmtDelta(comparison?.success_delta, "%")}
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-confidence-delta">
          <CardHeader className="pb-1">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Confidence Δ
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-lg font-bold tabular-nums ${deltaClass(comparison?.confidence_delta)}`}>
              {fmtDelta(comparison?.confidence_delta)}
            </p>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

// ── Section 2: Version Timeline table ────────────────────────────────────────

function TimelineSection({ versions }: { versions: LearningVersionOut[] }) {
  return (
    <section data-testid="timeline-section">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Version Timeline
      </h3>
      {versions.length === 0 ? (
        <p data-testid="timeline-empty" className="text-sm text-muted-foreground">
          No version history yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table
            data-testid="version-table"
            className="w-full text-sm"
          >
            <thead className="bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-muted-foreground">Version</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Generated</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Adopted</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Completed</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Successful</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Quality</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr
                  key={v.version}
                  data-testid={`version-row-${v.version}`}
                  className="border-t"
                >
                  <td className="px-3 py-2 font-mono text-xs">{v.version}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{v.recommendations_generated}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{v.acted}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{v.completed}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{v.successful}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {v.quality_score != null ? v.quality_score.toFixed(1) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{v.avg_confidence.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ── Section 3: Improvement Trend chart ───────────────────────────────────────

function TrendSection({ versions }: { versions: LearningVersionOut[] }) {
  // Oldest first for the chart so time flows left → right
  const chartData = [...versions].reverse().map((v) => ({
    version: v.version,
    confidence: v.avg_confidence,
    quality: v.quality_score ?? 0,
    acted: v.acted,
  }));

  return (
    <section data-testid="trend-section">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Improvement Trend
      </h3>
      {chartData.length < 2 ? (
        <p data-testid="trend-insufficient" className="text-sm text-muted-foreground">
          At least 2 versions required to display a trend.
        </p>
      ) : (
        <div data-testid="trend-chart">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartData}>
              <XAxis dataKey="version" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={32} />
              <Tooltip contentStyle={{ fontSize: 12 }} labelStyle={{ fontWeight: 600 }} />
              <Line
                type="monotone"
                dataKey="confidence"
                name="Confidence"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="quality"
                name="Quality"
                stroke="#22c55e"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

// ── Section 4: Change Summary ─────────────────────────────────────────────────

function SummarySection({ lines }: { lines: string[] }) {
  return (
    <section data-testid="summary-section">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Change Summary
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

export function RecommendationLearningPanel({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const learning = useRecommendationLearning(workspaceId);
  const history = useRecommendationVersionHistory(workspaceId);

  if (learning.isLoading || history.isLoading) {
    return (
      <div data-testid="learning-skeleton" className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (learning.isError || history.isError) {
    return (
      <div
        data-testid="learning-error"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load recommendation learning data. Try refreshing.
      </div>
    );
  }

  const l = learning.data!;
  const h = history.data!;

  if (l.insufficient_data && h.total_versions === 0) {
    return (
      <div data-testid="learning-no-history" className="space-y-2">
        <p data-testid="learning-no-history-message" className="text-sm text-muted-foreground">
          No recommendation versions recorded yet. Version comparison will appear once
          recommendations have been generated at least twice.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="recommendation-learning-panel" className="space-y-6">
      <ComparisonSection
        currentVersion={l.current_version}
        previousVersion={l.previous_version}
        comparison={l.comparison}
      />
      <TimelineSection versions={h.versions} />
      <TrendSection versions={h.versions} />
      <SummarySection lines={l.summary.lines} />
    </div>
  );
}
