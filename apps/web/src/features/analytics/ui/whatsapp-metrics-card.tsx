"use client";

import { MessageSquare, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWhatsAppAnalytics } from "@/features/analytics/api/use-analytics";

function KpiCard({
  label,
  value,
  sub,
  isLoading,
}: {
  label: string;
  value: string | number;
  sub?: string;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <>
            <p className="text-2xl font-bold">{value}</p>
            {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function WhatsAppMetricsCard({ days = 30 }: { days?: number }) {
  const { data, isLoading, isError, refetch } = useWhatsAppAnalytics(days);

  if (isError) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 pb-2">
          <MessageSquare className="h-4 w-4 text-green-500" />
          <CardTitle className="text-sm">WhatsApp Delivery ({days}d)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            Failed to load WhatsApp analytics.{" "}
            <button
              onClick={() => refetch()}
              className="underline underline-offset-2"
            >
              Retry
            </button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const d = data;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-green-500" />
        <h3 className="text-sm font-semibold">WhatsApp Delivery ({days}d)</h3>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <KpiCard
          label="Sent"
          value={d?.sent.toLocaleString() ?? "—"}
          sub="messages dispatched"
          isLoading={isLoading}
        />
        <KpiCard
          label="Delivery Rate"
          value={d ? `${(d.delivery_rate * 100).toFixed(1)}%` : "—"}
          sub={`${d?.delivered.toLocaleString() ?? 0} delivered`}
          isLoading={isLoading}
        />
        <KpiCard
          label="Read Rate"
          value={d ? `${(d.read_rate * 100).toFixed(1)}%` : "—"}
          sub={`${d?.opened.toLocaleString() ?? 0} read`}
          isLoading={isLoading}
        />
        <KpiCard
          label="Failed Sends"
          value={d?.failed.toLocaleString() ?? "—"}
          sub="provider errors"
          isLoading={isLoading}
        />
        <KpiCard
          label="Compliance Blocks"
          value={d?.compliance_blocks.toLocaleString() ?? "—"}
          sub="blocked before send"
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
