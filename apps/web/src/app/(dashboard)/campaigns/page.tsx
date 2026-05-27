"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CampaignList } from "@/features/campaigns/ui/campaign-list";
import { CreateCampaignDialog } from "@/features/campaigns/ui/create-campaign-dialog";
import { useWorkspace } from "@/hooks/use-workspace";

export default function CampaignsPage() {
  const { workspaceId } = useWorkspace();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (!workspaceId) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">Loading workspace…</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Campaigns</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Manage and launch multi-channel outreach campaigns.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>New campaign</Button>
      </div>

      <CampaignList
        workspaceId={workspaceId}
        onNewCampaign={() => setDialogOpen(true)}
      />

      <CreateCampaignDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
