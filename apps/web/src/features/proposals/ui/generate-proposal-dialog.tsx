"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useGenerateProposal } from "@/features/proposals/api/use-proposals";
import { usePipelineLeads } from "@/features/crm/api/use-leads";
import { STAGE_CONFIG } from "@/features/crm/types";

const ELIGIBLE_STAGES = ["meeting_completed", "booked"] as const;

interface GenerateProposalDialogProps {
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (proposalId: string) => void;
}

export function GenerateProposalDialog({
  workspaceId,
  open,
  onOpenChange,
  onSuccess,
}: GenerateProposalDialogProps) {
  const [leadId, setLeadId] = useState("");
  const { leadsByStage, isLoading: leadsLoading } = usePipelineLeads(workspaceId);
  const { mutate, isPending, error } = useGenerateProposal(workspaceId);

  const eligibleLeads = ELIGIBLE_STAGES.flatMap((s) => leadsByStage[s] ?? []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!leadId) return;
    mutate(
      { lead_id: leadId, workspace_id: workspaceId },
      {
        onSuccess: (proposal) => {
          setLeadId("");
          onOpenChange(false);
          onSuccess?.(proposal.id);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate AI Proposal</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="lead">Select lead</Label>
            {leadsLoading ? (
              <p className="text-xs text-muted-foreground">Loading leads…</p>
            ) : eligibleLeads.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No eligible leads. Advance a lead to{" "}
                <span className="font-medium">Meeting Done</span> or{" "}
                <span className="font-medium">Booked</span> first.
              </p>
            ) : (
              <select
                id="lead"
                value={leadId}
                onChange={(e) => setLeadId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">— select a lead —</option>
                {ELIGIBLE_STAGES.flatMap((stage) =>
                  (leadsByStage[stage] ?? []).map((lead) => (
                    <option key={lead.id} value={lead.id}>
                      {STAGE_CONFIG[stage]?.label ?? stage} · Score {lead.score} ·{" "}
                      {lead.id.slice(0, 8)}…
                    </option>
                  ))
                )}
              </select>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            The AI will draft a personalised proposal based on the lead&apos;s
            meeting notes and profile.
          </p>

          {error && (
            <p className="text-xs text-destructive">
              Failed to generate proposal. Please try again.
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isPending || !leadId || eligibleLeads.length === 0}
            >
              {isPending ? "Generating…" : "Generate proposal"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
