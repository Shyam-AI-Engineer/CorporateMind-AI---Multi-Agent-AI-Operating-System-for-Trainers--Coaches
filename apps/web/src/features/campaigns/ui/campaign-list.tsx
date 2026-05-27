"use client";

import Link from "next/link";
import { useCampaignList } from "@/features/campaigns/api/use-campaigns";
import { CampaignStatusBadge } from "@/features/campaigns/ui/campaign-status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CHANNEL_CONFIG } from "@/features/campaigns/types";
import { Button } from "@/components/ui/button";

interface CampaignListProps {
  workspaceId: string;
  onNewCampaign: () => void;
}

export function CampaignList({ workspaceId, onNewCampaign }: CampaignListProps) {
  const { data, isLoading, isError, refetch } = useCampaignList(workspaceId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">Failed to load campaigns.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const campaigns = data?.items ?? [];

  if (campaigns.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No campaigns yet. Create your first one.
        </p>
        <Button size="sm" onClick={onNewCampaign}>
          New campaign
        </Button>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Channel</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Recipients</th>
            <th className="px-4 py-3 font-medium">Created</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {campaigns.map((c) => {
            const ch = CHANNEL_CONFIG[c.channel];
            return (
              <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                <td className="px-4 py-3 font-medium">{c.name}</td>
                <td className="px-4 py-3 text-muted-foreground">
                  {ch ? `${ch.emoji} ${ch.label}` : c.channel}
                </td>
                <td className="px-4 py-3">
                  <CampaignStatusBadge status={c.status} />
                </td>
                <td className="px-4 py-3 tabular-nums text-muted-foreground">
                  {c.recipient_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {new Date(c.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/campaigns/${c.id}`}
                    className="text-xs text-primary underline-offset-2 hover:underline"
                  >
                    View
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
