import { StatsHeader } from "@/features/dashboard/ui/stats-header";
import { PipelineFunnel } from "@/features/dashboard/ui/pipeline-funnel";
import { CampaignsSummary } from "@/features/dashboard/ui/campaigns-summary";
import { InsightsCard } from "@/features/dashboard/ui/insights-card";
import { OnboardingBanner } from "@/features/dashboard/ui/onboarding-banner";

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Your pipeline, campaigns, and AI insights at a glance.
        </p>
      </div>

      {/* Onboarding checklist — hidden once all steps are complete */}
      <OnboardingBanner />

      {/* Top stats row */}
      <StatsHeader />

      {/* Main content: funnel + campaigns side by side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <PipelineFunnel />
        <CampaignsSummary />
      </div>

      {/* AI Insights */}
      <InsightsCard />
    </div>
  );
}
