"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useExtractProfile } from "@/features/trainer/api/use-trainer-profile";
import { ApiError } from "@/lib/api";

const MIN_CHARS = 20;
const MAX_CHARS = 20_000;

interface ExtractProfileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialContent?: string;
}

export function ExtractProfileDialog({
  open,
  onOpenChange,
  initialContent = "",
}: ExtractProfileDialogProps) {
  const [content, setContent] = useState(initialContent);
  const { mutate, isPending, error, reset } = useExtractProfile();

  const len = content.length;
  const tooShort = len > 0 && len < MIN_CHARS;
  const tooLong = len > MAX_CHARS;
  const canSubmit = len >= MIN_CHARS && len <= MAX_CHARS;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    mutate(
      { content },
      {
        onSuccess: () => {
          setContent("");
          onOpenChange(false);
        },
      }
    );
  }

  function handleClose(open: boolean) {
    if (!open) {
      reset();
      setContent(initialContent);
    }
    onOpenChange(open);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Extract Profile from Text</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-1">
          <p className="text-xs text-muted-foreground">
            Paste your bio, LinkedIn About, speaker reel description, or
            brochure text. We&apos;ll extract structured profile fields. This
            will overwrite any existing unlocked profile.
          </p>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="content">Source text</Label>
              <span
                className={`text-xs tabular-nums ${
                  tooShort || tooLong ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {len} / {MAX_CHARS}
              </span>
            </div>
            <textarea
              id="content"
              rows={12}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="e.g. I'm a leadership-development trainer with 12 years of experience working with IT and BFSI mid-managers. My signature program 'The Mindful Leader' has been delivered to 60+ Fortune 500 teams…"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none font-mono"
            />
            {tooShort && (
              <p className="text-xs text-destructive">
                Minimum {MIN_CHARS} characters.
              </p>
            )}
            {tooLong && (
              <p className="text-xs text-destructive">
                Maximum {MAX_CHARS} characters.
              </p>
            )}
          </div>

          {error && (
            <p className="text-xs text-destructive">
              {error instanceof ApiError ? error.message : "Extraction failed — please try again."}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || isPending}>
              {isPending ? "Extracting…" : "Extract profile"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
