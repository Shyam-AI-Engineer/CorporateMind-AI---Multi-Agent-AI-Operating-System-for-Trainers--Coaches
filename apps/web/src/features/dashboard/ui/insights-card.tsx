"use client";

import { Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function InsightsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold text-foreground">
          AI Insights
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-muted/30 py-8 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-100">
            <Sparkles className="h-5 w-5 text-violet-600" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">AI Insights — Phase 2</p>
            <p className="max-w-xs text-xs text-muted-foreground">
              The AnalyticsAgent will surface nudges, wins, and anomalies here
              once your first campaign completes.
            </p>
          </div>
          <Badge variant="secondary" className="text-xs">
            Coming in Phase 2
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
