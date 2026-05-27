"use client";

import { useCampaignRecipients } from "@/features/campaigns/api/use-campaign";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { BadgeVariant } from "@/components/ui/badge";

const RECIPIENT_STATUS: Record<string, { label: string; variant: BadgeVariant }> = {
  pending:  { label: "Pending",  variant: "secondary"   },
  sent:     { label: "Sent",     variant: "success"      },
  failed:   { label: "Failed",   variant: "destructive"  },
  bounced:  { label: "Bounced",  variant: "warning"      },
};

interface RecipientsListProps {
  campaignId: string;
}

export function RecipientsList({ campaignId }: RecipientsListProps) {
  const { data, isLoading, isError } = useCampaignRecipients(campaignId, 50);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-sm text-destructive">Failed to load recipients.</p>
    );
  }

  if (!data?.length) {
    return (
      <p className="text-sm text-muted-foreground">No recipients added yet.</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">Contact ID</th>
            <th className="pb-2 pr-4 font-medium">Status</th>
            <th className="pb-2 pr-4 font-medium">Sent at</th>
            <th className="pb-2 font-medium">Error</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {data.map((r) => {
            const cfg = RECIPIENT_STATUS[r.status] ?? {
              label: r.status,
              variant: "secondary" as BadgeVariant,
            };
            return (
              <tr key={r.id} className="py-1.5">
                <td className="py-1.5 pr-4 font-mono text-muted-foreground">
                  {r.contact_id.slice(0, 8)}…
                </td>
                <td className="py-1.5 pr-4">
                  <Badge variant={cfg.variant}>{cfg.label}</Badge>
                </td>
                <td className="py-1.5 pr-4 text-muted-foreground">
                  {r.sent_at
                    ? new Date(r.sent_at).toLocaleString()
                    : "—"}
                </td>
                <td className="py-1.5 text-destructive">
                  {r.error_code ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
