"use client";

/**
 * ConnectionsPanel — Inbox Connections page main component.
 *
 * Shows one row per connected Gmail account with status, health, last sync,
 * and lifecycle actions (refresh-health, disconnect, connect).  Uses Dialog
 * for the confirm-disconnect modal — keyboard + escape close come for free.
 *
 * Loading / empty / error states all use existing Skeleton + Button + Card.
 */

import { useState } from "react";
import { formatDistanceToNow, parseISO } from "date-fns";
import {
  AlertCircle,
  CheckCircle2,
  Mail,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCheckConnectionHealth,
  useDisconnectInbox,
  useInboxConnections,
} from "@/features/inbox/api/use-inbox";
import { CONNECTION_STATUS_CONFIG, type InboxConnection } from "@/features/inbox/types";
import { useWorkspace } from "@/hooks/use-workspace";

export function ConnectionsPanel() {
  const { workspaceId } = useWorkspace();
  const { data, isLoading, isError, refetch } = useInboxConnections(workspaceId);
  const disconnect = useDisconnectInbox(workspaceId);
  const checkHealth = useCheckConnectionHealth(workspaceId);

  const [confirmDisconnect, setConfirmDisconnect] =
    useState<InboxConnection | null>(null);

  if (!workspaceId) {
    return (
      <p className="text-sm text-muted-foreground">
        No workspace — please sign in again.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-lg border bg-card">
        <AlertCircle className="h-8 w-8 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          Failed to load inbox connections.
        </p>
        <Button variant="secondary" size="sm" onClick={() => void refetch()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Retry
        </Button>
      </div>
    );
  }

  const connections = data?.items ?? [];

  return (
    <>
      <div className="flex flex-col gap-3">
        {/* Header + Connect button */}
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {connections.length} connected
          </p>
          {/* /api/v1/inbox/connect issues a redirect to Google — full page navigation. */}
          <Button asChild size="sm">
            <a href="/api/v1/inbox/connect">
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Connect inbox
            </a>
          </Button>
        </div>

        {connections.length === 0 ? (
          <EmptyState />
        ) : (
          connections.map((conn) => (
            <ConnectionRow
              key={conn.id}
              connection={conn}
              onDisconnect={() => setConfirmDisconnect(conn)}
              onCheckHealth={() => checkHealth.mutate(conn.id)}
              isCheckingHealth={
                checkHealth.isPending && checkHealth.variables === conn.id
              }
            />
          ))
        )}
      </div>

      {/* Confirm-disconnect dialog — Dialog handles a11y + escape close. */}
      <Dialog
        open={!!confirmDisconnect}
        onOpenChange={(open) => {
          if (!open) setConfirmDisconnect(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect inbox?</DialogTitle>
            <DialogDescription>
              {confirmDisconnect?.email_address} will stop syncing immediately.
              All previously synced messages remain in your inbox.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setConfirmDisconnect(null)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={disconnect.isPending}
              onClick={() => {
                if (confirmDisconnect) {
                  disconnect.mutate(confirmDisconnect.id, {
                    onSettled: () => setConfirmDisconnect(null),
                  });
                }
              }}
            >
              {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── Subcomponents ───────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-card">
      <Mail className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">No inboxes connected yet.</p>
      <p className="text-xs text-muted-foreground/70">
        Connect a Gmail account to start tracking replies.
      </p>
    </div>
  );
}

function ConnectionRow({
  connection,
  onDisconnect,
  onCheckHealth,
  isCheckingHealth,
}: {
  connection: InboxConnection;
  onDisconnect: () => void;
  onCheckHealth: () => void;
  isCheckingHealth: boolean;
}) {
  const statusConfig =
    CONNECTION_STATUS_CONFIG[connection.status] ?? {
      label: connection.status,
      variant: "outline" as const,
    };

  const lastSync = connection.last_sync_at
    ? formatDistanceToNow(parseISO(connection.last_sync_at), { addSuffix: true })
    : "Never";

  const connectedAt = formatDistanceToNow(parseISO(connection.created_at), {
    addSuffix: true,
  });

  const HealthIcon =
    connection.status === "active"
      ? CheckCircle2
      : connection.status === "revoked" || connection.status === "error"
        ? XCircle
        : AlertCircle;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-muted p-2">
            <Mail className="h-4 w-4 text-foreground" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {connection.email_address}
              </span>
              <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {connection.provider} · connected {connectedAt}
            </p>
            <p className="text-xs text-muted-foreground">
              <HealthIcon
                className="mr-1 inline h-3 w-3 align-text-bottom"
                aria-hidden="true"
              />
              Last sync: {lastSync}
              {connection.last_error && (
                <span className="ml-2 text-destructive">
                  · {connection.last_error}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onCheckHealth}
            disabled={isCheckingHealth}
            aria-label={`Refresh health for ${connection.email_address}`}
          >
            <RefreshCw
              className={`mr-1.5 h-3.5 w-3.5 ${
                isCheckingHealth ? "animate-spin" : ""
              }`}
            />
            {isCheckingHealth ? "Checking…" : "Refresh"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDisconnect}
            aria-label={`Disconnect ${connection.email_address}`}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Disconnect
          </Button>
        </div>
      </div>
    </Card>
  );
}
