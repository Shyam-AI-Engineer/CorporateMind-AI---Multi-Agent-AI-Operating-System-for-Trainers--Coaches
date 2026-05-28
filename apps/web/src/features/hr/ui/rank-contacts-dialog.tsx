"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, UserCircle } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { useRankContacts } from "@/features/hr/api/use-contacts";
import { useTrainerProfile } from "@/features/trainer/api/use-trainer-profile";
import type { HRContact, RankedContact } from "@/features/hr/types";

interface RankContactsDialogProps {
  contacts: HRContact[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round((score / 10) * 100);
  const color =
    score >= 8 ? "bg-green-500" : score >= 5 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs font-medium">{score}/10</span>
    </div>
  );
}

function RankedRow({ ranked }: { ranked: RankedContact }) {
  return (
    <div className="rounded-lg border p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{ranked.contact.full_name}</p>
          <p className="text-xs text-muted-foreground">{ranked.contact.title}</p>
        </div>
        <ScoreBar score={ranked.score} />
      </div>
      <p className="text-xs text-muted-foreground">{ranked.reason}</p>
    </div>
  );
}

export function RankContactsDialog({
  contacts,
  open,
  onOpenChange,
}: RankContactsDialogProps) {
  const [niche, setNiche] = useState("");
  const [topicsRaw, setTopicsRaw] = useState("");
  const [industriesRaw, setIndustriesRaw] = useState("");
  const [edited, setEdited] = useState(false);

  const { data: profile, isLoading: profileLoading } = useTrainerProfile();
  const { mutate, isPending, data, error, reset } = useRankContacts();

  const hasResults = !!data?.rankings?.length;
  const hasProfile = !!profile;
  const prefilledFromProfile = hasProfile && !edited;

  // Prefill from trainer profile on open (or when profile identity changes).
  // Tracking `profile?.id` (not `profile`) avoids clobbering user edits on
  // background refetches.
  useEffect(() => {
    if (open && profile) {
      setNiche(profile.niche ?? "");
      setTopicsRaw(profile.topics.join(", "));
      setIndustriesRaw(profile.target_industries.join(", "));
      setEdited(false);
    }
  }, [open, profile?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleRank(e: React.FormEvent) {
    e.preventDefault();
    const topics = topicsRaw.split(",").map((s) => s.trim()).filter(Boolean);
    const industries = industriesRaw.split(",").map((s) => s.trim()).filter(Boolean);
    mutate({
      contact_ids: contacts.map((c) => c.id),
      trainer_niche: niche,
      trainer_topics: topics,
      trainer_target_industries: industries,
    });
  }

  function handleClose(open: boolean) {
    if (!open) reset();
    onOpenChange(open);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Rank Contacts by Fit</DialogTitle>
        </DialogHeader>

        {!hasResults ? (
          <form onSubmit={handleRank} className="space-y-4 py-1">
            <p className="text-xs text-muted-foreground">
              The AI will score your{" "}
              <Badge variant="secondary">{contacts.length}</Badge> contacts
              against your trainer profile.
            </p>

            {/* Profile source indicator / CTA */}
            {profileLoading ? (
              <div className="h-9 rounded-md border bg-muted/40 animate-pulse" />
            ) : prefilledFromProfile ? (
              <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
                <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
                <span className="text-foreground">
                  Pre-filled from your{" "}
                  <Link href="/trainer" className="font-medium underline-offset-2 hover:underline">
                    stored trainer profile
                  </Link>
                  . Edit any field to override for this run.
                </span>
              </div>
            ) : !hasProfile ? (
              <div className="flex items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs">
                <UserCircle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground">
                  No trainer profile yet.{" "}
                  <Link href="/trainer" className="font-medium text-primary underline-offset-2 hover:underline">
                    Set one up
                  </Link>{" "}
                  to skip these fields every time.
                </span>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="niche">Your niche</Label>
              <Input
                id="niche"
                placeholder="e.g. Leadership Development, Sales Training"
                value={niche}
                onChange={(e) => {
                  setNiche(e.target.value);
                  setEdited(true);
                }}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="topics">Topics (comma-separated)</Label>
              <Input
                id="topics"
                placeholder="e.g. Mindset, Team Building, Communication"
                value={topicsRaw}
                onChange={(e) => {
                  setTopicsRaw(e.target.value);
                  setEdited(true);
                }}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="industries">Target industries (comma-separated)</Label>
              <Input
                id="industries"
                placeholder="e.g. IT, Banking, Manufacturing"
                value={industriesRaw}
                onChange={(e) => {
                  setIndustriesRaw(e.target.value);
                  setEdited(true);
                }}
              />
            </div>

            {error && (
              <p className="text-xs text-destructive">
                Ranking failed — please try again.
              </p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isPending || !niche || contacts.length === 0}>
                {isPending ? "Ranking…" : "Rank contacts"}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-3 py-1">
            <p className="text-xs text-muted-foreground">
              Ranked {data.rankings.length} contacts — highest fit first.
            </p>
            <div className="space-y-2">
              {data.rankings.map((r) => (
                <RankedRow key={r.contact_id} ranked={r} />
              ))}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => reset()}>
                Rank again
              </Button>
              <Button onClick={() => handleClose(false)}>Done</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
