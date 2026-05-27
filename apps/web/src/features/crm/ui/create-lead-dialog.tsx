"use client";

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

const schema = z.object({
  contact_id: z.string().uuid("Must be a valid UUID (e.g. 550e8400-…)"),
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

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    await createLead.mutateAsync({
      contact_id: values.contact_id,
      workspace_id: workspaceId,
      score: values.score,
      notes: values.notes || undefined,
    });
    reset();
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Lead to Pipeline</DialogTitle>
          <DialogDescription>
            Enter the contact's ID to create a new lead in the "Discovered" stage.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="contact_id">Contact ID (UUID)</Label>
            <Input
              id="contact_id"
              placeholder="550e8400-e29b-41d4-a716-446655440000"
              {...register("contact_id")}
            />
            {errors.contact_id && (
              <p className="text-xs text-destructive">{errors.contact_id.message}</p>
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
              <Button type="button" variant="secondary" onClick={onClose}>
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
