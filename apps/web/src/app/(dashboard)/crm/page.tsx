import { PipelineBoard } from "@/features/crm/ui/pipeline-board";

export default function CRMPage() {
  return (
    <div className="flex flex-col gap-1 p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">CRM Pipeline</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Advance leads through each stage toward a booked engagement.
        </p>
      </div>
      <PipelineBoard />
    </div>
  );
}
