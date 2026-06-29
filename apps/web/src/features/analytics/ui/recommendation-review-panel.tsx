"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AlertCircle, TrendingDown, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecReview } from "@/features/analytics/api/use-analytics";
import type {
  RecBestWorstPerformer,
  RecCalibrationGroupItem,
  RecCalibrationGroupSummary,
} from "@/features/analytics/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

// ── 1. Top Performers ─────────────────────────────────────────────────────────

function PerformerCard({
  title,
  value,
  sub,
  testId,
  icon,
}: {
  title: string;
  value: string;
  sub: string;
  testId: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xl font-bold capitalize" data-testid={testId}>
          {value}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function EmptyPerformerCard({ title }: { title: string }) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground" data-testid="performer-empty">
          No data yet
        </p>
      </CardContent>
    </Card>
  );
}

function TopPerformers({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecReview(workspaceId);

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Top Performers</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-6 w-24" data-testid="skeleton" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            {data?.best_performing_type ? (
              <PerformerCard
                title="Best Performing Type"
                value={data.best_performing_type.recommendation_type}
                sub={`Quality score: ${data.best_performing_type.quality_score}`}
                testId="card-best-type"
                icon={<TrendingUp className="h-3 w-3 text-emerald-600" />}
              />
            ) : (
              <EmptyPerformerCard title="Best Performing Type" />
            )}

            {data?.most_successful_type ? (
              <PerformerCard
                title="Most Successful Type"
                value={data.most_successful_type.recommendation_type}
                sub={`Success rate: ${pct(data.most_successful_type.success_rate)}`}
                testId="card-most-successful"
              />
            ) : (
              <EmptyPerformerCard title="Most Successful Type" />
            )}

            {data?.most_adopted_type ? (
              <PerformerCard
                title="Most Adopted Type"
                value={data.most_adopted_type.recommendation_type}
                sub={`Adoption rate: ${pct(data.most_adopted_type.adoption_rate)}`}
                testId="card-most-adopted"
              />
            ) : (
              <EmptyPerformerCard title="Most Adopted Type" />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── 2. Improvement Opportunities ─────────────────────────────────────────────

function ImprovementOpportunities({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecReview(workspaceId);

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Improvement Opportunities</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {isLoading ? (
          Array.from({ length: 2 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-6 w-24" data-testid="skeleton" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            {data?.worst_performing_type ? (
              <PerformerCard
                title="Worst Performing Type"
                value={data.worst_performing_type.recommendation_type}
                sub={`Quality score: ${data.worst_performing_type.quality_score}`}
                testId="card-worst-type"
                icon={<TrendingDown className="h-3 w-3 text-red-500" />}
              />
            ) : (
              <EmptyPerformerCard title="Worst Performing Type" />
            )}

            {data?.most_ignored_type ? (
              <PerformerCard
                title="Most Ignored Type"
                value={data.most_ignored_type.recommendation_type}
                sub={`Ignored rate: ${pct(data.most_ignored_type.ignored_rate)}`}
                testId="card-most-ignored"
              />
            ) : (
              <EmptyPerformerCard title="Most Ignored Type" />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── 3. Calibration Review ─────────────────────────────────────────────────────

function CalibrationGroup({
  title,
  items,
  badgeClass,
  testId,
}: {
  title: string;
  items: RecCalibrationGroupItem[];
  badgeClass: string;
  testId: string;
}) {
  if (items.length === 0) {
    return (
      <div data-testid={testId}>
        <p className="mb-1 text-xs font-semibold text-muted-foreground">{title}</p>
        <p className="text-xs text-muted-foreground" data-testid={`${testId}-empty`}>
          None
        </p>
      </div>
    );
  }
  return (
    <div data-testid={testId}>
      <p className="mb-2 text-xs font-semibold text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <Badge
            key={item.recommendation_type}
            variant="secondary"
            className={badgeClass}
            data-testid={`cal-badge-${item.recommendation_type}`}
          >
            <span className="capitalize">{item.recommendation_type}</span>
            <span className="ml-1 tabular-nums">
              ({item.calibration_delta > 0 ? "+" : ""}
              {item.calibration_delta.toFixed(1)})
            </span>
          </Badge>
        ))}
      </div>
    </div>
  );
}

function CalibrationReview({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecReview(workspaceId);

  const summary: RecCalibrationGroupSummary = data?.calibration_summary ?? {
    overconfident: [],
    underconfident: [],
    well_calibrated: [],
  };
  const hasAny =
    summary.overconfident.length +
      summary.underconfident.length +
      summary.well_calibrated.length >
    0;

  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold">Calibration Review</h3>
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <Skeleton className="h-20 w-full" data-testid="skeleton" />
          ) : !hasAny ? (
            <p
              className="text-sm text-muted-foreground"
              data-testid="calibration-review-empty"
            >
              Need at least 5 acted recommendations before calibration analysis.
            </p>
          ) : (
            <div className="space-y-4" data-testid="calibration-review-groups">
              <CalibrationGroup
                title="Well Calibrated"
                items={summary.well_calibrated}
                badgeClass="text-emerald-700 bg-emerald-50"
                testId="group-well-calibrated"
              />
              <CalibrationGroup
                title="Overconfident"
                items={summary.overconfident}
                badgeClass="text-red-700 bg-red-50"
                testId="group-overconfident"
              />
              <CalibrationGroup
                title="Underconfident"
                items={summary.underconfident}
                badgeClass="text-amber-700 bg-amber-50"
                testId="group-underconfident"
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── 4. Quality Trend chart ────────────────────────────────────────────────────

function QualityTrend({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading } = useRecReview(workspaceId);

  const trend = data?.quality_trend ?? [];
  const chartData = trend.map((p) => ({
    date: p.date.slice(5), // MM-DD
    score: p.quality_score,
  }));

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
              data-testid="review-trend-empty"
            >
              Quality scores will appear here once enough feedback is collected.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={192}>
              <LineChart data={chartData} data-testid="review-trend-chart">
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
                <Line
                  type="monotone"
                  dataKey="score"
                  name="Avg Quality"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── main panel ────────────────────────────────────────────────────────────────

export function RecommendationReviewPanel({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const { data, isError } = useRecReview(workspaceId);

  if (isError) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-destructive"
        data-testid="review-error"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load recommendation review data.
      </div>
    );
  }

  if (data?.insufficient_data) {
    return (
      <div
        className="flex h-48 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground"
        data-testid="review-insufficient"
      >
        No recommendation history available yet. Generate recommendations to
        unlock this view.
      </div>
    );
  }

  return (
    <div className="space-y-8" data-testid="rec-review-panel">
      <TopPerformers workspaceId={workspaceId} />
      <ImprovementOpportunities workspaceId={workspaceId} />
      <CalibrationReview workspaceId={workspaceId} />
      <QualityTrend workspaceId={workspaceId} />
    </div>
  );
}
