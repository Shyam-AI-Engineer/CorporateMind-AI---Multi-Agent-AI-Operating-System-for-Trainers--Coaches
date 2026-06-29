"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEvidence } from "@/features/analytics/api/use-analytics";

// ── Constants ─────────────────────────────────────────────────────────────────

const REC_TYPES = ["campaign", "channel", "industry", "pricing", "topic"] as const;
type RecType = (typeof REC_TYPES)[number];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "—";
  return value.toFixed(decimals);
}

function BadgeChip({
  label,
  testId,
  value,
}: {
  label: string;
  testId: string;
  value: string | null | undefined;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        data-testid={testId}
        className="rounded-full border px-3 py-0.5 text-xs font-medium capitalize"
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

function MetricCard({
  testId,
  label,
  value,
}: {
  testId: string;
  label: string;
  value: string | number;
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

// ── Panel ─────────────────────────────────────────────────────────────────────

export function RecommendationEvidencePanel({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const [selectedType, setSelectedType] = useState<RecType>("industry");
  const { data, isLoading, isError } = useEvidence(workspaceId, selectedType);

  const s = data?.summary;

  return (
    <div data-testid="recommendation-evidence-panel" className="space-y-6">

      {/* ── Section 1: Recommendation selector ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Select Recommendation Type</CardTitle>
        </CardHeader>
        <CardContent>
          <select
            data-testid="rec-type-selector"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value as RecType)}
          >
            {REC_TYPES.map((t) => (
              <option key={t} value={t} data-testid={`rec-type-option-${t}`}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      {/* ── Loading skeletons ───────────────────────────────────────────────── */}
      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} data-testid="skeleton" className="h-24 w-full" />
          ))}
        </div>
      )}

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {isError && (
        <div
          data-testid="evidence-error"
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load evidence data. Please try again.
        </div>
      )}

      {/* ── Insufficient data ───────────────────────────────────────────────── */}
      {!isLoading && !isError && data?.insufficient_data && (
        <div
          data-testid="evidence-insufficient"
          className="rounded-md border p-6 text-center text-sm text-muted-foreground"
        >
          No evidence available. Recommendation has not yet accumulated enough
          history to display evidence.
        </div>
      )}

      {/* ── Section 2: Evidence Summary cards ──────────────────────────────── */}
      {!isLoading && !isError && s && !data.insufficient_data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            testId="card-generated-count"
            label="Generated Count"
            value={s.generated_count}
          />
          <MetricCard
            testId="card-quality-score"
            label="Quality Score"
            value={s.quality_score != null ? s.quality_score : "—"}
          />
          <MetricCard
            testId="card-reliability"
            label="Reliability Score"
            value={s.reliability_score != null ? `${fmt(s.reliability_score)}` : "—"}
          />
          <MetricCard
            testId="card-success-rate"
            label="Success Rate"
            value={`${fmt(s.success_rate)}%`}
          />
        </div>
      )}

      {/* ── Section 3: Evidence Timeline cards ─────────────────────────────── */}
      {!isLoading && !isError && s && !data.insufficient_data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            testId="card-last-generated"
            label="Last Generated"
            value={s.last_generated_at ?? "—"}
          />
          <MetricCard
            testId="card-days-since"
            label="Days Since Last Generated"
            value={s.days_since_last_generated != null ? s.days_since_last_generated : "—"}
          />
          <MetricCard
            testId="card-avg-days-action"
            label="Avg Days to Action"
            value={`${fmt(s.avg_days_to_action)} d`}
          />
          <MetricCard
            testId="card-avg-days-success"
            label="Avg Days to Success"
            value={`${fmt(s.avg_days_to_success)} d`}
          />
        </div>
      )}

      {/* ── Section 4: Supporting Metrics Table ────────────────────────────── */}
      {!isLoading && !isError && data && !data.insufficient_data && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Supporting Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            {data.supporting_metrics.length === 0 ? (
              <p
                data-testid="metrics-table-empty"
                className="text-sm text-muted-foreground"
              >
                No supporting metrics available.
              </p>
            ) : (
              <div data-testid="metrics-table" className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="pb-2 text-left font-medium">Metric</th>
                      <th className="pb-2 text-right font-medium">Value</th>
                      <th className="pb-2 text-right font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.supporting_metrics.map((m) => (
                      <tr
                        key={m.name}
                        data-testid={`metric-row-${m.name.toLowerCase().replace(/\s+/g, "-")}`}
                        className="border-b last:border-0"
                      >
                        <td className="py-2">{m.name}</td>
                        <td className="py-2 text-right tabular-nums">
                          {m.value != null ? fmt(m.value, 2) : "—"}
                        </td>
                        <td className="py-2 text-right text-muted-foreground">
                          {m.source}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Section 5: Recommendation Health badges ─────────────────────────── */}
      {!isLoading && !isError && s && !data.insufficient_data && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Recommendation Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div
              data-testid="health-badges"
              className="flex flex-wrap gap-6 py-2"
            >
              <BadgeChip
                label="Calibration"
                testId="badge-calibration"
                value={s.calibration_status}
              />
              <BadgeChip
                label="Reliability"
                testId="badge-reliability"
                value={s.reliability_rating}
              />
              <BadgeChip
                label="Stability"
                testId="badge-stability"
                value={s.stability_rating}
              />
              <BadgeChip
                label="Coverage"
                testId="badge-coverage"
                value={s.coverage_status}
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
