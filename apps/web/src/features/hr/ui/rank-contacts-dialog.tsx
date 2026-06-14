"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
import { useAddRecipients } from "@/features/campaigns/api/use-campaigns";
import { useTrainerProfile } from "@/features/trainer/api/use-trainer-profile";
import { useWorkspace } from "@/hooks/use-workspace";
import { RankResultsPanel } from "@/features/hr/ui/rank-results-panel";
import { CampaignPicker } from "@/features/campaigns/ui/campaign-picker";
import type { HRContact } from "@/features/hr/types";

type Step = "rank" | "select";

interface RankContactsDialogProps {
  contacts: HRContact[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RankContactsDialog({
  contacts,
  open,
  onOpenChange,
}: RankContactsDialogProps) {
  const router = useRouter();
  const { workspaceId } = useWorkspace();

  // ── Step state ───────────────────────────────────────────────────────────
  const [step, setStep] = useState<Step>("rank");

  // ── Step 1: Rank form fields ─────────────────────────────────────────────
  const [niche, setNiche] = useState("");
  const [topicsRaw, setTopicsRaw] = useState("");
  const [industriesRaw, setIndustriesRaw] = useState("");
  const [edited, setEdited] = useState(false);

  // ── Step 2: Selection state ──────────────────────────────────────────────
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  // ── Hooks ────────────────────────────────────────────────────────────────
  const { data: profile, isLoading: profileLoading } = useTrainerProfile();

  const {
    mutate: rank,
    isPending: ranking,
    data: rankData,
    error: rankError,
    reset: resetRank,
  } = useRankContacts();

  const { mutate: addRecipients, isPending: adding } =
    useAddRecipients(workspaceId);

  const hasProfile = !!profile;
  const prefilledFromProfile = hasProfile && !edited;

  // Pre-fill form from trainer profile whenever the dialog is opened.
  // Tracking profile?.id (not the full object) avoids clobbering user edits
  // on background refetches.
  useEffect(() => {
    if (open && profile) {
      setNiche(profile.niche ?? "");
      setTopicsRaw(profile.topics.join(", "));
      setIndustriesRaw(profile.target_industries.join(", "));
      setEdited(false);
    }
  }, [open, profile?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Helpers ──────────────────────────────────────────────────────────────

  function resetAll() {
    resetRank();
    setStep("rank");
    setSelectedContactIds([]);
    setSelectedCampaignId(null);
    setAddError(null);
  }

  function handleClose(isOpen: boolean) {
    if (!isOpen) resetAll();
    onOpenChange(isOpen);
  }

  // ── Step 1: Rank contacts ────────────────────────────────────────────────

  function handleRank(e: React.FormEvent) {
    e.preventDefault();
    const topics = topicsRaw.split(",").map((s) => s.trim()).filter(Boolean);
    const industries = industriesRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    rank(
      {
        contact_ids: contacts.map((c) => c.id),
        trainer_niche: niche,
        trainer_topics: topics,
        trainer_target_industries: industries,
      },
      { onSuccess: () => setStep("select") },
    );
  }

  // ── Step 2: Add to campaign ───────────────────────────────────────────────

  function handleBack() {
    resetAll();
  }

  function handleAddRecipients() {
    if (!selectedCampaignId || selectedContactIds.length === 0 || !workspaceId)
      return;
    setAddError(null);
    addRecipients(
      { campaignId: selectedCampaignId, contactIds: selectedContactIds },
      {
        onSuccess: () => {
          handleClose(false);
          router.push(`/campaigns/${selectedCampaignId}`);
        },
        onError: () => {
          setAddError("Failed to add recipients — please try again.");
        },
      },
    );
  }

  const addLabel = adding
    ? "Adding…"
    : selectedContactIds.length > 0
      ? `Add ${selectedContactIds.length} contact${selectedContactIds.length === 1 ? "" : "s"}`
      : "Add contacts";

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {step === "rank"
              ? "Rank Contacts by Fit"
              : "Select Contacts to Add"}
          </DialogTitle>
        </DialogHeader>

        {step === "rank" ? (
          /* ── Step 1: Ranking form ──────────────────────────────────────── */
          <form onSubmit={handleRank} className="space-y-4 py-1">
            <p className="text-xs text-muted-foreground">
              The AI will score your{" "}
              <Badge variant="secondary">{contacts.length}</Badge> contacts
              against your trainer profile.
            </p>

            {/* Profile source indicator */}
            {profileLoading ? (
              <div className="h-9 rounded-md border bg-muted/40 animate-pulse" />
            ) : prefilledFromProfile ? (
              <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
                <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
                <span className="text-foreground">
                  Pre-filled from your{" "}
                  <Link
                    href="/trainer"
                    className="font-medium underline-offset-2 hover:underline"
                  >
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
                  <Link
                    href="/trainer"
                    className="font-medium text-primary underline-offset-2 hover:underline"
                  >
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
              <Label htmlFor="industries">
                Target industries (comma-separated)
              </Label>
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

            {rankError && (
              <p className="text-xs text-destructive">
                Ranking failed — please try again.
              </p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleClose(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={ranking || !niche || contacts.length === 0}
              >
                {ranking ? "Ranking…" : "Rank contacts"}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          /* ── Step 2: Select + assign to campaign ───────────────────────── */
          <div className="space-y-4 py-1">
            <RankResultsPanel
              rankings={rankData?.rankings ?? []}
              onSelectionChange={setSelectedContactIds}
            />

            {workspaceId && (
              <CampaignPicker
                workspaceId={workspaceId}
                value={selectedCampaignId}
                onChange={setSelectedCampaignId}
              />
            )}

            {addError && (
              <p className="text-xs text-destructive">{addError}</p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={handleBack}
                disabled={adding}
              >
                ← Back
              </Button>
              <Button
                type="button"
                onClick={handleAddRecipients}
                disabled={
                  adding ||
                  selectedContactIds.length === 0 ||
                  !selectedCampaignId
                }
              >
                {addLabel}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
