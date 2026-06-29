import { BusinessHealthDashboard } from "@/features/dashboard/ui/business-health-dashboard";

export const metadata = { title: "Health Center — CorporateMind AI" };

export default function HealthPage() {
  return (
    <div className="max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Business Health Center</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Real-time view of your business health across pipeline, revenue,
          campaigns, recommendations, and communications.
        </p>
      </div>

      <BusinessHealthDashboard />
    </div>
  );
}
