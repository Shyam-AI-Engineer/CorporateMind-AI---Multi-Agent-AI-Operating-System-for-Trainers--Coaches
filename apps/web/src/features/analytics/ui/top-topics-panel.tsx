"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTopicPerformance } from "@/features/analytics/api/use-analytics";
import type { TopicStat } from "@/features/analytics/types";

function TopicRow({ row, max }: { row: TopicStat; max: number }) {
  const pct = max > 0 ? Math.round((row.closed_revenue_inr / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{row.topic}</span>
        <span className="tabular-nums text-muted-foreground">
          ₹{row.closed_revenue_inr.toLocaleString("en-IN")} ·{" "}
          {(row.win_rate * 100).toFixed(0)}% win
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-violet-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function TopTopicsPanel({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useTopicPerformance(workspaceId);

  const maxRevenue = data
    ? Math.max(...data.items.map((r) => r.closed_revenue_inr), 1)
    : 1;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Top Topics by Revenue</CardTitle>
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
          <p className="text-sm text-destructive">Failed to load topic data.</p>
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No topic data yet. Add topics to your trainer profile and send
            proposals to see performance.
          </p>
        ) : (
          data.items.map((row) => (
            <TopicRow key={row.topic} row={row} max={maxRevenue} />
          ))
        )}
      </CardContent>
    </Card>
  );
}
