"use client";

import Link from "next/link";
import { ArrowRight, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalyticsSummary } from "@/features/analytics/api/use-analytics";

function StatRow({
  label,
  value,
  isLoading,
}: {
  label: string;
  value: string;
  isLoading: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {isLoading ? (
        <Skeleton className="h-4 w-12" />
      ) : (
        <span className="font-semibold tabular-nums">{value}</span>
      )}
    </div>
  );
}

export function InsightsCard() {
  const { data, isLoading, isError } = useAnalyticsSummary(30);

  const replyRatePct = data ? `${(data.reply_rate * 100).toFixed(1)}%` : "—";
  const bookingRatePct = data ? `${(data.booking_rate * 100).toFixed(1)}%` : "—";
  const approvalRatePct = data
    ? `${(data.proposal_approval_rate * 100).toFixed(0)}%`
    : "—";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 pb-2">
        <TrendingUp className="h-4 w-4 text-primary" />
        <CardTitle className="text-sm font-semibold">30-Day Performance</CardTitle>
      </CardHeader>
      <CardContent className="space-y-0.5">
        {isError ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            Analytics unavailable — check back after your first nightly rollup.
          </p>
        ) : (
          <>
            <StatRow label="Reply rate" value={replyRatePct} isLoading={isLoading} />
            <StatRow
              label="Outreach sent"
              value={data ? data.total_sent.toLocaleString() : "—"}
              isLoading={isLoading}
            />
            <StatRow
              label="Meetings scheduled"
              value={data ? String(data.meetings_scheduled) : "—"}
              isLoading={isLoading}
            />
            <StatRow
              label="Proposals sent"
              value={data ? String(data.proposals_sent) : "—"}
              isLoading={isLoading}
            />
            <StatRow
              label="Approval rate"
              value={approvalRatePct}
              isLoading={isLoading}
            />
            <StatRow label="Close rate" value={bookingRatePct} isLoading={isLoading} />
          </>
        )}
        <div className="pt-3">
          <Link
            href="/analytics"
            className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            View full analytics
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
