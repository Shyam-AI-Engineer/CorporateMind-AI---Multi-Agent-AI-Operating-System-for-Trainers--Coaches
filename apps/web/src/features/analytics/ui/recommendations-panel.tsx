"use client";

import { AlertCircle, Lightbulb } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useRecommendationEffectiveness,
  useRecommendations,
} from "@/features/analytics/api/use-analytics";
import { RecommendationCard } from "@/features/analytics/ui/recommendation-card";

// ── Empty / suppressed state helpers ─────────────────────────────────────────

const UNLOCK_HINTS: Record<string, string> = {
  industry: "Need proposals sent to at least 2 industries with 5+ proposals each.",
  topic: "Need 5+ proposals across at least 2 trainer topics.",
  pricing: "Need 10+ accepted proposals with recorded deal values.",
  campaign: "Need 3+ campaigns each with 5+ proposals sent.",
  channel: "Need 5+ proposals across at least 2 different outreach channels.",
};

function SuppressedHint({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <div className="rounded-md border border-dashed bg-muted/30 px-4 py-3">
      <p className="text-xs text-muted-foreground">
        <span className="font-medium">{count} recommendation{count > 1 ? "s" : ""}</span>{" "}
        will unlock as your data grows. To unlock:
      </p>
      <ul className="mt-2 space-y-1">
        {Object.values(UNLOCK_HINTS).map((hint) => (
          <li key={hint} className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <span className="mt-0.5 shrink-0">•</span>
            {hint}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Quality badge ─────────────────────────────────────────────────────────────

function QualityBadge({ workspaceId }: { workspaceId: string }) {
  const { data } = useRecommendationEffectiveness(workspaceId);

  if (!data) return null;

  const scored = data.by_type.filter((t) => t.quality_score !== null);
  const score =
    scored.length > 0
      ? Math.round(scored.reduce((s, t) => s + (t.quality_score ?? 0), 0) / scored.length)
      : null;

  if (score === null) {
    return (
      <Badge
        variant="outline"
        className="text-xs text-muted-foreground"
        data-testid="quality-badge-building"
      >
        Building data…
      </Badge>
    );
  }

  const colorClass =
    score >= 70
      ? "bg-emerald-500 text-white"
      : score >= 40
      ? "border-amber-400 text-amber-600"
      : "text-muted-foreground";

  return (
    <Badge variant={score >= 70 ? "default" : "outline"} className={`text-xs ${colorClass}`} data-testid="quality-badge">
      Quality {score}%
    </Badge>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function RecommendationsPanel({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useRecommendations(workspaceId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-36 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load recommendations. Try refreshing.
      </div>
    );
  }

  const recs = data?.recommendations ?? [];
  const suppressed = data?.suppressed_count ?? 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 pb-2">
          <Lightbulb className="h-4 w-4 text-amber-500" />
          <CardTitle className="text-sm">
            Recommendations
            {recs.length > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {recs.length} active · based on last 90 days
              </span>
            )}
          </CardTitle>
          <div className="ml-auto">
            <QualityBadge workspaceId={workspaceId} />
          </div>
        </CardHeader>
        <CardContent>
          {recs.length === 0 ? (
            <div className="py-4 text-center text-sm text-muted-foreground">
              No recommendations yet — keep running campaigns and recording deal outcomes.
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {recs.map((item) => (
                <RecommendationCard
                  key={`${item.type}-${item.generated_at}`}
                  item={item}
                  workspaceId={workspaceId}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <SuppressedHint count={suppressed} />
    </div>
  );
}
