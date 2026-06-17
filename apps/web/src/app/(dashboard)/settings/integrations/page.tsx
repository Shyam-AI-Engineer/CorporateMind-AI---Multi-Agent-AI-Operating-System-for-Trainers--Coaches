import { IntegrationsPanel } from "@/features/workspace/ui/integrations-panel";

export const metadata = { title: "Integrations — CorporateMind AI" };

export default function IntegrationsPage() {
  return (
    <div className="max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Integrations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect external tools to automate your CRM pipeline.
        </p>
      </div>

      <div className="rounded-lg border p-6">
        <IntegrationsPanel />
      </div>
    </div>
  );
}
