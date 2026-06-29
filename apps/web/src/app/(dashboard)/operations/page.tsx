import { OperationsCenter } from "@/features/operations/ui/operations-center";

export const metadata = { title: "Operations — CorporateMind AI" };

export default function OperationsPage() {
  return (
    <div className="max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Business Operations Center</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage, prioritize, and track your operational workload across all business areas.
        </p>
      </div>

      <OperationsCenter />
    </div>
  );
}
