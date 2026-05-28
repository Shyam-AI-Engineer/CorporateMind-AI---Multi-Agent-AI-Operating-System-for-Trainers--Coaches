"use client";

import { useState } from "react";
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

      <PostList workspaceId={workspaceId} onCompose={() => setDialogOpen(true)} />

      <PostComposerDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
