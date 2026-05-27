"use client";

import { Badge } from "@/components/ui/badge";
import { PROPOSAL_STATUS_CONFIG } from "@/features/proposals/types";

export function ProposalStatusBadge({ status }: { status: string }) {
  const cfg = PROPOSAL_STATUS_CONFIG[status] ?? { label: status, variant: "secondary" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
