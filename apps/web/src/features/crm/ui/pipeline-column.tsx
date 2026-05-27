"use client";

import { cn } from "@/lib/utils";
import { LeadCard } from "@/features/crm/ui/lead-card";
import type { Lead } from "@/features/crm/types";
import { STAGE_CONFIG } from "@/features/crm/types";

interface PipelineColumnProps {
  stage: string;
  leads: Lead[];
  onAdvance: (leadId: string) => void;
  onMarkLost: (leadId: string) => void;
  isAdvancing: boolean;
}

export function PipelineColumn({
  stage,
  leads,
  onAdvance,
  onMarkLost,
  isAdvancing,
}: PipelineColumnProps) {
  const config = STAGE_CONFIG[stage] ?? {
    label: stage,
    colorClass: "text-foreground",
    bgClass: "bg-muted",
    borderClass: "border-border",
  };

  return (
    <div className="flex w-56 shrink-0 flex-col rounded-lg border bg-muted/30">
      {/* Column header */}
      <div
        className={cn(
          "flex items-center justify-between rounded-t-lg border-b px-3 py-2.5",
          config.bgClass,
          config.borderClass
        )}
      >
        <span className={cn("text-xs font-semibold uppercase tracking-wide", config.colorClass)}>
          {config.label}
        </span>
        <span
          className={cn(
            "flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-medium",
            config.bgClass,
            config.colorClass,
            "border",
            config.borderClass
          )}
        >
          {leads.length}
        </span>
      </div>

      {/* Lead cards */}
      <div className="flex-1 overflow-y-auto p-2">
        {leads.length === 0 ? (
          <p className="mt-4 text-center text-xs text-muted-foreground/50">
            No leads
          </p>
        ) : (
          leads.map((lead) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              onAdvance={onAdvance}
              onMarkLost={onMarkLost}
              isAdvancing={isAdvancing}
            />
          ))
        )}
      </div>
    </div>
  );
}
