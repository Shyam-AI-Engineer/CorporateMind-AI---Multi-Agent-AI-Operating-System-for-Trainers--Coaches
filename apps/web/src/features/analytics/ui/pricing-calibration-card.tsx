"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePricingCalibration } from "@/features/analytics/api/use-analytics";

function PricingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums font-medium">{value}</span>
    </div>
  );
}

function fmt(v: number | null): string {
  if (v == null) return "—";
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
}

export function PricingCalibrationCard({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = usePricingCalibration(workspaceId);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Pricing Calibration</CardTitle>
          {data?.low_confidence && (
            <span className="flex items-center gap-1 text-xs text-amber-600">
              <AlertCircle className="h-3 w-3" />
              Low data ({data.sample_size} accepted)
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load pricing data.</p>
        ) : !data ? (
          <p className="text-sm text-muted-foreground">No pricing data yet.</p>
        ) : (
          <>
            <div className="mb-3 rounded-md bg-muted/50 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Stated Range (Trainer Profile)
              </p>
              <p className="text-sm font-semibold">
                {fmt(data.stated_min_inr)} – {fmt(data.stated_max_inr)}
              </p>
            </div>
            <div className="mb-3 rounded-md bg-muted/50 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground mb-1">
                Actual Accepted Values ({data.sample_size} proposals)
              </p>
              <div className="space-y-1">
                <PricingRow label="Min" value={fmt(data.actual_min_inr)} />
                <PricingRow label="Max" value={fmt(data.actual_max_inr)} />
                <PricingRow label="Average" value={fmt(data.actual_avg_inr)} />
                <PricingRow label="Median" value={fmt(data.actual_median_inr)} />
              </div>
            </div>
            <PricingRow
              label="Avg days to accept"
              value={
                data.avg_days_to_accept != null
                  ? `${data.avg_days_to_accept.toFixed(1)} days`
                  : "—"
              }
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
