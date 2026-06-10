"use client";

/**
 * MessagesPanel — paginated inbox message list with intent filter.
 *
 * Filter bar: chip group for All + the 7 canonical reply intents.
 * Table rows: sender, subject, body preview, received time, IntentBadge.
 * Pagination: Prev / Next with "X–Y of Z" counter.
 *
 * States: skeleton rows (loading), empty illustration, error + retry.
 * Follows the same shell pattern as ConnectionsPanel.
 */

import { useState } from "react";
import { formatDistanceToNow, parseISO } from "date-fns";
import { AlertCircle, Inbox, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInboxMessages } from "@/features/inbox/api/use-inbox";
import { IntentBadge } from "@/features/inbox/ui/intent-badge";
import {
  INTENT_CONFIG,
  REPLY_INTENTS,
  type InboxMessage,
  type ReplyIntent,
} from "@/features/inbox/types";
import { useWorkspace } from "@/hooks/use-workspace";

const PAGE_SIZE = 20;

export function MessagesPanel() {
  const { workspaceId } = useWorkspace();
  const [intent, setIntent] = useState<ReplyIntent | undefined>(undefined);
  const [offset, setOffset] = useState(0);

  const { data, isLoading, isError, refetch } = useInboxMessages(workspaceId, {
    intent,
    limit: PAGE_SIZE,
    offset,
  });

  // Reset to first page when filter changes
  function handleIntentChange(next: ReplyIntent | undefined) {
    setIntent(next);
    setOffset(0);
  }

  if (!workspaceId) {
    return (
      <p className="text-sm text-muted-foreground">
        No workspace — please sign in again.
      </p>
    );
  }

  const messages = data?.items ?? [];
  const total = data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="flex flex-col gap-4">
      {/* Intent filter chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        <IntentChip
          label="All"
          active={intent === undefined}
          onClick={() => handleIntentChange(undefined)}
        />
        {REPLY_INTENTS.map((ri) => (
          <IntentChip
            key={ri}
            label={INTENT_CONFIG[ri].label}
            active={intent === ri}
            onClick={() => handleIntentChange(ri)}
          />
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingRows />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : messages.length === 0 ? (
        <EmptyState filtered={intent !== undefined} />
      ) : (
        <>
          <MessageTable messages={messages} />
          <Pagination
            from={from}
            to={to}
            total={total}
            onPrev={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            onNext={() => setOffset((o) => o + PAGE_SIZE)}
            hasPrev={offset > 0}
            hasNext={to < total}
          />
        </>
      )}
    </div>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function IntentChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded-full px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function MessageTable({ messages }: { messages: InboxMessage[] }) {
  return (
    <div className="rounded-lg border overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-[1fr_1.5fr_1fr_auto_auto] gap-3 border-b bg-muted/50 px-4 py-2 text-xs font-medium text-muted-foreground">
        <span>From</span>
        <span>Subject</span>
        <span>Preview</span>
        <span>Intent</span>
        <span>Received</span>
      </div>
      {/* Rows */}
      {messages.map((msg) => (
        <MessageRow key={msg.id} message={msg} />
      ))}
    </div>
  );
}

function MessageRow({ message }: { message: InboxMessage }) {
  const receivedAgo = formatDistanceToNow(parseISO(message.received_at), {
    addSuffix: true,
  });

  // Show just the name part of the email if it includes one
  const fromDisplay = message.from_address.includes("<")
    ? message.from_address.split("<")[0].trim()
    : message.from_address;

  return (
    <div className="grid grid-cols-[1fr_1.5fr_1fr_auto_auto] gap-3 items-center border-b last:border-b-0 px-4 py-3 text-sm hover:bg-muted/30 transition-colors">
      <span
        className="truncate font-medium text-foreground"
        title={message.from_address}
      >
        {fromDisplay || message.from_address}
      </span>

      <span
        className="truncate text-foreground"
        title={message.subject ?? undefined}
      >
        {message.subject ?? <span className="text-muted-foreground italic">(no subject)</span>}
      </span>

      <span
        className="truncate text-muted-foreground text-xs"
        title={message.body_snippet ?? undefined}
      >
        {message.body_snippet ?? "—"}
      </span>

      <IntentBadge
        intent={message.reply_intent}
        confidence={message.confidence}
        showConfidence
      />

      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {receivedAgo}
      </span>
    </div>
  );
}

function Pagination({
  from,
  to,
  total,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: {
  from: number;
  to: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">
        {from}–{to} of {total}
      </span>
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={onPrev}
          disabled={!hasPrev}
        >
          Prev
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={onNext}
          disabled={!hasNext}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="rounded-lg border overflow-hidden">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-[1fr_1.5fr_1fr_auto_auto] gap-3 items-center border-b last:border-b-0 px-4 py-3"
        >
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-card">
      <Inbox className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">
        {filtered ? "No messages match this filter." : "No messages synced yet."}
      </p>
      {!filtered && (
        <p className="text-xs text-muted-foreground/70">
          Connect a Gmail inbox and messages will appear here after the next sync.
        </p>
      )}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-lg border bg-card">
      <AlertCircle className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">Failed to load messages.</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
        Retry
      </Button>
    </div>
  );
}
