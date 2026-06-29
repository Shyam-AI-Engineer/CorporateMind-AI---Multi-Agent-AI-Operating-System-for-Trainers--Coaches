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
import { useAcceptProposal } from "@/features/proposals/api/use-proposals";
import { ApiError } from "@/lib/api";

interface AcceptProposalDialogProps {
  proposalId: string | null;
  workspaceId: string | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AcceptProposalDialog({
  proposalId,
  workspaceId,
  open,
  onOpenChange,
}: AcceptProposalDialogProps) {
  const [actualValue, setActualValue] = useState("");
  const [expectedValue, setExpectedValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const accept = useAcceptProposal(workspaceId);

  function handleOpenChange(next: boolean) {
    if (!next) {
      setActualValue("");
      setExpectedValue("");
      setError(null);
    }
    onOpenChange(next);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!proposalId) return;
    const actual = parseFloat(actualValue);
    if (!actualValue || isNaN(actual) || actual <= 0) {
      setError("Deal value must be greater than zero.");
      return;
    }
    setError(null);
    try {
      const expected = expectedValue ? parseFloat(expectedValue) : undefined;
      await accept.mutateAsync({
        proposalId,
        actual_value_inr: actual,
        ...(expected !== undefined && !isNaN(expected) && { expected_value_inr: expected }),
      });
      handleOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to record acceptance — please try again.",
      );
    }
  }

  const canSubmit = !!actualValue && parseFloat(actualValue) > 0 && !accept.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record acceptance</DialogTitle>
          <DialogDescription>
            Record that the client has accepted this proposal and enter the confirmed deal value.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="actual-value">Deal value (₹) *</Label>
            <input
              id="actual-value"
              type="number"
              min="0.01"
              step="0.01"
              value={actualValue}
              onChange={(e) => setActualValue(e.target.value)}
              placeholder="e.g. 150000"
              disabled={accept.isPending}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="expected-value">Expected value (₹) — optional</Label>
            <input
              id="expected-value"
              type="number"
              min="0.01"
              step="0.01"
              value={expectedValue}
              onChange={(e) => setExpectedValue(e.target.value)}
              placeholder="Leave blank to keep existing value"
              disabled={accept.isPending}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
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
              disabled={accept.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {accept.isPending ? "Saving…" : "Record acceptance"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
