"use client";

/**
 * ApprovalCountBadge — the Phase-1 in-app notification (ADR-0008 §F).
 *
 * Shows the number of follow-ups awaiting human review for the current
 * workspace.  Renders nothing when the feature flag is off, there's no
 * workspace, the count is zero, or the query is still loading — so it's safe to
 * drop into the sidebar and the tab label without layout churn.
 */

import { Badge } from "@/components/ui/badge";
import { useFollowUps } from "@/features/crm/api/use-activities";
import { useWorkspace } from "@/hooks/use-workspace";
import { FOLLOWUP_APPROVAL_ENABLED } from "@/lib/flags";

export function ApprovalCountBadge({ className }: { className?: string }) {
  const { workspaceId } = useWorkspace();

  // Hook order must be stable — always call, then decide whether to render.
  const { data } = useFollowUps({
    workspace_id: FOLLOWUP_APPROVAL_ENABLED ? workspaceId : null,
    status: "awaiting_approval",
    limit: 1,
  });

  if (!FOLLOWUP_APPROVAL_ENABLED) return null;
  const count = data?.total ?? 0;
  if (count === 0) return null;

  return (
    <Badge variant="warning" className={className}>
      {count}
    </Badge>
  );
}
