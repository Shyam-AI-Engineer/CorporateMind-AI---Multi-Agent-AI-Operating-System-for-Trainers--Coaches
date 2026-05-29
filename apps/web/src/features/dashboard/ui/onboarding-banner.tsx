"use client";

import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useTrainerProfile } from "@/features/trainer/api/use-trainer-profile";
import { useContacts } from "@/features/hr/api/use-contacts";
import { useCampaigns } from "@/features/campaigns/api/use-campaigns";
import { useWorkspace } from "@/hooks/use-workspace";

const STEPS = [
  {
    href: "/trainer" as Route,
    label: "Extract your trainer profile",
    cta: "Set up profile",
  },
  {
    href: "/hr" as Route,
    label: "Import your first HR contacts",
    cta: "Import contacts",
  },
  {
    href: "/campaigns" as Route,
    label: "Launch your first campaign",
    cta: "Create campaign",
  },
] as const;

export function OnboardingBanner() {
  const { workspaceId } = useWorkspace();
  const { data: profile, isLoading: profileLoading } = useTrainerProfile();
  const { data: contactsData, isLoading: contactsLoading } = useContacts();
  const { data: campaignsData, isLoading: campaignsLoading } = useCampaigns(
    workspaceId,
    { limit: 1 }
  );

  if (profileLoading || contactsLoading || campaignsLoading) return null;

  const done = [
    !!profile,
    (contactsData?.items.length ?? 0) > 0,
    (campaignsData?.items.length ?? 0) > 0,
  ];

  // All steps complete — hide banner entirely
  if (done.every(Boolean)) return null;

  const completedCount = done.filter(Boolean).length;
  const nextIndex = done.findIndex((d) => !d);

  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold">
              Getting started — {completedCount} of {STEPS.length} done
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Complete these steps to start sending AI-powered outreach.
            </p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {Math.round((completedCount / STEPS.length) * 100)}%
          </span>
        </div>

        <div className="mt-4 space-y-2.5">
          {STEPS.map(({ href, label, cta }, i) => (
            <div key={href} className="flex items-center gap-3">
              {done[i] ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
              ) : (
                <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span
                className={`flex-1 text-sm ${
                  done[i] ? "text-muted-foreground line-through" : ""
                }`}
              >
                {label}
              </span>
              {!done[i] && i === nextIndex && (
                <Link
                  href={href}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium",
                    "bg-primary text-primary-foreground transition-colors hover:bg-primary/90"
                  )}
                >
                  {cta}
                  <ArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
