"use client";

import Link from "next/link";
import type { Route } from "next";
import { ChevronRight, MoreHorizontal, Calendar, XCircle } from "lucide-react";
import { format } from "date-fns";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Lead } from "@/features/crm/types";
import { TERMINAL_STAGES } from "@/features/crm/types";

interface LeadCardProps {
  lead: Lead;
  onAdvance: (leadId: string) => void;
  onMarkLost: (leadId: string) => void;
  isAdvancing: boolean;
}

function ScoreBadge({ score }: { score: number }) {
  const variant =
    score >= 70 ? "success" : score >= 40 ? "warning" : "destructive";
  return (
    <Badge variant={variant} className="text-xs">
      {score}
    </Badge>
  );
}

export function LeadCard({ lead, onAdvance, onMarkLost, isAdvancing }: LeadCardProps) {
  const isTerminal = TERMINAL_STAGES.has(lead.stage);
  const shortContactId = lead.contact_id.slice(0, 8) + "…";

  return (
    <Link href={`/crm/leads/${lead.id}` as Route}>
      <Card className="mb-2 shadow-none hover:shadow-sm transition-shadow cursor-pointer">
        <CardContent className="p-3">
          {/* Header row */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-mono text-muted-foreground">
                {shortContactId}
              </p>
              <ScoreBadge score={lead.score} />
            </div>
            {!isTerminal && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0 text-muted-foreground"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>Actions</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={(e) => { e.stopPropagation(); onMarkLost(lead.id); }}
                  >
                    <XCircle className="mr-2 h-3.5 w-3.5" />
                    Mark as Lost
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>

          {/* Notes preview */}
          {lead.notes && (
            <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground">
              {lead.notes}
            </p>
          )}

          {/* Meeting / booked timestamp */}
          {lead.meeting_scheduled_at && (
            <div className="mt-1.5 flex items-center gap-1 text-xs text-violet-600">
              <Calendar className="h-3 w-3" />
              {format(new Date(lead.meeting_scheduled_at), "MMM d, h:mm a")}
            </div>
          )}
          {lead.booked_at && (
            <div className="mt-1.5 flex items-center gap-1 text-xs text-green-600">
              <Calendar className="h-3 w-3" />
              Booked {format(new Date(lead.booked_at), "MMM d")}
            </div>
          )}

          {/* Advance button */}
          {!isTerminal && (
            <Button
              size="sm"
              variant="secondary"
              className="mt-2 h-6 w-full gap-1 text-xs"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAdvance(lead.id); }}
              disabled={isAdvancing}
            >
              Advance
              <ChevronRight className="h-3 w-3" />
            </Button>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
