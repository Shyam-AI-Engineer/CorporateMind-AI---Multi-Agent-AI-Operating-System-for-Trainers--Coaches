"use client";

import { AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useLifecycle,
  useDecay,
} from "@/features/analytics/api/use-analytics";

interface Props {
  workspaceId: string;
}

function KpiCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
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

export function LifecycleObservatoryPanel({ workspaceId }: Props) {
  const lifecycle = useLifecycle(workspaceId);
  const decay = useDecay(workspaceId);

  const lc = lifecycle.data;
  const dc = decay.data;

  return (
    <div className="space-y-6" data-testid="lifecycle-observatory-panel">
      {/* ── Lifecycle section ────────────────────────────────────────────── */}
      {lifecycle.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : lifecycle.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="lifecycle-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load lifecycle data.
        </div>
      ) : lc?.insufficient_data ? (
        <div
          className="rounded-md border border-muted p-4 text-sm text-muted-foreground"
          data-testid="lifecycle-insufficient"
        >
          Need completed recommendation outcomes to evaluate lifecycle.
        </div>
      ) : lc ? (
        <>
          {/* Section 1: Lifecycle Summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Lifecycle Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <KpiCard
                  label="Avg Days To Action"
                  value={lc.overall.avg_days_to_action.toFixed(1)}
                  testId="card-avg-days-action"
                />
                <KpiCard
                  label="Avg Days To Success"
                  value={lc.overall.avg_days_to_success.toFixed(1)}
                  testId="card-avg-days-success"
                />
                <KpiCard
                  label="Acted Rate"
                  value={`${lc.overall.acted_rate.toFixed(1)}%`}
                  testId="card-acted-rate"
                />
                <KpiCard
                  label="Success Rate"
                  value={`${lc.overall.success_rate.toFixed(1)}%`}
                  testId="card-success-rate"
                />
              </div>
            </CardContent>
          </Card>

          {/* Section 2: Recommendation Lifecycle Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                Recommendation Lifecycle
              </CardTitle>
            </CardHeader>
            <CardContent>
              {lc.recommendation_types.length === 0 ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="lifecycle-table-empty"
                >
                  Need completed recommendation outcomes to evaluate lifecycle.
                </p>
              ) : (
                <table
                  className="w-full text-sm"
                  data-testid="lifecycle-table"
                >
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-right font-medium">
                        Avg Days To Action
                      </th>
                      <th className="py-2 text-right font-medium">
                        Avg Days To Success
                      </th>
                      <th className="py-2 text-right font-medium">
                        Acted Rate
                      </th>
                      <th className="py-2 text-right font-medium">
                        Success Rate
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {lc.recommendation_types.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        className="border-b last:border-0"
                        data-testid={`lifecycle-row-${item.recommendation_type}`}
                      >
                        <td className="py-2 capitalize">
                          {item.recommendation_type}
                        </td>
                        <td className="py-2 text-right">
                          {item.avg_days_to_action.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          {item.avg_days_to_success.toFixed(1)}
                        </td>
                        <td className="py-2 text-right">
                          {item.acted_rate.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right">
                          {item.success_rate.toFixed(1)}%
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

      {/* ── Decay section ────────────────────────────────────────────────── */}
      {decay.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" data-testid="skeleton" />
          ))}
        </div>
      ) : decay.isError ? (
        <div
          className="flex items-center gap-2 text-sm text-destructive"
          data-testid="decay-error"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load decay data.
        </div>
      ) : dc ? (
        <>
          {/* Section 3: Effectiveness Decay */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Effectiveness Decay</CardTitle>
            </CardHeader>
            <CardContent>
              {dc.buckets.every((b) => b.sample_size === 0) ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="decay-table-empty"
                >
                  Not enough historical recommendation data to evaluate decay.
                </p>
              ) : (
                <table className="w-full text-sm" data-testid="decay-table">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Age Bucket</th>
                      <th className="py-2 text-right font-medium">
                        Acted Rate
                      </th>
                      <th className="py-2 text-right font-medium">
                        Success Rate
                      </th>
                      <th className="py-2 text-right font-medium">
                        Sample Size
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {dc.buckets.map((bucket) => (
                      <tr
                        key={bucket.age_bucket}
                        className="border-b last:border-0"
                        data-testid={`decay-bucket-${bucket.age_bucket}`}
                      >
                        <td className="py-2 font-mono text-xs">
                          {bucket.age_bucket} days
                        </td>
                        <td className="py-2 text-right">
                          {bucket.acted_rate.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right">
                          {bucket.success_rate.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {bucket.sample_size}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          {/* Section 4: Decay Detection */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Decay Detection</CardTitle>
            </CardHeader>
            <CardContent>
              {dc.recommendation_types.length === 0 ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="decay-detection-table-empty"
                >
                  Not enough historical recommendation data to evaluate decay.
                </p>
              ) : (
                <table
                  className="w-full text-sm"
                  data-testid="decay-detection-table"
                >
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-right font-medium">
                        Best Bucket
                      </th>
                      <th className="py-2 text-right font-medium">
                        Worst Bucket
                      </th>
                      <th className="py-2 text-right font-medium">
                        Decay Detected
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {dc.recommendation_types.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        className="border-b last:border-0"
                        data-testid={`decay-detection-row-${item.recommendation_type}`}
                      >
                        <td className="py-2 capitalize">
                          {item.recommendation_type}
                        </td>
                        <td className="py-2 text-right font-mono text-xs">
                          {item.best_bucket}
                        </td>
                        <td className="py-2 text-right font-mono text-xs">
                          {item.worst_bucket}
                        </td>
                        <td className="py-2 text-right">
                          <Badge
                            variant={
                              item.decay_detected ? "destructive" : "secondary"
                            }
                          >
                            {item.decay_detected ? "Yes" : "No"}
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
