"use client";

import { useState } from "react";
import { Calendar } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useScheduleMeeting } from "@/features/crm/api/use-leads";
import { ApiError } from "@/lib/api";

interface MeetingSchedulerDialogProps {
  leadId: string;
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MeetingSchedulerDialog({
  leadId,
  workspaceId,
  open,
  onOpenChange,
}: MeetingSchedulerDialogProps) {
  const [meetingAt, setMeetingAt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { mutateAsync, isPending } = useScheduleMeeting(workspaceId);

  async function handleSubmit() {
    if (!meetingAt) return;
    setError(null);
    try {
      // Convert local datetime-local value to an ISO-8601 UTC string.
      await mutateAsync({ leadId, meetingAt: new Date(meetingAt).toISOString() });
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to set meeting time — please try again.",
      );
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      setMeetingAt("");
      setError(null);
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Set meeting time</DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="meeting-at">Date and time</Label>
            <div className="relative">
              <Calendar className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                id="meeting-at"
                type="datetime-local"
                value={meetingAt}
                onChange={(e) => setMeetingAt(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              />
            </div>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!meetingAt || isPending}
            onClick={() => void handleSubmit()}
          >
            {isPending ? "Saving…" : "Set time"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
