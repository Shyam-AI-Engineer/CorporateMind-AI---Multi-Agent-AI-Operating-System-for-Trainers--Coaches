"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateLead } from "@/features/crm/api/use-leads";
import { useContacts } from "@/features/hr/api/use-contacts";
import { ContactSearch } from "@/features/hr/ui/contact-search";
import type { HRContact } from "@/features/hr/types";

const schema = z.object({
  score: z.coerce.number().int().min(0).max(100).default(0),
  notes: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface CreateLeadDialogProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
}

export function CreateLeadDialog({ open, onClose, workspaceId }: CreateLeadDialogProps) {
  const createLead = useCreateLead(workspaceId);
  const [selectedContact, setSelectedContact] = useState<HRContact | null>(null);
  const [contactRequired, setContactRequired] = useState(false);

  const { data: contactsData, isLoading: contactsLoading } = useContacts();
  const contacts = contactsData?.items ?? [];

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    if (!selectedContact) {
      setContactRequired(true);
      return;
    }
    setContactRequired(false);
    await createLead.mutateAsync({
      contact_id: selectedContact.id,
      workspace_id: workspaceId,
      score: values.score,
      notes: values.notes || undefined,
    });
    handleReset();
  }

  function handleReset() {
    reset();
    setSelectedContact(null);
    setContactRequired(false);
  }

  function handleClose() {
    handleReset();
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Lead to Pipeline</DialogTitle>
          <DialogDescription>
            Search for a contact to create a new lead in the &ldquo;Discovered&rdquo; stage.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Contact</Label>
            {contactsLoading ? (
              <div className="h-9 rounded-md border bg-muted/40 animate-pulse" />
            ) : (
              <ContactSearch
                contacts={contacts}
                selected={selectedContact}
                onSelect={(c) => {
                  setSelectedContact(c);
                  setContactRequired(false);
                }}
                onClear={() => setSelectedContact(null)}
              />
            )}
            {contactRequired && (
              <p className="text-xs text-destructive">Please select a contact.</p>
            )}
            {selectedContact && !selectedContact.is_contactable && (
              <p className="text-xs text-destructive">
                This contact is flagged non-contactable.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="score">Initial Score (0–100)</Label>
            <Input
              id="score"
              type="number"
              min={0}
              max={100}
              defaultValue={0}
              {...register("score")}
            />
            {errors.score && (
              <p className="text-xs text-destructive">{errors.score.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Input
              id="notes"
              placeholder="e.g. Met at SHRM conference"
              {...register("notes")}
            />
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="secondary" onClick={handleClose}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={isSubmitting || createLead.isPending}>
              {createLead.isPending ? "Creating…" : "Create Lead"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
