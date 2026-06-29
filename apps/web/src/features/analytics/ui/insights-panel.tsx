"use client";

import { AlertCircle, BrainCircuit, ShieldAlert, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInsights } from "@/features/analytics/api/use-analytics";
import type { InsightOpportunity } from "@/features/analytics/types";

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ level }: { level: string }) {
  if (level === "high") {
    return (
      <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
        HIGH
      </Badge>
    );
  }
  if (level === "medium") {
    return (
      <Badge variant="outline" className="border-amber-400 text-amber-700 dark:text-amber-400">
        MED
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-muted-foreground/40 text-muted-foreground">
      LOW
    </Badge>
  );
}

// ── Opportunity card ──────────────────────────────────────────────────────────

function OpportunityCard({ opp }: { opp: InsightOpportunity }) {
  return (
    <div
      className="rounded-lg border bg-card p-4 space-y-2"
      data-testid={`insight-opportunity-${opp.confidence_level}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 shrink-0 text-primary" />
          <p className="text-sm font-medium leading-tight">{opp.title}</p>
        </div>
        <ConfidenceBadge level={opp.confidence_level} />
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed pl-6">{opp.rationale}</p>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function InsightsPanel({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useInsights(workspaceId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-36 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load insights. Try refreshing.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Executive summary */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 pb-2">
          <BrainCircuit className="h-4 w-4 text-violet-500" />
          <CardTitle className="text-sm">AI Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm text-muted-foreground leading-relaxed"
            data-testid="insight-executive-summary"
          >
            {data?.executive_summary ?? "No summary available."}
          </p>
        </CardContent>
      </Card>

      {/* Top opportunities */}
      {(data?.top_opportunities?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Top Opportunities</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data!.top_opportunities.map((opp, i) => (
              <OpportunityCard key={`${opp.title}-${i}`} opp={opp} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Risks */}
      {(data?.risks?.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 pb-2">
            <ShieldAlert className="h-4 w-4 text-amber-500" />
            <CardTitle className="text-sm">Risks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data!.risks.map((risk, i) => (
              <div
                key={`${risk.title}-${i}`}
                className="space-y-1"
                data-testid={`insight-risk-${i}`}
              >
                <p className="text-xs font-medium">{risk.title}</p>
                <p className="text-xs text-muted-foreground">{risk.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Data limitations */}
      {(data?.data_limitations?.length ?? 0) > 0 && (
        <div
          className="rounded-md border border-dashed bg-muted/30 px-4 py-3 space-y-1"
          data-testid="insight-limitations"
        >
          <p className="text-xs font-medium text-muted-foreground">Data limitations</p>
          <ul className="space-y-1">
            {data!.data_limitations.map((lim, i) => (
              <li
                key={i}
                className="flex items-start gap-1.5 text-xs text-muted-foreground"
              >
                <span className="mt-0.5 shrink-0">•</span>
                {lim}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
