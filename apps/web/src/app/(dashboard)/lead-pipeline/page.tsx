import type { Metadata } from "next";
import { LeadPipelineAnalyticsCenter } from "@/features/crm/ui/lead-pipeline-analytics-center";

export const metadata: Metadata = {
  title: "Lead Pipeline Analytics — CorporateMind AI",
};

export default function LeadPipelineAnalyticsRoute() {
  const workspaceId = "default";
  return <LeadPipelineAnalyticsCenter workspaceId={workspaceId} />;
}
