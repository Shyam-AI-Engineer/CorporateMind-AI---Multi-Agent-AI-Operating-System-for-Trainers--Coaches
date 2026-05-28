"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  useLockCampaign,
  useLaunchCampaign,
  usePauseCampaign,
  useResumeCampaign,
  useCancelCampaign,
  useApproveCampaign,
} from "@/features/campaigns/api/use-campaigns";
import type { Campaign } from "@/features/campaigns/types";

interface CampaignActionsProps {
  campaign: Campaign;
  workspaceId: string;
}

export function CampaignActions({ campaign, workspaceId }: CampaignActionsProps) {
  const [confirming, setConfirming] = useState(false);

  const lock = useLockCampaign(workspaceId);
  const launch = useLaunchCampaign(workspaceId);
  const pause = usePauseCampaign(workspaceId);
  const resume = useResumeCampaign(workspaceId);
  const cancel = useCancelCampaign(workspaceId);
  const approve = useApproveCampaign(workspaceId);

  const busy =
    lock.isPending ||
    launch.isPending ||
    pause.isPending ||
    resume.isPending ||
    cancel.isPending ||
    approve.isPending;

  const { id, status } = campaign;

  return (
    <div className="flex flex-wrap gap-2">
      {status === "draft" && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => lock.mutate(id)}
        >
          {lock.isPending ? "Locking…" : "Lock recipients"}
        </Button>
      )}

      {status === "locked" && (
        <Button
          size="sm"
          disabled={busy}
          onClick={() => launch.mutate(id)}
        >
          {launch.isPending ? "Launching…" : "Launch campaign"}
        </Button>
      )}

      {status === "running" && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => pause.mutate(id)}
        >
          {pause.isPending ? "Pausing…" : "Pause"}
        </Button>
      )}

      {status === "paused" && (
        <Button
          size="sm"
          disabled={busy}
          onClick={() => resume.mutate(id)}
        >
          {resume.isPending ? "Resuming…" : "Resume"}
        </Button>
      )}

      {status === "pending_hitl" && (
        <Button
          size="sm"
          disabled={busy}
          onClick={() => approve.mutate(id)}
        >
          {approve.isPending ? "Approving…" : "Approve & Launch"}
        </Button>
      )}

      {(status === "draft" || status === "locked" || status === "paused" || status === "pending_hitl") && (
        <>
          {confirming ? (
            <>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => {
                  cancel.mutate(id);
                  setConfirming(false);
                }}
              >
                {cancel.isPending ? "Cancelling…" : "Confirm cancel"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirming(false)}
              >
                Keep
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              disabled={busy}
              onClick={() => setConfirming(true)}
            >
              Cancel campaign
            </Button>
          )}
        </>
      )}
    </div>
  );
}
