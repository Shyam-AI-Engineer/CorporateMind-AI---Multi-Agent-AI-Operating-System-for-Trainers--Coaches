"use client";

import { Megaphone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCampaigns } from "@/features/campaigns/api/use-campaigns";
import { useWorkspace } from "@/hooks/use-workspace";
import type { BadgeVariant } from "@/components/ui/badge";

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  running: "success",
  locked: "warning",
  draft: "secondary",
  paused: "outline",
  completed: "secondary",
  cancelled: "destructive",
};

const CHANNEL_LABEL: Record<string, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  instagram: "Instagram",
  linkedin: "LinkedIn",
};

export function CampaignsSummary() {
  const { workspaceId } = useWorkspace();
  const { data, isLoading, isError } = useCampaigns(workspaceId, { limit: 6 });

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-semibold text-foreground">
          Recent Campaigns
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}
        {isError && (
          <p className="text-sm text-muted-foreground">
            Unable to load campaigns.
          </p>
        )}
        {!isLoading && !isError && data?.items.length === 0 && (
          <div className="flex flex-col items-center py-8 text-center">
            <Megaphone className="mb-2 h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No campaigns yet.</p>
          </div>
        )}
        {!isLoading && !isError && data && data.items.length > 0 && (
          <ul className="divide-y">
            {data.items.map((campaign) => (
              <li key={campaign.id} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{campaign.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {CHANNEL_LABEL[campaign.channel] ?? campaign.channel} ·{" "}
                    {campaign.recipient_count} recipients
                  </p>
                </div>
                <Badge
                  variant={STATUS_VARIANT[campaign.status] ?? "secondary"}
                  className="ml-3 shrink-0 capitalize"
                >
                  {campaign.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
