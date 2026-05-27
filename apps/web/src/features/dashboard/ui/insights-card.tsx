"use client";

import { Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const PLACEHOLDER_INSIGHTS = [
  {
    id: 1,
    text: "3 leads have been in 'engaged' for over 14 days — consider scheduling a follow-up.",
    type: "nudge",
  },
  {
    id: 2,
    text: "Your email campaign last week had a 34% open rate — 12% above your average.",
    type: "win",
  },
  {
    id: 3,
    text: "2 meetings scheduled for next week. Proposals can be auto-generated when ready.",
    type: "info",
  },
];

const TYPE_VARIANT: Record<string, "warning" | "success" | "secondary"> = {
  nudge: "warning",
  win: "success",
  info: "secondary",
};

export function InsightsCard() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold text-foreground">
            AI Insights
          </CardTitle>
          <div className="flex items-center gap-1.5 rounded-full bg-violet-50 px-2 py-0.5">
            <Sparkles className="h-3 w-3 text-violet-600" />
            <span className="text-xs font-medium text-violet-700">Powered by AI</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {PLACEHOLDER_INSIGHTS.map((insight) => (
            <li key={insight.id} className="flex items-start gap-3">
              <Badge
                variant={TYPE_VARIANT[insight.type]}
                className="mt-0.5 shrink-0 capitalize"
              >
                {insight.type}
              </Badge>
              <p className="text-sm leading-snug text-muted-foreground">
                {insight.text}
              </p>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground/60">
          Live AI insights powered by AnalyticsAgent — available in Phase 2.
        </p>
      </CardContent>
    </Card>
  );
}
