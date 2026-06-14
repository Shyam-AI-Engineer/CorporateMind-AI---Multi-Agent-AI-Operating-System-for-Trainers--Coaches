"use client";

import { useRouter } from "next/navigation";
import { useCampaigns } from "@/features/campaigns/api/use-campaigns";

export interface CampaignPickerProps {
  workspaceId: string;
  value: string | null;
  onChange: (campaignId: string) => void;
}

export function CampaignPicker({
  workspaceId,
  value,
  onChange,
}: CampaignPickerProps) {
  const router = useRouter();
  const { data, isLoading } = useCampaigns(workspaceId, { limit: 50 });

  // Client-side filter: only show campaigns that can still receive recipients.
  const drafts = (data?.items ?? []).filter((c) => c.status === "draft");

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (e.target.value === "__create__") {
      router.push("/campaigns?create=1");
      return;
    }
    onChange(e.target.value);
  }

  return (
    <div className="space-y-1.5">
      <label
        htmlFor="campaign-picker"
        className="text-xs font-medium text-muted-foreground"
      >
        Add to campaign
      </label>
      <select
        id="campaign-picker"
        value={value ?? ""}
        onChange={handleChange}
        disabled={isLoading}
        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      >
        <option value="" disabled>
          {isLoading ? "Loading campaigns…" : "— Select a draft campaign —"}
        </option>
        {drafts.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
        {!isLoading && drafts.length === 0 && (
          <option value="" disabled>
            No draft campaigns — create one first
          </option>
        )}
        <option value="__create__">＋ Create new campaign</option>
      </select>
    </div>
  );
}
