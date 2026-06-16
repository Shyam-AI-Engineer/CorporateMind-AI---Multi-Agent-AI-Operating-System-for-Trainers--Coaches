"use client";

import { Badge } from "@/components/ui/badge";
import {
  APPROVAL_STATUS_CONFIG,
  DELIVERY_STATUS_CONFIG,
  PROPOSAL_STATUS_CONFIG,
} from "@/features/proposals/types";

export function ProposalStatusBadge({ status }: { status: string }) {
  const cfg = PROPOSAL_STATUS_CONFIG[status] ?? {
    label: status,
    variant: "secondary" as const,
  };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

export function ApprovalStatusBadge({ status }: { status: string }) {
  const cfg = APPROVAL_STATUS_CONFIG[status] ?? {
    label: status,
    variant: "outline" as const,
  };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

export function DeliveryStatusBadge({
  status,
}: {
  status: string | null | undefined;
}) {
  if (!status) return null;
  const cfg = DELIVERY_STATUS_CONFIG[status] ?? {
    label: status,
    variant: "outline" as const,
  };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
