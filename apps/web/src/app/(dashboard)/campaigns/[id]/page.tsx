"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useCampaign } from "@/features/campaigns/api/use-campaign";
import { CampaignStatusBadge } from "@/features/campaigns/ui/campaign-status-badge";
import { CampaignActions } from "@/features/campaigns/ui/campaign-actions";
import { AddRecipientsPanel } from "@/features/campaigns/ui/add-recipients-panel";
import { RecipientsList } from "@/features/campaigns/ui/recipients-list";
import { Skeleton } from "@/components/ui/skeleton";
import { CHANNEL_CONFIG } from "@/features/campaigns/types";
import { useWorkspace } from "@/hooks/use-workspace";

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { workspaceId } = useWorkspace();
  const { data: campaign, isLoading, isError } = useCampaign(id);

  if (isLoading) {
    return (
      <div className="p-6 space-y-4 max-w-3xl">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-32 w-full rounded-lg" />
      </div>
    );
  }

  if (isError || !campaign) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">Campaign not found.</p>
        <Link
          href="/campaigns"
          className="mt-2 inline-block text-sm text-primary underline-offset-2 hover:underline"
        >
          Back to campaigns
        </Link>
      </div>
    );
  }

  const ch = CHANNEL_CONFIG[campaign.channel];
  const showAddRecipients = campaign.status === "draft";
  const showHitlBanner = campaign.status === "pending_hitl";

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Breadcrumb */}
      <div className="text-xs text-muted-foreground">
        <Link href="/campaigns" className="hover:underline">
          Campaigns
        </Link>
        {" / "}
        <span>{campaign.name}</span>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold truncate">{campaign.name}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ch ? `${ch.emoji} ${ch.label}` : campaign.channel}
            {" · "}
            {campaign.recipient_count.toLocaleString()} recipients
          </p>
        </div>
        <CampaignStatusBadge status={campaign.status} />
      </div>

      {/* HITL banner */}
      {showHitlBanner && (
        <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-700 dark:bg-yellow-950/30 dark:text-yellow-300">
          <p className="font-medium">Manual review required</p>
          <p className="mt-0.5 text-xs">
            This campaign has more than 200 recipients. Review the recipient list
            below, then click <strong>Approve &amp; Launch</strong> to start sending.
          </p>
        </div>
      )}

      {/* Actions */}
      {workspaceId && (
        <CampaignActions campaign={campaign} workspaceId={workspaceId} />
      )}

      {/* Metadata */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border p-4 text-sm sm:grid-cols-3">
        {[
          { label: "Status",   value: <CampaignStatusBadge status={campaign.status} /> },
          { label: "Created",  value: new Date(campaign.created_at).toLocaleString() },
          { label: "Scheduled", value: campaign.scheduled_at ? new Date(campaign.scheduled_at).toLocaleString() : "—" },
          { label: "Started",  value: campaign.started_at ? new Date(campaign.started_at).toLocaleString() : "—" },
          { label: "Completed", value: campaign.completed_at ? new Date(campaign.completed_at).toLocaleString() : "—" },
        ].map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      {/* Add recipients — only in draft */}
      {showAddRecipients && workspaceId && (
        <AddRecipientsPanel campaignId={id} workspaceId={workspaceId} />
      )}

      {/* Recipients table */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold">Recipients</h2>
        <RecipientsList campaignId={id} />
      </div>
    </div>
  );
}
