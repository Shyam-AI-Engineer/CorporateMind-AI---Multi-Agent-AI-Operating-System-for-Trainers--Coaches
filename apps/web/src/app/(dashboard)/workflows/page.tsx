import type { Metadata } from "next";
import { WorkflowTemplateCenter } from "@/features/workflows/ui/workflow-template-center";

export const metadata: Metadata = { title: "Workflow Templates — CorporateMind AI" };

export default function WorkflowsRoute() {
  return (
    <div className="max-w-3xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Workflow Templates & Playbooks</h1>
      <WorkflowTemplateCenter />
    </div>
  );
}
