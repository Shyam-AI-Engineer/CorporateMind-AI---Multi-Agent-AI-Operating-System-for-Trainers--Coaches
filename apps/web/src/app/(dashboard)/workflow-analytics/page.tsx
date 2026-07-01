import type { Metadata } from "next";
import { WorkflowAnalyticsCenter } from "@/features/workflows/ui/workflow-analytics-center";

export const metadata: Metadata = { title: "Workflow Analytics — CorporateMind AI" };

export default function WorkflowAnalyticsRoute() {
  const workspaceId = "default";
  return <WorkflowAnalyticsCenter workspaceId={workspaceId} />;
}
