import type { Metadata } from "next";
import { WorkflowObservabilityCenter } from "@/features/workflows/ui/workflow-observability-center";

export const metadata: Metadata = { title: "Workflow Observability — CorporateMind AI" };

export default function WorkflowObservabilityRoute() {
  const workspaceId = "default";
  return <WorkflowObservabilityCenter workspaceId={workspaceId} />;
}
