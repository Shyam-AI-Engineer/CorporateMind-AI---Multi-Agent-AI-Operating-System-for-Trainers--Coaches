"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { Button } from "@/components/ui/button";
import { ProposalList } from "@/features/proposals/ui/proposal-list";
import { GenerateProposalDialog } from "@/features/proposals/ui/generate-proposal-dialog";
import { useWorkspace } from "@/hooks/use-workspace";

export default function ProposalsPage() {
  const { workspaceId } = useWorkspace();
  const router = useRouter();
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
          <h1 className="text-xl font-semibold">Proposals</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            AI-drafted proposals generated from CRM leads.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>Generate proposal</Button>
      </div>

      <ProposalList
        workspaceId={workspaceId}
        onGenerate={() => setDialogOpen(true)}
      />

      <GenerateProposalDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSuccess={(id) => router.push(`/proposals/${id}` as Route)}
      />
    </div>
  );
}
