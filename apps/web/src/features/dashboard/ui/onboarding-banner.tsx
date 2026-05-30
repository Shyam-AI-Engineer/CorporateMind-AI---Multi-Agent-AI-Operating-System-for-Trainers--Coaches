"use client";

import Link from "next/link";
import type { Route } from "next";
import { AlertCircle, ArrowRight, CheckCircle2, Circle, RefreshCw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
  const {
    data: profile,
    isLoading: profileLoading,
    isError: profileError,
    refetch: refetchProfile,
  } = useTrainerProfile();
  const {
    data: contactsData,
    isLoading: contactsLoading,
    isError: contactsError,
    refetch: refetchContacts,
  } = useContacts();
  const {
    data: campaignsData,
    isLoading: campaignsLoading,
    isError: campaignsError,
    refetch: refetchCampaigns,
  } = useCampaigns(workspaceId, { limit: 1 });

  const isLoading = profileLoading || contactsLoading || campaignsLoading;
  const isError = profileError || contactsError || campaignsError;

  if (isLoading) {
    return (
      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="p-4 space-y-3">
          <div className="h-4 w-48 rounded bg-primary/10 animate-pulse" />
          <div className="h-3 w-64 rounded bg-primary/10 animate-pulse" />
          <div className="mt-2 space-y-2.5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-5 w-full rounded bg-primary/10 animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    const retry = () => {
      if (profileError) void refetchProfile();
      if (contactsError) void refetchContacts();
      if (campaignsError) void refetchCampaigns();
    };
    return (
      <Card className="border-destructive/20 bg-destructive/5">
        <CardContent className="flex items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
            <p className="text-sm text-destructive">
              Could not load onboarding progress.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={retry}
            className="shrink-0 gap-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

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
