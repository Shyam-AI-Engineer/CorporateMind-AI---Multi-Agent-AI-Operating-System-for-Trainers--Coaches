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
import { useRejectProposal } from "@/features/proposals/api/use-proposals";
import { ApiError } from "@/lib/api";

interface ProposalRejectDialogProps {
  proposalId: string | null;
  workspaceId: string | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProposalRejectDialog({
  proposalId,
  workspaceId,
  open,
  onOpenChange,
}: ProposalRejectDialogProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reject = useRejectProposal(workspaceId);

  function handleOpenChange(next: boolean) {
    if (!next) {
      setReason("");
      setError(null);
    }
    onOpenChange(next);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!proposalId || !reason.trim()) return;
    setError(null);
    try {
      await reject.mutateAsync({ proposalId, reason: reason.trim() });
      handleOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to reject — please try again.",
      );
    }
  }

  const trimmed = reason.trim();
  const canSubmit = !!trimmed && !reject.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reject proposal</DialogTitle>
          <DialogDescription>
            Provide a reason so the trainer knows what to improve.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="reject-reason">Reason</Label>
            <Textarea
              id="reject-reason"
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Explain why the proposal is being rejected…"
              disabled={reject.isPending}
            />
            {!trimmed && reason.length > 0 && (
              <p className="text-xs text-destructive">Reason must not be empty.</p>
            )}
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
              disabled={reject.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!canSubmit}
            >
              {reject.isPending ? "Rejecting…" : "Reject proposal"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
