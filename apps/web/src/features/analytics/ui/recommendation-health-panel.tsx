"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { AlertCircle, CheckCircle, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useRecommendationEffectiveness,
  useRecCalibration,
} from "@/features/analytics/api/use-analytics";
import type {
  RecCalibrationTypeItem,
  RecEffectivenessTypeItem,
  QualityTrendPoint,
} from "@/features/analytics/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function calibrationStatus(
  delta: number | null,
): "calibrated" | "warning" | "attention" {
  if (delta === null) return "calibrated";
  const abs = Math.abs(delta);
  if (abs < 5) return "calibrated";
  if (abs <= 15) return "warning";
  return "attention";
}

const STATUS_CLASSES: Record<string, string> = {
  calibrated: "text-emerald-600",
  warning: "text-amber-500",
  attention: "text-red-500",
};

const STATUS_LABELS: Record<string, string> = {
  calibrated: "Calibrated",
  warning: "Warning",
  attention: "Attention",
};

// ── 1. Effectiveness summary cards ────────────────────────────────────────────

function EffectivenessSummary({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useRecommendationEffectiveness(workspaceId);

  if (isError) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-destructive"
        data-testid="effectiveness-error"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load effectiveness data.
      </div>
    );
  }

  const s = data?.summary;

  const cards = [
    { label: "Generated", value: s?.recommendations_generated ?? "—", testId: "card-generated" },
    { label: "Adopted", value: s?.recommendations_acted ?? "—", testId: "card-adopted" },
    { label: "Successful", value: s?.recommendations_successful ?? "—", testId: "card-successful" },
    {
      label: "Adoption Rate",
      value: s ? pct(s.adoption_rate) : "—",
      testId: "card-adoption-rate",
    },
    {
      label: "Success Rate",
      value: s ? pct(s.success_rate) : "—",
      testId: "card-success-rate",
    },
  ];

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Effectiveness Summary</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {cards.map(({ label, value, testId }) => (
          <Card key={label}>
            <CardHeader className="pb-1">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-7 w-14" data-testid="skeleton" />
              ) : (
                <p
                  className="text-2xl font-bold tabular-nums"
                  data-testid={testId}
                >
                  {value}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ── 2. Type performance table ─────────────────────────────────────────────────

function TypePerformanceRow({ item }: { item: RecEffectivenessTypeItem }) {
  return (
    <TableRow data-testid={`type-row-${item.recommendation_type}`}>
      <TableCell className="font-medium capitalize">
        {item.recommendation_type}
      </TableCell>
      <TableCell className="tabular-nums">{item.generated}</TableCell>
      <TableCell className="tabular-nums">{item.acted}</TableCell>
      <TableCell className="tabular-nums">{item.successful}</TableCell>
      <TableCell className="tabular-nums">{pct(item.adoption_rate)}</TableCell>
      <TableCell className="tabular-nums">{pct(item.success_rate)}</TableCell>
      <TableCell className="tabular-nums">
        {item.quality_score !== null ? (
          <Badge variant="secondary">{item.quality_score}</Badge>
        ) : (
          <span className="text-xs text-muted-foreground">Building…</span>
        )}
      </TableCell>
    </TableRow>
  );
}

function TypePerformanceTable({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecommendationEffectiveness(workspaceId);

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Recommendation Type Performance</h3>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Generated</TableHead>
                <TableHead>Adopted</TableHead>
                <TableHead>Successful</TableHead>
                <TableHead>Adoption Rate</TableHead>
                <TableHead>Success Rate</TableHead>
                <TableHead>Quality Score</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-12" data-testid="skeleton" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : !data || data.by_type.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="py-8 text-center text-sm text-muted-foreground"
                    data-testid="type-table-empty"
                  >
                    No recommendation outcomes recorded yet.
                  </TableCell>
                </TableRow>
              ) : (
                data.by_type.map((item) => (
                  <TypePerformanceRow key={item.recommendation_type} item={item} />
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ── 3. Confidence calibration table ──────────────────────────────────────────

function CalibrationRow({ item }: { item: RecCalibrationTypeItem }) {
  const status = calibrationStatus(item.calibration_delta);
  return (
    <TableRow data-testid={`cal-row-${item.recommendation_type}`}>
      <TableCell className="font-medium capitalize">
        {item.recommendation_type}
      </TableCell>
      <TableCell className="tabular-nums">
        {item.predicted_confidence.toFixed(1)}
      </TableCell>
      <TableCell className="tabular-nums">
        {item.observed_success_rate !== null
          ? item.observed_success_rate.toFixed(1)
          : "—"}
      </TableCell>
      <TableCell
        className={`tabular-nums font-medium ${STATUS_CLASSES[status]}`}
        data-testid={`cal-delta-${item.recommendation_type}`}
      >
        {item.calibration_delta !== null ? (
          <>
            {item.calibration_delta > 0 ? "+" : ""}
            {item.calibration_delta.toFixed(1)}
            <span className="ml-1 text-xs font-normal">
              ({STATUS_LABELS[status]})
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">No data</span>
        )}
      </TableCell>
    </TableRow>
  );
}

function CalibrationTable({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecCalibration(workspaceId);

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Confidence Calibration</h3>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Predicted (%)</TableHead>
                <TableHead>Observed (%)</TableHead>
                <TableHead>Delta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 4 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-12" data-testid="skeleton" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : data?.insufficient_data || !data?.recommendation_types.length ? (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="py-8 text-center text-sm text-muted-foreground"
                    data-testid="calibration-empty"
                  >
                    Need at least {data?.minimum_acted_recommendations ?? 5} acted
                    recommendations to evaluate calibration.
                  </TableCell>
                </TableRow>
              ) : (
                data.recommendation_types.map((item) => (
                  <CalibrationRow key={item.recommendation_type} item={item} />
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* legend */}
      {data && !data.insufficient_data && data.recommendation_types.length > 0 && (
        <div
          className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground"
          data-testid="calibration-legend"
        >
          <span className="flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-emerald-600" />
            Calibrated: |delta| &lt; 5
          </span>
          <span className="flex items-center gap-1">
            <Info className="h-3 w-3 text-amber-500" />
            Warning: 5–15
          </span>
          <span className="flex items-center gap-1">
            <AlertCircle className="h-3 w-3 text-red-500" />
            Attention: &gt;15
          </span>
        </div>
      )}
    </div>
  );
}

// ── 4. Quality score trend chart ──────────────────────────────────────────────

const TREND_COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#06b6d4",
];

function buildChartData(trend: QualityTrendPoint[]) {
  const byDate: Record<string, Record<string, number | null>> = {};
  for (const p of trend) {
    const d = p.score_date.slice(5); // MM-DD
    if (!byDate[d]) byDate[d] = {};
    byDate[d][p.rec_type] = p.quality_score;
  }
  return Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }));
}

function QualityTrendChart({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecommendationEffectiveness(workspaceId);

  const trend = data?.quality_trend ?? [];
  const recTypes = [...new Set(trend.map((p) => p.rec_type))];
  const chartData = buildChartData(trend);

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Quality Score Trend</h3>
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <Skeleton className="h-48 w-full" data-testid="skeleton" />
          ) : chartData.length === 0 ? (
            <div
              className="flex h-48 items-center justify-center text-sm text-muted-foreground"
              data-testid="trend-empty"
            >
              Quality scores will appear here once enough feedback is collected.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={192} data-testid="trend-chart">
              <LineChart data={chartData}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  width={28}
                />
                <Tooltip contentStyle={{ fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {recTypes.map((rt, i) => (
                  <Line
                    key={rt}
                    type="monotone"
                    dataKey={rt}
                    name={rt.charAt(0).toUpperCase() + rt.slice(1)}
                    stroke={TREND_COLORS[i % TREND_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── main panel ────────────────────────────────────────────────────────────────

export function RecommendationHealthPanel({
  workspaceId,
}: {
  workspaceId: string;
}) {
  return (
    <div className="space-y-8" data-testid="rec-health-panel">
      <EffectivenessSummary workspaceId={workspaceId} />
      <TypePerformanceTable workspaceId={workspaceId} />
      <CalibrationTable workspaceId={workspaceId} />
      <QualityTrendChart workspaceId={workspaceId} />
    </div>
  );
}
