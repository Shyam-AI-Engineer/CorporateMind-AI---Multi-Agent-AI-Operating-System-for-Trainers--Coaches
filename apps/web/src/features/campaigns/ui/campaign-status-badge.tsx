"use client";

import { Badge } from "@/components/ui/badge";
import { STATUS_CONFIG } from "@/features/campaigns/types";

interface CampaignStatusBadgeProps {
  status: string;
}

export function CampaignStatusBadge({ status }: CampaignStatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? { label: status, variant: "secondary" as const };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
