"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateCampaign } from "@/features/campaigns/api/use-campaigns";
import { SUPPORTED_CHANNELS, CHANNEL_CONFIG, LIVE_CHANNELS } from "@/features/campaigns/types";

const schema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  channel: z.enum(SUPPORTED_CHANNELS as [string, ...string[]]),
  scheduled_at: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface CreateCampaignDialogProps {
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateCampaignDialog({
  workspaceId,
  open,
  onOpenChange,
}: CreateCampaignDialogProps) {
  const { mutate, isPending, error } = useCreateCampaign(workspaceId);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { channel: "email" },
  });

  function onSubmit(values: FormValues) {
    mutate(
      {
        ...values,
        workspace_id: workspaceId,
        scheduled_at: values.scheduled_at || undefined,
      },
      {
        onSuccess: () => {
          reset();
          onOpenChange(false);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Campaign</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="name">Campaign name</Label>
            <Input id="name" placeholder="Q2 Outreach" {...register("name")} />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="channel">Channel</Label>
            <select
              id="channel"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              {...register("channel")}
            >
              {SUPPORTED_CHANNELS.map((ch) => (
                <option key={ch} value={ch} disabled={!LIVE_CHANNELS.has(ch)}>
                  {CHANNEL_CONFIG[ch]?.emoji} {CHANNEL_CONFIG[ch]?.label ?? ch}
                  {!LIVE_CHANNELS.has(ch) ? " (coming soon)" : ""}
                </option>
              ))}
            </select>
            {errors.channel && (
              <p className="text-xs text-destructive">{errors.channel.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="scheduled_at">Schedule for (optional)</Label>
            <Input
              id="scheduled_at"
              type="datetime-local"
              {...register("scheduled_at")}
            />
          </div>

          {error && (
            <p className="text-xs text-destructive">
              Failed to create campaign. Please try again.
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
            <Button type="submit" disabled={isPending}>
              {isPending ? "Creating…" : "Create campaign"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
