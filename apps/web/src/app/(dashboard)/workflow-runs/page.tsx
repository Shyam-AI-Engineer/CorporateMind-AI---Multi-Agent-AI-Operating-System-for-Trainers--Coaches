import type { Metadata } from "next";
import { WorkflowExecutionCenter } from "@/features/workflows/ui/workflow-execution-center";

export const metadata: Metadata = { title: "Workflow Runs — CorporateMind AI" };

export default function WorkflowRunsRoute() {
  const workspaceId = "default";
  return <WorkflowExecutionCenter workspaceId={workspaceId} />;
}
