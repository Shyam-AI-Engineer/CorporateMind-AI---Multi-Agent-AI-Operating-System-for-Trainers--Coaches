"use client";

import { TrendingUp, Users, Megaphone, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePipelineStats } from "@/features/crm/api/use-pipeline-stats";
import { useCampaigns } from "@/features/campaigns/api/use-campaigns";
import { useWorkspace } from "@/hooks/use-workspace";

export function StatsHeader() {
  const { workspaceId } = useWorkspace();
  const { data: stats, isLoading: statsLoading } = usePipelineStats(workspaceId);
  const { data: campaigns, isLoading: campaignsLoading } = useCampaigns(workspaceId, { limit: 100 });

  const booked = stats?.stages.find((s) => s.stage === "booked")?.count ?? 0;
  const total = stats?.total ?? 0;
  const conversionRate = total > 0 ? Math.round((booked / total) * 100) : 0;

  const activeCampaigns = campaigns?.items.filter(
    (c) => c.status === "running" || c.status === "locked"
  ).length ?? 0;

  const metrics = [
    {
      label: "Pipeline Leads",
      value: statsLoading ? null : total,
      icon: Users,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Booked",
      value: statsLoading ? null : booked,
      icon: Target,
      color: "text-green-600",
      bg: "bg-green-50",
    },
    {
      label: "Active Campaigns",
      value: campaignsLoading ? null : activeCampaigns,
      icon: Megaphone,
      color: "text-violet-600",
      bg: "bg-violet-50",
    },
    {
      label: "Conversion Rate",
      value: statsLoading ? null : `${conversionRate}%`,
      icon: TrendingUp,
      color: "text-amber-600",
      bg: "bg-amber-50",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {metrics.map(({ label, value, icon: Icon, color, bg }) => (
        <Card key={label}>
          <CardHeader className="pb-2">
            <CardTitle>{label}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              {value === null ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <span className="text-2xl font-bold">{value}</span>
              )}
              <div className={`rounded-full p-2 ${bg}`}>
                <Icon className={`h-4 w-4 ${color}`} />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
