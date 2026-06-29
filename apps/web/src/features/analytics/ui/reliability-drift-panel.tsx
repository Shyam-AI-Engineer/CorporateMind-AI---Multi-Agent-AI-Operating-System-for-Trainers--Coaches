"use client";

import { AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDrift,
  useReliability,
} from "@/features/analytics/api/use-analytics";
import type { MetricTrend } from "@/features/analytics/types";

interface Props {
  workspaceId: string;
}

function directionBadgeVariant(
  direction: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (direction === "improving") return "default";
  if (direction === "declining") return "destructive";
  return "secondary";
}

function reliabilityBadgeVariant(
  rating: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (rating === "high") return "default";
  if (rating === "low") return "destructive";
  return "secondary";
}

function TrendCard({
  label,
  trend,
  testId,
}: {
  label: string;
  trend: MetricTrend;
  testId: string;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <p className="text-2xl font-bold">{trend.current.toFixed(1)}</p>
        <p className="text-xs text-muted-foreground">
          Previous: {trend.previous.toFixed(1)}
        </p>
        <p className="text-xs">
          Change:{" "}
          <span
            className={
              trend.change > 0
                ? "text-green-600"
                : trend.change < 0
                  ? "text-destructive"
                  : "text-muted-foreground"
            }
          >
            {trend.change > 0 ? "+" : ""}
            {trend.change.toFixed(1)}
          </span>
        </p>
        <Badge
          variant={directionBadgeVariant(trend.direction)}
          className="capitalize"
        >
          {trend.direction}
        </Badge>
      </CardContent>
    </Card>
  );
}

export function ReliabilityDriftPanel({ workspaceId }: Props) {
  const drift = useDrift(workspaceId);
  const reliability = useReliability(workspaceId);

  const driftData = drift.data;
  const relData = reliability.data;

  return (
    <div className="space-y-6" data-testid="reliability-drift-panel">
      {/* ── Drift section ────────────────────────────────────────────────── */}
      {drift.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : drift.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="drift-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load drift data.
        </div>
      ) : driftData?.insufficient_data ? (
        <div
          className="rounded-md border border-muted p-4 text-sm text-muted-foreground"
          data-testid="drift-insufficient"
        >
          Need at least 60 days of history to measure drift.
        </div>
      ) : driftData ? (
        <>
          {/* Section 1: Overall Drift */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Overall Drift</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <TrendCard
                  label="Quality Score Trend"
                  trend={driftData.overall.quality_score}
                  testId="card-drift-quality"
                />
                <TrendCard
                  label="Adoption Trend"
                  trend={driftData.overall.adoption_rate}
                  testId="card-drift-adoption"
                />
                <TrendCard
                  label="Success Trend"
                  trend={driftData.overall.success_rate}
                  testId="card-drift-success"
                />
              </div>
            </CardContent>
          </Card>

          {/* Section 2: Recommendation Drift Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Recommendation Drift</CardTitle>
            </CardHeader>
            <CardContent>
              {driftData.by_type.length === 0 ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="drift-table-empty"
                >
                  Insufficient recommendation history.
                </p>
              ) : (
                <table className="w-full text-sm" data-testid="drift-table">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-right font-medium">Current</th>
                      <th className="py-2 text-right font-medium">Previous</th>
                      <th className="py-2 text-right font-medium">Change</th>
                      <th className="py-2 text-right font-medium">Direction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {driftData.by_type.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        className="border-b last:border-0"
                        data-testid={`drift-row-${item.recommendation_type}`}
                      >
                        <td className="py-2 capitalize">
                          {item.recommendation_type}
                        </td>
                        <td className="py-2 text-right">
                          {item.quality_score.current.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          {item.quality_score.previous.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          <span
                            className={
                              item.quality_score.change > 0
                                ? "text-green-600"
                                : item.quality_score.change < 0
                                  ? "text-destructive"
                                  : "text-muted-foreground"
                            }
                          >
                            {item.quality_score.change > 0 ? "+" : ""}
                            {item.quality_score.change.toFixed(1)}
                          </span>
                        </td>
                        <td className="py-2 text-right">
                          <Badge
                            variant={directionBadgeVariant(
                              item.quality_score.direction,
                            )}
                            className="capitalize"
                          >
                            {item.quality_score.direction}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}

      {/* ── Reliability section ──────────────────────────────────────────── */}
      {reliability.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : reliability.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="reliability-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load reliability data.
        </div>
      ) : relData?.insufficient_data ? (
        <div
          className="rounded-md border border-muted p-4 text-sm text-muted-foreground"
          data-testid="reliability-insufficient"
        >
          Insufficient recommendation history.
        </div>
      ) : relData ? (
        <>
          {/* Section 3: Reliability Overview */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Reliability Overview</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div data-testid="card-reliability-score">
                  <p className="text-2xl font-bold">
                    {relData.overall_reliability.score.toFixed(1)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Overall Reliability Score
                  </p>
                </div>
                <div
                  className="flex flex-col items-start justify-center"
                  data-testid="card-reliability-rating"
                >
                  <Badge
                    variant={reliabilityBadgeVariant(
                      relData.overall_reliability.rating,
                    )}
                    className="capitalize"
                  >
                    {relData.overall_reliability.rating}
                  </Badge>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Reliability Rating
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 4: Recommendation Reliability Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Recommendation Reliability
              </CardTitle>
            </CardHeader>
            <CardContent>
              {relData.recommendation_types.length === 0 ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="reliability-table-empty"
                >
                  Insufficient recommendation history.
                </p>
              ) : (
                <table
                  className="w-full text-sm"
                  data-testid="reliability-table"
                >
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-right font-medium">
                        Reliability Score
                      </th>
                      <th className="py-2 text-right font-medium">Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {relData.recommendation_types.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        className="border-b last:border-0"
                        data-testid={`reliability-row-${item.recommendation_type}`}
                      >
                        <td className="py-2 capitalize">
                          {item.recommendation_type}
                        </td>
                        <td className="py-2 text-right">
                          {item.reliability_score.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          <Badge
                            variant={reliabilityBadgeVariant(item.rating)}
                            className="capitalize"
                          >
                            {item.rating}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
