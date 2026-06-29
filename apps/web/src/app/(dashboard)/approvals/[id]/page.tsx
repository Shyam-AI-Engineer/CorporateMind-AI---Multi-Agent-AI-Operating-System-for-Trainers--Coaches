"use client";

import { useParams } from "next/navigation";
import { ApprovalDetailPage } from "@/features/approvals/ui/approval-detail-page";

export default function ApprovalDetailRoute() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="max-w-3xl space-y-6 p-6">
      <ApprovalDetailPage approvalId={id} />
    </div>
  );
}
