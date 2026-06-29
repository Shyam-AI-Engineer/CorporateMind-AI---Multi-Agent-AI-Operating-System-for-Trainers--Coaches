"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useIndustryPerformance } from "@/features/analytics/api/use-analytics";
import type { IndustryStat } from "@/features/analytics/types";

function IndustryRow({ row, max }: { row: IndustryStat; max: number }) {
  const pct = max > 0 ? Math.round((row.closed_revenue_inr / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{row.industry}</span>
        <span className="tabular-nums text-muted-foreground">
          ₹{row.closed_revenue_inr.toLocaleString("en-IN")} ·{" "}
          {(row.win_rate * 100).toFixed(0)}% win
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function TopIndustriesPanel({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useIndustryPerformance(workspaceId);

  const maxRevenue = data
    ? Math.max(...data.items.map((r) => r.closed_revenue_inr), 1)
    : 1;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Top Industries by Revenue</CardTitle>
          {data?.low_confidence && (
            <span className="flex items-center gap-1 text-xs text-amber-600">
              <AlertCircle className="h-3 w-3" />
              Low data ({data.sample_size} proposals)
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load industry data.</p>
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No industry data yet. Send proposals to contacts with company
            profiles to see performance by industry.
          </p>
        ) : (
          <>
            {data.items.map((row) => (
              <IndustryRow key={row.industry} row={row} max={maxRevenue} />
            ))}
            {data.unknown_count > 0 && (
              <p className="pt-1 text-xs text-muted-foreground">
                {data.unknown_count} proposal
                {data.unknown_count !== 1 ? "s" : ""} sent to contacts with no
                industry data.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
