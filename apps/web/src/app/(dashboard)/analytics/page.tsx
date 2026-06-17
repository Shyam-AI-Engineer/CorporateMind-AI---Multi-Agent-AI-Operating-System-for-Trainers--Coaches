import { AnalyticsPanel } from "@/features/analytics/ui/analytics-panel";

export const metadata = { title: "Analytics — CorporateMind AI" };

export default function AnalyticsPage() {
  return (
    <div className="max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          30-day outreach performance, pipeline trends, and revenue funnel.
          Updated nightly.
        </p>
      </div>

      <AnalyticsPanel />
    </div>
  );
}
