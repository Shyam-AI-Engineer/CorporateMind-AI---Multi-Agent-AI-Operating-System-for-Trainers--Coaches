"use client";

import { useState } from "react";
import { Lock, Pencil, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { useLockProfile } from "@/features/trainer/api/use-trainer-profile";
import type { TrainerProfile } from "@/features/trainer/types";

interface ProfileViewProps {
  profile: TrainerProfile;
  onEdit: () => void;
  onReextract: () => void;
}

function formatINR(n: number): string {
  return `₹${n.toLocaleString("en-IN")}`;
}

function PricingLabel({ min, max }: { min: number | null; max: number | null }) {
  if (min === null && max === null) return <span className="text-muted-foreground">—</span>;
  if (min !== null && max !== null) return <span>{formatINR(min)} – {formatINR(max)}</span>;
  if (min !== null) return <span>From {formatINR(min)}</span>;
  return <span>Up to {formatINR(max!)}</span>;
}

function ChipList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (items.length === 0)
    return <span className="text-sm text-muted-foreground">{emptyText}</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="secondary" className="text-xs font-normal">
          {item}
        </Badge>
      ))}
    </div>
  );
}

export function ProfileView({ profile, onEdit, onReextract }: ProfileViewProps) {
  const lockMutation = useLockProfile();
  const [confirmOpen, setConfirmOpen] = useState(false);

  function handleLockConfirm() {
    setConfirmOpen(false);
    lockMutation.mutate();
  }

  return (
    <div className="space-y-6">
      {/* Top metadata row */}
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border p-4">
        <div className="space-y-0.5">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Niche
          </p>
          <p className="text-lg font-semibold">
            {profile.niche ?? <span className="text-muted-foreground">Not set</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {profile.is_locked ? (
            <Badge variant="warning" className="gap-1">
              <Lock className="h-3 w-3" />
              Locked
            </Badge>
          ) : (
            <>
              <Button size="sm" variant="outline" onClick={onEdit}>
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Button>
              <Button size="sm" variant="outline" onClick={onReextract}>
                <RefreshCw className="h-3.5 w-3.5" />
                Re-extract
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={lockMutation.isPending}
                onClick={() => setConfirmOpen(true)}
              >
                <Lock className="h-3.5 w-3.5" />
                {lockMutation.isPending ? "Locking…" : "Lock"}
              </Button>
            </>
          )}
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Lock this profile?</DialogTitle>
            <DialogDescription>
              Once locked, the profile cannot be edited or re-extracted. This
              action is permanent.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleLockConfirm}
              disabled={lockMutation.isPending}
            >
              {lockMutation.isPending ? "Locking…" : "Lock profile"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Core fields */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border p-4 space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Tone</p>
          <p className="text-sm">
            {profile.tone ?? <span className="text-muted-foreground">Not set</span>}
          </p>
        </div>
        <div className="rounded-lg border p-4 space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Pricing range</p>
          <p className="text-sm">
            <PricingLabel min={profile.pricing_min_inr} max={profile.pricing_max_inr} />
          </p>
        </div>
      </div>

      {/* USP */}
      {profile.usp && (
        <div className="rounded-lg border p-4 space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">USP</p>
          <p className="text-sm leading-relaxed">{profile.usp}</p>
        </div>
      )}

      {/* Bio */}
      {profile.bio && (
        <div className="rounded-lg border p-4 space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Bio</p>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{profile.bio}</p>
        </div>
      )}

      {/* Lists */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border p-4 space-y-2">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Topics</p>
          <ChipList items={profile.topics} emptyText="No topics" />
        </div>
        <div className="rounded-lg border p-4 space-y-2">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Target industries
          </p>
          <ChipList items={profile.target_industries} emptyText="None specified" />
        </div>
        <div className="rounded-lg border p-4 space-y-2">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Languages</p>
          <ChipList items={profile.languages} emptyText="None specified" />
        </div>
      </div>
    </div>
  );
}
