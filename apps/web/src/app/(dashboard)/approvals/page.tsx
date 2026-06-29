import { ApprovalInbox } from "@/features/approvals/ui/approval-inbox";

export const metadata = { title: "Approvals — CorporateMind AI" };

export default function ApprovalsRoute() {
  return (
    <div className="max-w-5xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Approval Workflow</h1>
      <ApprovalInbox />
    </div>
  );
}
