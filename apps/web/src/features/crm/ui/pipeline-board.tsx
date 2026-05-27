"use client";

import { useState } from "react";
import { Plus, RefreshCw, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PipelineColumn } from "@/features/crm/ui/pipeline-column";
import { CreateLeadDialog } from "@/features/crm/ui/create-lead-dialog";
import {
  usePipelineLeads,
  useAdvanceStage,
  useMarkLost,
} from "@/features/crm/api/use-leads";
import { useWorkspace } from "@/hooks/use-workspace";
import { PIPELINE_STAGES } from "@/features/crm/types";

export function PipelineBoard() {
  const { workspaceId } = useWorkspace();
  const [createOpen, setCreateOpen] = useState(false);

  const { leadsByStage, isLoading, isError, refetch } = usePipelineLeads(workspaceId);
  const advanceMutation = useAdvanceStage(workspaceId);
  const lostMutation = useMarkLost(workspaceId);

  const isActing = advanceMutation.isPending || lostMutation.isPending;

  if (!workspaceId) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">No workspace — please sign in again.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex gap-4 overflow-x-auto pb-4">
        {PIPELINE_STAGES.map((stage) => (
          <div key={stage} className="w-56 shrink-0 space-y-2 rounded-lg border bg-muted/30 p-3">
            <Skeleton className="h-6 w-24" />
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <AlertCircle className="h-8 w-8 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">Failed to load pipeline.</p>
        <Button variant="secondary" size="sm" onClick={() => void refetch()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Board header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">
            {Object.values(leadsByStage).flat().length} total leads ·{" "}
            {isActing ? "Updating…" : "Live"}
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          New Lead
        </Button>
      </div>

      {/* Kanban columns — horizontally scrollable */}
      <div className="flex gap-3 overflow-x-auto pb-3">
        {PIPELINE_STAGES.map((stage) => (
          <PipelineColumn
            key={stage}
            stage={stage}
            leads={leadsByStage[stage] ?? []}
            onAdvance={(leadId) => advanceMutation.mutate({ leadId })}
            onMarkLost={(leadId) => lostMutation.mutate({ leadId })}
            isAdvancing={isActing}
          />
        ))}
      </div>

      <CreateLeadDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        workspaceId={workspaceId}
      />
    </div>
  );
}
