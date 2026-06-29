"use client";

import { Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCampaignROI } from "@/features/analytics/api/use-analytics";
import type { CampaignROISummary } from "@/features/analytics/types";

function ConfidenceBadge({ lowConfidence }: { lowConfidence: boolean }) {
  if (!lowConfidence) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="ml-1 text-xs text-amber-600 border-amber-300">
          Low data
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Fewer than 5 proposals sent — interpret with caution.</TooltipContent>
    </Tooltip>
  );
}

function CampaignRow({ row }: { row: CampaignROISummary }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 border-b py-2 text-sm last:border-0">
      <div className="min-w-0">
        <p className="truncate font-medium">{row.campaign_name}</p>
        <p className="text-xs text-muted-foreground capitalize">
          {row.channel} · {row.campaign_status}
        </p>
      </div>
      <div className="text-right tabular-nums">
        <p className="font-medium">
          ₹{row.closed_revenue_inr.toLocaleString("en-IN")}
        </p>
        <p className="text-xs text-muted-foreground">closed</p>
      </div>
      <div className="text-right tabular-nums">
        <p className="font-medium">{(row.win_rate * 100).toFixed(1)}%</p>
        <p className="text-xs text-muted-foreground">win rate</p>
      </div>
      <div className="text-right tabular-nums">
        <p className="font-medium">
          {row.avg_days_to_accept != null
            ? `${row.avg_days_to_accept.toFixed(1)}d`
            : "—"}
        </p>
        <p className="text-xs text-muted-foreground">avg close</p>
      </div>
      <div className="text-right tabular-nums">
        <p className="font-medium">{row.proposals_sent}</p>
        <p className="text-xs text-muted-foreground flex items-center justify-end gap-0.5">
          proposals
          <ConfidenceBadge lowConfidence={row.low_confidence} />
        </p>
      </div>
    </div>
  );
}

export function CampaignROIPanel({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useCampaignROI(workspaceId);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 pb-2">
        <CardTitle className="text-sm">Campaign ROI</CardTitle>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="h-3.5 w-3.5 cursor-help text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            <strong>All-touch attribution</strong> — revenue from a contact who
            appeared in multiple campaigns is credited to each campaign they
            were in.
          </TooltipContent>
        </Tooltip>
        {data && (
          <span className="ml-auto text-xs text-muted-foreground">
            {data.total} campaign{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load campaign ROI.</p>
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No campaign data yet. Run your first campaign to see ROI metrics.
          </p>
        ) : (
          <div>
            {data.items.map((row) => (
              <CampaignRow key={row.campaign_id} row={row} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
