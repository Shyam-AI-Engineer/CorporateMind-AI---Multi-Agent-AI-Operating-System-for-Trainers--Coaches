import type { Metadata } from "next";
import { WorkflowSLACenter } from "@/features/workflows/ui/workflow-sla-center";

export const metadata: Metadata = { title: "Workflow SLA — CorporateMind AI" };

export default function WorkflowSLARoute() {
  const workspaceId = "default";
  return <WorkflowSLACenter workspaceId={workspaceId} />;
}
