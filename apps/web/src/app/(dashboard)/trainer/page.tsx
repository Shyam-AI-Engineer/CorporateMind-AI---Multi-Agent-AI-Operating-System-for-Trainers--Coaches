"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useTrainerProfile } from "@/features/trainer/api/use-trainer-profile";
import { EmptyProfile } from "@/features/trainer/ui/empty-profile";
import { ProfileView } from "@/features/trainer/ui/profile-view";
import { ExtractProfileDialog } from "@/features/trainer/ui/extract-profile-dialog";
import { EditProfileDialog } from "@/features/trainer/ui/edit-profile-dialog";

export default function TrainerPage() {
  const { data: profile, isLoading, isError, refetch } = useTrainerProfile();
  const [extractOpen, setExtractOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-xl font-semibold">Trainer Profile</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Your profile is the source of truth for personalized outreach, HR
          contact ranking, and proposal generation.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 w-full rounded-lg" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
          </div>
          <Skeleton className="h-32 w-full rounded-lg" />
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="text-sm text-destructive">Failed to load profile.</p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      ) : profile ? (
        <ProfileView
          profile={profile}
          onEdit={() => setEditOpen(true)}
          onReextract={() => setExtractOpen(true)}
        />
      ) : (
        <EmptyProfile onExtract={() => setExtractOpen(true)} />
      )}

      <ExtractProfileDialog open={extractOpen} onOpenChange={setExtractOpen} />

      {profile && (
        <EditProfileDialog
          profile={profile}
          open={editOpen}
          onOpenChange={setEditOpen}
        />
      )}
    </div>
  );
}
