"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDeclineProposal } from "@/features/proposals/api/use-proposals";
import { ApiError } from "@/lib/api";

interface DeclineProposalDialogProps {
  proposalId: string | null;
  workspaceId: string | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeclineProposalDialog({
  proposalId,
  workspaceId,
  open,
  onOpenChange,
}: DeclineProposalDialogProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const decline = useDeclineProposal(workspaceId);

  function handleOpenChange(next: boolean) {
    if (!next) {
      setReason("");
      setError(null);
    }
    onOpenChange(next);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!proposalId) return;
    setError(null);
    try {
      await decline.mutateAsync({ proposalId, reason: reason.trim() || undefined });
      handleOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to record decline — please try again.",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record decline</DialogTitle>
          <DialogDescription>
            Optionally note why the client declined. This helps improve future proposals.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="decline-reason">Reason — optional</Label>
            <Textarea
              id="decline-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Budget constraints, timing not right…"
              disabled={decline.isPending}
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={decline.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={decline.isPending}
            >
              {decline.isPending ? "Saving…" : "Record decline"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
