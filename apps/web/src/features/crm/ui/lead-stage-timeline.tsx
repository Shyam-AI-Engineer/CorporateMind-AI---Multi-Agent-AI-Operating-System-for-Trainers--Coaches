"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { PIPELINE_STAGES, STAGE_CONFIG, type PipelineStage } from "@/features/crm/types";

// The five forward stages in order; "lost" is a side-exit shown separately.
const TIMELINE_STAGES = PIPELINE_STAGES.filter(
  (s): s is PipelineStage => s !== "lost",
);

interface LeadStageTimelineProps {
  currentStage: string;
}

export function LeadStageTimeline({ currentStage }: LeadStageTimelineProps) {
  const isLost = currentStage === "lost";
  const currentIdx = TIMELINE_STAGES.indexOf(currentStage as PipelineStage);

  return (
    <div className="flex flex-wrap items-start gap-y-3">
      {TIMELINE_STAGES.map((stage, idx) => {
        const config = STAGE_CONFIG[stage];
        const isDone = !isLost && currentIdx > idx;
        const isCurrent = !isLost && currentIdx === idx;

        return (
          <div key={stage} className="flex items-start">
            {/* Step bubble + label */}
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors",
                  isDone &&
                    "border-green-500 bg-green-500 text-white",
                  isCurrent &&
                    `${config.borderClass} ${config.bgClass} ${config.colorClass}`,
                  !isDone &&
                    !isCurrent &&
                    "border-muted-foreground/25 bg-background text-muted-foreground/40",
                )}
              >
                {isDone ? <Check className="h-3.5 w-3.5" /> : idx + 1}
              </div>
              <span
                className={cn(
                  "whitespace-nowrap text-[10px] font-medium leading-none",
                  isDone && "text-green-600",
                  isCurrent && config.colorClass,
                  !isDone && !isCurrent && "text-muted-foreground/40",
                )}
              >
                {config.label}
              </span>
            </div>

            {/* Connector line between steps */}
            {idx < TIMELINE_STAGES.length - 1 && (
              <div
                className={cn(
                  "mb-4 h-0.5 w-8 shrink-0 self-start mt-3.5",
                  isDone ? "bg-green-400" : "bg-muted-foreground/20",
                )}
              />
            )}
          </div>
        );
      })}

      {/* Lost indicator — side-exit, shown after the forward chain */}
      {isLost && (
        <div className="ml-3 flex items-center self-start mt-1.5 gap-1.5 rounded-md bg-red-50 px-2.5 py-1.5 border border-red-200">
          <div className="h-2 w-2 rounded-full bg-red-500" />
          <span className="text-xs font-medium text-red-600">Lost</span>
        </div>
      )}
    </div>
  );
}
