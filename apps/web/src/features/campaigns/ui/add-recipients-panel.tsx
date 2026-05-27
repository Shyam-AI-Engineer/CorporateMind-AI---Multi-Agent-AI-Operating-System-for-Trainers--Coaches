"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useAddRecipients } from "@/features/campaigns/api/use-campaigns";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface AddRecipientsPanelProps {
  campaignId: string;
  workspaceId: string;
}

export function AddRecipientsPanel({
  campaignId,
  workspaceId,
}: AddRecipientsPanelProps) {
  const [raw, setRaw] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const { mutate, isPending, isSuccess, error, reset } = useAddRecipients(workspaceId);

  function handleAdd() {
    setParseError(null);
    const ids = raw
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    const invalid = ids.filter((id) => !UUID_RE.test(id));
    if (invalid.length > 0) {
      setParseError(`Invalid contact IDs: ${invalid.slice(0, 3).join(", ")}${invalid.length > 3 ? "…" : ""}`);
      return;
    }
    if (ids.length === 0) {
      setParseError("Paste at least one contact UUID.");
      return;
    }

    mutate(
      { campaignId, contactIds: ids },
      {
        onSuccess: () => setRaw(""),
      }
    );
  }

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <Label className="text-sm font-medium">Add recipients</Label>
      <p className="text-xs text-muted-foreground">
        Paste contact UUIDs separated by commas or newlines.
      </p>
      <textarea
        className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs font-mono shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring min-h-[80px]"
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          reset();
          setParseError(null);
        }}
      />

      {parseError && (
        <p className="text-xs text-destructive">{parseError}</p>
      )}
      {error && (
        <p className="text-xs text-destructive">
          Server error — could not add recipients.
        </p>
      )}
      {isSuccess && (
        <p className="text-xs text-green-600">Recipients added successfully.</p>
      )}

      <Button size="sm" onClick={handleAdd} disabled={isPending || !raw.trim()}>
        {isPending ? "Adding…" : "Add recipients"}
      </Button>
    </div>
  );
}
