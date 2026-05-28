"use client";

import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyProfileProps {
  onExtract: () => void;
}

export function EmptyProfile({ onExtract }: EmptyProfileProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed py-20 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
        <Sparkles className="h-6 w-6 text-primary" />
      </div>
      <div className="max-w-md space-y-1">
        <h2 className="text-base font-semibold">Set up your trainer profile</h2>
        <p className="text-sm text-muted-foreground">
          Paste your bio, LinkedIn About section, or brochure text. The AI will
          extract your niche, topics, USP, pricing range, and target industries
          to personalize every outreach message.
        </p>
      </div>
      <Button onClick={onExtract}>Extract from text</Button>
    </div>
  );
}
