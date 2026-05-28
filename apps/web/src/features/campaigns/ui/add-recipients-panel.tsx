"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useAddRecipients } from "@/features/campaigns/api/use-campaigns";
import { useContacts } from "@/features/hr/api/use-contacts";
import { ContactMultiSearch } from "@/features/hr/ui/contact-multi-search";
import type { HRContact } from "@/features/hr/types";

interface AddRecipientsPanelProps {
  campaignId: string;
  workspaceId: string;
}

export function AddRecipientsPanel({
  campaignId,
  workspaceId,
}: AddRecipientsPanelProps) {
  const [selected, setSelected] = useState<HRContact[]>([]);

  const { data: contactsData, isLoading: contactsLoading } = useContacts();
  const contacts = contactsData?.items ?? [];

  const { mutate, isPending, isSuccess, error, reset } = useAddRecipients(workspaceId);

  function handleAdd(c: HRContact) {
    setSelected((prev) => [...prev, c]);
    reset();
  }

  function handleRemove(id: string) {
    setSelected((prev) => prev.filter((c) => c.id !== id));
  }

  function handleClearAll() {
    setSelected([]);
    reset();
  }

  function handleSubmit() {
    if (selected.length === 0) return;
    mutate(
      { campaignId, contactIds: selected.map((c) => c.id) },
      { onSuccess: () => setSelected([]) }
    );
  }

  const buttonLabel = isPending
    ? "Adding…"
    : selected.length > 0
    ? `Add ${selected.length} recipient${selected.length === 1 ? "" : "s"}`
    : "Add recipients";

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <Label className="text-sm font-medium">Add recipients</Label>
      <p className="text-xs text-muted-foreground">
        Search and select contacts to include in this campaign.
      </p>

      {contactsLoading ? (
        <div className="h-9 rounded-md border bg-muted/40 animate-pulse" />
      ) : (
        <ContactMultiSearch
          contacts={contacts}
          selected={selected}
          onAdd={handleAdd}
          onRemove={handleRemove}
          onClearAll={handleClearAll}
        />
      )}

      {error && (
        <p className="text-xs text-destructive">
          Server error — could not add recipients.
        </p>
      )}
      {isSuccess && (
        <p className="text-xs text-green-600">Recipients added successfully.</p>
      )}

      <Button
        size="sm"
        onClick={handleSubmit}
        disabled={isPending || selected.length === 0}
      >
        {buttonLabel}
      </Button>
    </div>
  );
}
