"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Info, ThumbsDown, ThumbsUp, TrendingUp, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useSubmitFeedback } from "@/features/analytics/api/use-analytics";
import type { RecommendationFeedbackOutcome, RecommendationItem } from "@/features/analytics/types";

// ── Icon per recommendation type ─────────────────────────────────────────────

function RecIcon({ type }: { type: string }) {
  switch (type) {
    case "industry":
      return <TrendingUp className="h-4 w-4 text-violet-500" />;
    case "topic":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    case "pricing":
      return <Info className="h-4 w-4 text-amber-500" />;
    case "campaign":
      return <TrendingUp className="h-4 w-4 text-blue-500" />;
    case "channel":
      return <TrendingUp className="h-4 w-4 text-sky-500" />;
    default:
      return <Info className="h-4 w-4 text-muted-foreground" />;
  }
}

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({
  level,
  score,
}: {
  level: string;
  score: number;
}) {
  if (level === "high") {
    return (
      <Badge variant="default" className="bg-emerald-500 text-white text-xs">
        HIGH {score}
      </Badge>
    );
  }
  if (level === "medium") {
    return (
      <Badge variant="outline" className="border-amber-400 text-amber-600 text-xs">
        MED {score}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-muted-foreground text-xs">
      LOW {score}
    </Badge>
  );
}

// ── Feedback buttons ──────────────────────────────────────────────────────────

function FeedbackButtons({
  workspaceId,
  recType,
}: {
  workspaceId: string;
  recType: string;
}) {
  const [submitted, setSubmitted] = useState<RecommendationFeedbackOutcome | null>(null);
  const mutation = useSubmitFeedback(workspaceId);

  function handleFeedback(outcome: RecommendationFeedbackOutcome) {
    if (submitted) return;
    setSubmitted(outcome);
    mutation.mutate({ workspace_id: workspaceId, rec_type: recType, outcome });
  }

  if (submitted) {
    return (
      <span className="text-xs text-muted-foreground" data-testid={`feedback-submitted-${recType}`}>
        Thanks for your feedback
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1" data-testid={`feedback-buttons-${recType}`}>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        aria-label="Helpful"
        onClick={() => handleFeedback("helpful")}
        disabled={mutation.isPending}
        data-testid={`feedback-helpful-${recType}`}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        aria-label="Not helpful"
        onClick={() => handleFeedback("not_helpful")}
        disabled={mutation.isPending}
        data-testid={`feedback-not-helpful-${recType}`}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        aria-label="Dismiss"
        onClick={() => handleFeedback("dismissed")}
        disabled={mutation.isPending}
        data-testid={`feedback-dismissed-${recType}`}
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

// ── Main card ─────────────────────────────────────────────────────────────────

export function RecommendationCard({
  item,
  workspaceId,
}: {
  item: RecommendationItem;
  workspaceId: string;
}) {
  const generatedAgo = (() => {
    const diffMs = Date.now() - new Date(item.generated_at).getTime();
    const hours = Math.round(diffMs / (1000 * 60 * 60));
    if (hours < 1) return "just now";
    if (hours === 1) return "1h ago";
    return `${hours}h ago`;
  })();

  return (
    <Card data-testid={`recommendation-card-${item.type}`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <RecIcon type={item.type} />
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {item.type}
            </span>
          </div>
          <ConfidenceBadge level={item.confidence_level} score={item.confidence_score} />
        </div>
        <p className="mt-1 text-sm font-semibold leading-snug">{item.title}</p>
      </CardHeader>

      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">{item.rationale}</p>

        <div className="rounded-md bg-muted/50 px-3 py-2">
          <p className="text-xs font-medium">Action</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{item.action}</p>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-2">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>
              <span className="font-medium">Evidence:</span>{" "}
              {item.evidence_strength}
            </span>
            <span>
              <span className="font-medium">Sample:</span> {item.sample_size}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <FeedbackButtons workspaceId={workspaceId} recType={item.type} />
            <span className="text-xs text-muted-foreground">{generatedAgo}</span>
          </div>
        </div>

        {item.low_confidence && (
          <div className="flex items-center gap-1.5 text-xs text-amber-600">
            <AlertCircle className="h-3 w-3 shrink-0" />
            Limited data — interpret with caution.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
