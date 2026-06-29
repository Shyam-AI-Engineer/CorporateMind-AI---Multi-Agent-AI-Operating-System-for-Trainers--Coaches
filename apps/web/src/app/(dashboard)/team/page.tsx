import { TeamPage } from "@/features/team/ui/team-page";

export const metadata = { title: "Team — CorporateMind AI" };

export default function TeamRoute() {
  return (
    <div className="max-w-5xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Team Collaboration</h1>
      <TeamPage />
    </div>
  );
}
