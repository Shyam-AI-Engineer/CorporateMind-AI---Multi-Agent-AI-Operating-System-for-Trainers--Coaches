"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDeletePost } from "@/features/social/api/use-posts";
import {
  POST_STATUS_CONFIG,
  SOCIAL_CHANNEL_CONFIG,
  type SocialPost,
} from "@/features/social/types";

interface PostCardProps {
  post: SocialPost;
  workspaceId: string;
}

export function PostCard({ post, workspaceId }: PostCardProps) {
  const [confirming, setConfirming] = useState(false);
  const { mutate: deletePost, isPending } = useDeletePost(workspaceId);

  const statusCfg = POST_STATUS_CONFIG[post.status] ?? {
    label: post.status,
    variant: "secondary" as const,
  };
  const channelCfg =
    SOCIAL_CHANNEL_CONFIG[post.channel as keyof typeof SOCIAL_CHANNEL_CONFIG];
  const isDeletable = post.status === "draft" || post.status === "scheduled";

  return (
    <div className="rounded-lg border p-4 space-y-3 hover:border-muted-foreground/30 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span>{channelCfg?.emoji ?? "📣"}</span>
          <span>{channelCfg?.label ?? post.channel}</span>
        </div>
        <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
      </div>

      <p className="text-sm text-muted-foreground line-clamp-3 whitespace-pre-wrap">
        {post.content}
      </p>

      {post.hashtags.length > 0 && (
        <p className="text-xs text-primary/70">
          {post.hashtags.map((h) => `#${h}`).join(" ")}
        </p>
      )}

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {post.scheduled_at
            ? `Scheduled: ${new Date(post.scheduled_at).toLocaleString()}`
            : post.published_at
            ? `Published: ${new Date(post.published_at).toLocaleString()}`
            : `Created: ${new Date(post.created_at).toLocaleDateString()}`}
        </p>

        {isDeletable && (
          confirming ? (
            <div className="flex gap-1.5">
              <Button
                size="sm"
                variant="destructive"
                disabled={isPending}
                onClick={() => {
                  deletePost(post.id);
                  setConfirming(false);
                }}
              >
                {isPending ? "Deleting…" : "Confirm"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirming(false)}
              >
                Keep
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              onClick={() => setConfirming(true)}
            >
              Delete
            </Button>
          )
        )}
      </div>
    </div>
  );
}
