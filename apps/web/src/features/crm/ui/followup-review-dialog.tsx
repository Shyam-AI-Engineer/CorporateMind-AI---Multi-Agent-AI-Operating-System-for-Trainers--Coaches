"use client";

/**
 * FollowupReviewDialog — review + edit + approve/reject a parked follow-up.
 *
 * Approve sends the draft through the full ComplianceGuard (server side). A
 * compliance block is surfaced inline and the dialog stays open. Editing is
 * disabled once the draft is no longer editable; Approve is disabled while there
 * are unsaved edits so the trainer never sends stale copy.
 */

import { useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import { AlertCircle, Mail, Send, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useApproveFollowup,
  useEditFollowupDraft,
  useFollowupReview,
  useRejectFollowup,
} from "@/features/crm/api/use-followup-approval";
import { ApiError } from "@/lib/api";

interface Props {
  taskId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FollowupReviewDialog({ taskId, open, onOpenChange }: Props) {
  const { data, isLoading, isError } = useFollowupReview(open ? taskId : null);
  const approve = useApproveFollowup();
  const reject = useRejectFollowup();
  const edit = useEditFollowupDraft();

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [blockMsg, setBlockMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Seed the editable fields when the draft loads / changes.
  useEffect(() => {
    if (data?.draft) {
      setSubject(data.draft.subject ?? "");
      setBody(data.draft.body ?? "");
      setBlockMsg(null);
      setActionError(null);
    }
  }, [data?.draft]);

  const draft = data?.draft ?? null;
  const editable = draft?.status === "draft";
  const dirty =
    !!draft &&
    (subject !== (draft.subject ?? "") || body !== (draft.body ?? ""));
  const busy = approve.isPending || reject.isPending || edit.isPending;

  function describe(err: unknown): string {
    return err instanceof ApiError ? err.message : "Something went wrong.";
  }

  async function onSave() {
    if (!taskId) return;
    setActionError(null);
    try {
      await edit.mutateAsync({ taskId, subject: subject || null, body });
    } catch (err) {
      setActionError(describe(err));
    }
  }

  async function onApprove() {
    if (!taskId) return;
    setActionError(null);
    setBlockMsg(null);
    try {
      const res = await approve.mutateAsync(taskId);
      if (res.status === "blocked") {
        setBlockMsg(
          res.compliance_reason
            ? `Blocked by compliance: ${res.compliance_reason}. The follow-up was cancelled and not sent.`
            : "Blocked by compliance. The follow-up was cancelled and not sent."
        );
      } else {
        onOpenChange(false);
      }
    } catch (err) {
      setActionError(describe(err));
    }
  }

  async function onReject() {
    if (!taskId) return;
    setActionError(null);
    try {
      await reject.mutateAsync({ taskId });
      onOpenChange(false);
    } catch (err) {
      setActionError(describe(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Review follow-up</DialogTitle>
          <DialogDescription>
            Approve to send through compliance, edit the draft, or reject.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : isError || !data ? (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            Failed to load the follow-up.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Reply context */}
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                <Mail className="h-3.5 w-3.5" />
                <span>
                  Reply from {data.reply?.from_address ?? "unknown sender"}
                </span>
                {data.lead_stage && (
                  <Badge variant="outline">{data.lead_stage}</Badge>
                )}
                {data.reply?.received_at && (
                  <span className="ml-auto">
                    {format(parseISO(data.reply.received_at), "d MMM yyyy, HH:mm")}
                  </span>
                )}
              </div>
              {data.reply?.subject && (
                <p className="text-sm font-medium">{data.reply.subject}</p>
              )}
              <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
                {data.reply?.snippet ?? "(reply text unavailable)"}
              </p>
            </div>

            {/* Editable draft */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                Subject
              </label>
              <Input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                disabled={!editable || busy}
                placeholder="Subject"
              />
              <label className="text-xs font-medium text-muted-foreground">
                Draft reply
              </label>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={!editable || busy}
                rows={8}
              />
              {!editable && (
                <p className="text-xs text-muted-foreground">
                  This draft can no longer be edited (status: {draft?.status}).
                </p>
              )}
            </div>

            {blockMsg && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{blockMsg}</span>
              </div>
            )}
            {actionError && (
              <p className="text-sm text-destructive">{actionError}</p>
            )}
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            variant="ghost"
            onClick={() => void onReject()}
            disabled={busy || !data}
          >
            <X className="mr-1.5 h-4 w-4" />
            Reject
          </Button>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => void onSave()}
              disabled={!editable || !dirty || busy}
            >
              {edit.isPending ? "Saving…" : "Save edits"}
            </Button>
            <Button
              onClick={() => void onApprove()}
              disabled={busy || !data || dirty || !!blockMsg}
              title={dirty ? "Save your edits before approving" : undefined}
            >
              <Send className="mr-1.5 h-4 w-4" />
              {approve.isPending ? "Sending…" : "Approve & send"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
