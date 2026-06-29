"use client";

import { AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCalibrationReview,
  useStability,
} from "@/features/analytics/api/use-analytics";

interface Props {
  workspaceId: string;
}

function stabilityBadgeVariant(
  rating: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (rating === "unstable") return "destructive";
  if (rating === "volatile") return "secondary";
  return "default";
}

function severityBadgeVariant(
  severity: string | null,
): "default" | "secondary" | "destructive" | "outline" {
  if (severity === "severe") return "destructive";
  if (severity === "warning") return "secondary";
  return "default";
}

export function CalibrationAnalysisPanel({ workspaceId }: Props) {
  const calibration = useCalibrationReview(workspaceId);
  const stability = useStability(workspaceId);

  const calData = calibration.data;
  const stabData = stability.data;

  return (
    <div className="space-y-6" data-testid="calibration-analysis-panel">
      {/* ── Calibration section ──────────────────────────────────────────── */}
      {calibration.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : calibration.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="calibration-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load calibration review.
        </div>
      ) : calData?.insufficient_data ? (
        <div
          className="rounded-md border border-muted p-4 text-sm text-muted-foreground"
          data-testid="calibration-insufficient"
        >
          Need at least 5 successful outcomes to evaluate calibration.
        </div>
      ) : calData ? (
        <>
          {/* Section 1: Confidence Distribution */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Confidence Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div data-testid="card-conf-high">
                  <p className="text-2xl font-bold">
                    {calData.confidence_distribution.high}
                  </p>
                  <p className="text-xs text-muted-foreground">High</p>
                </div>
                <div data-testid="card-conf-medium">
                  <p className="text-2xl font-bold">
                    {calData.confidence_distribution.medium}
                  </p>
                  <p className="text-xs text-muted-foreground">Medium</p>
                </div>
                <div data-testid="card-conf-low">
                  <p className="text-2xl font-bold">
                    {calData.confidence_distribution.low}
                  </p>
                  <p className="text-xs text-muted-foreground">Low</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 2: Calibration Accuracy */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Calibration Accuracy</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div data-testid="card-acc-well-calibrated">
                  <p className="text-2xl font-bold">
                    {calData.accuracy.well_calibrated_count}
                  </p>
                  <p className="text-xs text-muted-foreground">Well Calibrated</p>
                </div>
                <div data-testid="card-acc-overconfident">
                  <p className="text-2xl font-bold">
                    {calData.accuracy.overconfident_count}
                  </p>
                  <p className="text-xs text-muted-foreground">Overconfident</p>
                </div>
                <div data-testid="card-acc-underconfident">
                  <p className="text-2xl font-bold">
                    {calData.accuracy.underconfident_count}
                  </p>
                  <p className="text-xs text-muted-foreground">Underconfident</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 3: Confidence Performance */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Confidence Performance</CardTitle>
            </CardHeader>
            <CardContent>
              {calData.overall.high_confidence_success_rate === null &&
              calData.overall.medium_confidence_success_rate === null &&
              calData.overall.low_confidence_success_rate === null ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="confidence-performance-empty"
                >
                  Need at least 5 successful outcomes to evaluate calibration.
                </p>
              ) : (
                <table className="w-full text-sm" data-testid="confidence-performance-table">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">
                        Confidence Level
                      </th>
                      <th className="py-2 text-right font-medium">
                        Success Rate
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(["high", "medium", "low"] as const).map((level) => {
                      const rate =
                        calData.overall[
                          `${level}_confidence_success_rate` as keyof typeof calData.overall
                        ];
                      return (
                        <tr
                          key={level}
                          className="border-b last:border-0"
                          data-testid={`confidence-perf-row-${level}`}
                        >
                          <td className="py-2 capitalize">{level}</td>
                          <td className="py-2 text-right">
                            {rate !== null ? `${rate.toFixed(1)}%` : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}

      {/* ── Stability section ────────────────────────────────────────────── */}
      {stability.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : stability.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="stability-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load stability data.
        </div>
      ) : stabData?.insufficient_data ? (
        <div
          className="rounded-md border border-muted p-4 text-sm text-muted-foreground"
          data-testid="stability-insufficient"
        >
          Not enough quality history to measure stability.
        </div>
      ) : stabData ? (
        <>
          {/* Section 4: Quality Score Stability */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Quality Score Stability</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div data-testid="card-stability-avg">
                  <p className="text-2xl font-bold">
                    {stabData.quality_score_stability.average.toFixed(1)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Average Quality Score
                  </p>
                </div>
                <div data-testid="card-stability-std">
                  <p className="text-2xl font-bold">
                    {stabData.quality_score_stability.std_dev.toFixed(1)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Standard Deviation
                  </p>
                </div>
                <div data-testid="card-stability-rating">
                  <Badge
                    variant={stabilityBadgeVariant(
                      stabData.quality_score_stability.stability_rating,
                    )}
                    className="capitalize"
                  >
                    {stabData.quality_score_stability.stability_rating}
                  </Badge>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Stability Rating
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 5: Recommendation Stability Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Recommendation Stability</CardTitle>
            </CardHeader>
            <CardContent>
              {stabData.recommendation_types.length === 0 ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="stability-table-empty"
                >
                  Not enough quality history to measure stability.
                </p>
              ) : (
                <table className="w-full text-sm" data-testid="stability-table">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-right font-medium">
                        Average Score
                      </th>
                      <th className="py-2 text-right font-medium">Std Dev</th>
                      <th className="py-2 text-right font-medium">Stability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stabData.recommendation_types.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        className="border-b last:border-0"
                        data-testid={`stability-row-${item.recommendation_type}`}
                      >
                        <td className="py-2 capitalize">
                          {item.recommendation_type}
                        </td>
                        <td className="py-2 text-right">
                          {item.average_quality_score.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          {item.std_dev.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          <Badge
                            variant={stabilityBadgeVariant(item.stability_rating)}
                            className="capitalize"
                          >
                            {item.stability_rating}
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
