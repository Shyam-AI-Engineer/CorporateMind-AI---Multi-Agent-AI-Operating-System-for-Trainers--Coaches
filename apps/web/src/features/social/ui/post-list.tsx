"use client";

import { useState } from "react";
import { useSocialPosts } from "@/features/social/api/use-posts";
import { PostCard } from "@/features/social/ui/post-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { POST_STATUS_CONFIG } from "@/features/social/types";

const STATUS_FILTERS = ["all", "draft", "scheduled", "published"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

interface PostListProps {
  workspaceId: string;
  onCompose: () => void;
}

export function PostList({ workspaceId, onCompose }: PostListProps) {
  const { data, isLoading, isError, refetch } = useSocialPosts(workspaceId);
  const [filter, setFilter] = useState<StatusFilter>("all");

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">Failed to load posts.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const all = data?.items ?? [];
  const posts = filter === "all" ? all : all.filter((p) => p.status === filter);

  if (all.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No posts yet. Compose your first one.
        </p>
        <Button size="sm" onClick={onCompose}>
          Compose post
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Status filter pills */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => {
          const count =
            f === "all" ? all.length : all.filter((p) => p.status === f).length;
          const cfg = f !== "all" ? POST_STATUS_CONFIG[f] : null;
          const active = filter === f;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-muted"
              }`}
            >
              {cfg ? cfg.label : "All"} ({count})
            </button>
          );
        })}
      </div>

      {posts.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No {filter} posts.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {posts.map((post) => (
            <PostCard key={post.id} post={post} workspaceId={workspaceId} />
          ))}
        </div>
      )}
    </div>
  );
}
