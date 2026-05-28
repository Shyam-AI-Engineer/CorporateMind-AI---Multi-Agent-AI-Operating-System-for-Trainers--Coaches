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
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreatePost } from "@/features/social/api/use-posts";
import { SOCIAL_CHANNELS, SOCIAL_CHANNEL_CONFIG } from "@/features/social/types";

const schema = z.object({
  channel: z.enum(SOCIAL_CHANNELS as [string, ...string[]]),
  content: z.string().min(1, "Content is required").max(3000),
  hashtags_raw: z.string().optional(),
  scheduled_at: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface PostComposerDialogProps {
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PostComposerDialog({
  workspaceId,
  open,
  onOpenChange,
}: PostComposerDialogProps) {
  const { mutate, isPending, error } = useCreatePost(workspaceId);
  const [charCount, setCharCount] = useState(0);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { channel: "linkedin" },
  });

  const channel = watch("channel");
  const cfg = SOCIAL_CHANNEL_CONFIG[channel as keyof typeof SOCIAL_CHANNEL_CONFIG];

  function onSubmit(values: FormValues) {
    const hashtags = (values.hashtags_raw ?? "")
      .split(/[\s,#]+/)
      .map((h) => h.trim().replace(/^#/, ""))
      .filter(Boolean);

    mutate(
      {
        workspace_id: workspaceId,
        channel: values.channel,
        content: values.content,
        hashtags,
        scheduled_at: values.scheduled_at
          ? new Date(values.scheduled_at).toISOString()
          : undefined,
      },
      {
        onSuccess: () => {
          reset();
          setCharCount(0);
          onOpenChange(false);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Compose Post</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="channel">Channel</Label>
            <select
              id="channel"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              {...register("channel")}
            >
              {SOCIAL_CHANNELS.map((ch) => (
                <option key={ch} value={ch}>
                  {SOCIAL_CHANNEL_CONFIG[ch].emoji} {SOCIAL_CHANNEL_CONFIG[ch].label}
                </option>
              ))}
            </select>
            {cfg?.label === "LinkedIn" && (
              <p className="text-xs text-muted-foreground">
                Public company-page posts only. Personal DMs are never automated.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="content">Content</Label>
              <span className="text-xs text-muted-foreground">{charCount}/3000</span>
            </div>
            <textarea
              id="content"
              rows={5}
              placeholder="Write your post…"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              {...register("content", {
                onChange: (e) => setCharCount(e.target.value.length),
              })}
            />
            {errors.content && (
              <p className="text-xs text-destructive">{errors.content.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="hashtags_raw">Hashtags (optional)</Label>
            <Input
              id="hashtags_raw"
              placeholder="#leadership #training"
              {...register("hashtags_raw")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="scheduled_at">Schedule for (optional)</Label>
            <Input
              id="scheduled_at"
              type="datetime-local"
              {...register("scheduled_at")}
            />
            <p className="text-xs text-muted-foreground">
              Leave empty to save as draft.
            </p>
          </div>

          {error && (
            <p className="text-xs text-destructive">
              Failed to save post. Please try again.
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Saving…" : "Save post"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
