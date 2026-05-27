"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePipelineStats } from "@/features/crm/api/use-pipeline-stats";
import { useWorkspace } from "@/hooks/use-workspace";

const STAGE_COLORS: Record<string, string> = {
  discovered: "#3b82f6",
  engaged: "#6366f1",
  meeting_scheduled: "#8b5cf6",
  meeting_completed: "#f59e0b",
  booked: "#22c55e",
  lost: "#ef4444",
};

const STAGE_LABELS: Record<string, string> = {
  discovered: "Discovered",
  engaged: "Engaged",
  meeting_scheduled: "Scheduled",
  meeting_completed: "Completed",
  booked: "Booked",
  lost: "Lost",
};

export function PipelineFunnel() {
  const { workspaceId } = useWorkspace();
  const { data, isLoading, isError } = usePipelineStats(workspaceId);

  const chartData = (data?.stages ?? []).map((s) => ({
    stage: STAGE_LABELS[s.stage] ?? s.stage,
    count: s.count,
    key: s.stage,
  }));

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-semibold text-foreground">
          Pipeline Funnel
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        )}
        {isError && (
          <p className="text-sm text-muted-foreground">
            Unable to load pipeline data.
          </p>
        )}
        {!isLoading && !isError && (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 8, right: 24, top: 4, bottom: 4 }}
            >
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="stage"
                width={80}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(value: number) => [value, "Leads"]}
                contentStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.key}
                    fill={STAGE_COLORS[entry.key] ?? "#94a3b8"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        {!isLoading && !isError && data && (
          <p className="mt-2 text-xs text-muted-foreground">
            {data.total} total leads across all stages
          </p>
        )}
      </CardContent>
    </Card>
  );
}
