"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PostList } from "@/features/social/ui/post-list";
import { PostComposerDialog } from "@/features/social/ui/post-composer-dialog";
import { useWorkspace } from "@/hooks/use-workspace";

export default function SocialPage() {
  const { workspaceId } = useWorkspace();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (!workspaceId) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">Loading workspace…</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Social</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Schedule posts across Instagram, Facebook, Telegram, and LinkedIn.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>Compose post</Button>
      </div>

      {/* Publishing not yet wired — show a clear alpha notice */}
      <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          <span className="font-medium">Publishing not yet active.</span>{" "}
          Posts are saved as drafts. Channel adapters for Instagram, Facebook,
          Telegram, and LinkedIn are coming in the next sprint — scheduled posts
          will auto-publish once they&apos;re wired.
        </p>
      </div>

      <PostList workspaceId={workspaceId} onCompose={() => setDialogOpen(true)} />

      <PostComposerDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
