import type { Metadata } from "next";
import { WorkflowEffectivenessCenter } from "@/features/workflows/ui/workflow-effectiveness-center";

export const metadata: Metadata = { title: "Workflow Effectiveness — CorporateMind AI" };

export default function WorkflowEffectivenessRoute() {
  const workspaceId = "default";
  return <WorkflowEffectivenessCenter workspaceId={workspaceId} />;
}
