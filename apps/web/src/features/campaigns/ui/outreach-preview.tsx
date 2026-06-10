"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useCampaignMessages } from "@/features/outreach/api/use-outreach";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MESSAGE_STATUS_CONFIG } from "@/features/outreach/types";
import type { OutboundMessage } from "@/features/outreach/types";

const LIMIT = 10;

// ── Expandable message row ────────────────────────────────────────────────────

function MessageRow({ msg }: { msg: OutboundMessage }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = MESSAGE_STATUS_CONFIG[msg.status] ?? { label: msg.status, variant: "secondary" as const };

  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={cfg.variant}>{cfg.label}</Badge>
            {msg.subject && (
              <span className="truncate text-sm font-medium">{msg.subject}</span>
            )}
            <span className="text-xs text-muted-foreground font-mono">
              {msg.contact_id.slice(0, 8)}…
            </span>
          </div>
          {msg.sent_at && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Sent {new Date(msg.sent_at).toLocaleString()}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
          aria-label={expanded ? "Collapse message" : "Expand message"}
        >
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 rounded-md border bg-muted/30 p-3 max-h-48 overflow-y-auto">
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.body}</p>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface OutreachPreviewProps {
  campaignId: string;
}

export function OutreachPreview({ campaignId }: OutreachPreviewProps) {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, isError, refetch } = useCampaignMessages(campaignId, LIMIT, offset);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-sm text-muted-foreground">Failed to load messages.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!data?.items.length) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No outreach generated yet. Use the Outreach page to generate personalised copy for
        contacts in this campaign.
      </p>
    );
  }

  const { items, total } = data;
  const from = offset + 1;
  const to = Math.min(offset + LIMIT, total);

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {from}–{to} of {total} messages
      </p>

      <div className="divide-y rounded-lg border">
        {items.map((msg) => (
          <MessageRow key={msg.id} msg={msg} />
        ))}
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={to >= total}
          onClick={() => setOffset((o) => o + LIMIT)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
