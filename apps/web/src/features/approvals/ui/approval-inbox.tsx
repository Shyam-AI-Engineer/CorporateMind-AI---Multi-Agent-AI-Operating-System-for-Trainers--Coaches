"use client";

import { useState } from "react";
import { AlertCircle, ChevronRight, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace } from "@/hooks/use-workspace";
import { useApprovals, useMyReviewApprovals } from "@/features/approvals/api/use-approvals";
import type { ApprovalPriority, ApprovalRequestOut, ApprovalStatus } from "@/features/approvals/types";
import Link from "next/link";
import type { Route } from "next";

// ── Priority badge ────────────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: ApprovalPriority }) {
  const colors: Record<ApprovalPriority, string> = {
    low: "bg-slate-100 text-slate-600 border-slate-200",
    medium: "bg-blue-100 text-blue-700 border-blue-200",
    high: "bg-amber-100 text-amber-700 border-amber-200",
    urgent: "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <span
      data-testid={`priority-badge-${priority}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[priority]}`}
    >
      {priority}
    </span>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ApprovalStatus }) {
  const colors: Record<ApprovalStatus, string> = {
    pending: "bg-amber-100 text-amber-700 border-amber-200",
    in_review: "bg-blue-100 text-blue-700 border-blue-200",
    approved: "bg-green-100 text-green-700 border-green-200",
    rejected: "bg-red-100 text-red-700 border-red-200",
    cancelled: "bg-slate-100 text-slate-500 border-slate-200",
  };
  const labels: Record<ApprovalStatus, string> = {
    pending: "Pending",
    in_review: "In Review",
    approved: "Approved",
    rejected: "Rejected",
    cancelled: "Cancelled",
  };
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[status]}`}
    >
      {labels[status]}
    </span>
  );
}

// ── Filter controls ───────────────────────────────────────────────────────────

interface Filters {
  status?: string;
  priority?: string;
  assigned_reviewer?: string;
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  return (
    <div data-testid="approval-filters" className="flex flex-wrap items-center gap-3">
      <select
        data-testid="filter-status"
        value={filters.status ?? ""}
        onChange={(e) => onChange({ ...filters, status: e.target.value || undefined })}
        className="h-8 rounded-md border border-input bg-transparent px-2 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      >
        <option value="">All Statuses</option>
        <option value="pending">Pending</option>
        <option value="in_review">In Review</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
        <option value="cancelled">Cancelled</option>
      </select>

      <select
        data-testid="filter-priority"
        value={filters.priority ?? ""}
        onChange={(e) => onChange({ ...filters, priority: e.target.value || undefined })}
        className="h-8 rounded-md border border-input bg-transparent px-2 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
      >
        <option value="">All Priorities</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="urgent">Urgent</option>
      </select>

      <input
        data-testid="filter-reviewer"
        type="text"
        placeholder="Reviewer user ID…"
        value={filters.assigned_reviewer ?? ""}
        onChange={(e) =>
          onChange({ ...filters, assigned_reviewer: e.target.value || undefined })
        }
        className="h-8 w-48 rounded-md border border-input bg-transparent px-2 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
      />

      {(filters.status || filters.priority || filters.assigned_reviewer) && (
        <Button
          size="sm"
          variant="ghost"
          data-testid="clear-filters-btn"
          onClick={() => onChange({})}
          className="h-8 text-xs"
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}

// ── Single approval row ───────────────────────────────────────────────────────

function ApprovalRow({ item }: { item: ApprovalRequestOut }) {
  return (
    <Link
      href={`/approvals/${item.id}` as Route}
      data-testid={`approval-row-${item.id}`}
      className="flex items-center gap-4 rounded-md border px-4 py-3 text-sm hover:bg-muted/40 transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span data-testid={`approval-entity-type-${item.id}`} className="font-medium capitalize">
            {item.entity_type}
          </span>
          <PriorityBadge priority={item.priority} />
          <StatusBadge status={item.status} />
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>Requested by <span className="font-mono">{item.requested_by.slice(0, 8)}</span></span>
          {item.due_date && (
            <span data-testid={`approval-due-${item.id}`}>
              Due {new Date(item.due_date).toLocaleDateString()}
            </span>
          )}
          <span>{new Date(item.created_at).toLocaleDateString()}</span>
        </div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </Link>
  );
}

// ── Approval list with pagination ─────────────────────────────────────────────

function ApprovalList({
  workspaceId,
  filters,
  testId,
}: {
  workspaceId: string;
  filters: Filters;
  testId: string;
}) {
  const [cursor, setCursor] = useState<string | undefined>();
  const { data, isLoading, isError } = useApprovals(workspaceId, { cursor, ...filters });

  if (isLoading) {
    return (
      <div data-testid={`${testId}-skeleton`} className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid={`${testId}-error`} className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load approval requests.
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div data-testid={testId} className="space-y-3">
      {items.length === 0 ? (
        <p data-testid={`${testId}-empty`} className="text-sm text-muted-foreground py-4">
          No approval requests found.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <ApprovalRow key={item.id} item={item} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        {cursor && (
          <Button
            size="sm"
            variant="outline"
            data-testid={`${testId}-prev-btn`}
            onClick={() => setCursor(undefined)}
          >
            <RefreshCw className="mr-1 h-3 w-3" />
            Back to latest
          </Button>
        )}
        {data?.has_more && (
          <Button
            size="sm"
            variant="outline"
            data-testid={`${testId}-next-btn`}
            onClick={() => setCursor(data.next_cursor ?? undefined)}
            className="ml-auto"
          >
            Load older
          </Button>
        )}
      </div>
    </div>
  );
}

// ── My reviews list ───────────────────────────────────────────────────────────

function MyReviewsList({ workspaceId }: { workspaceId: string }) {
  const [cursor, setCursor] = useState<string | undefined>();
  const { data, isLoading, isError } = useMyReviewApprovals(workspaceId, cursor);

  if (isLoading) {
    return (
      <div data-testid="my-reviews-skeleton" className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="my-reviews-error" className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load your assigned reviews.
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div data-testid="my-reviews-list" className="space-y-3">
      {items.length === 0 ? (
        <p data-testid="my-reviews-empty" className="text-sm text-muted-foreground py-4">
          No approval requests assigned to you.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <ApprovalRow key={item.id} item={item} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        {cursor && (
          <Button
            size="sm"
            variant="outline"
            data-testid="my-reviews-prev-btn"
            onClick={() => setCursor(undefined)}
          >
            <RefreshCw className="mr-1 h-3 w-3" />
            Back to latest
          </Button>
        )}
        {data?.has_more && (
          <Button
            size="sm"
            variant="outline"
            data-testid="my-reviews-next-btn"
            onClick={() => setCursor(data.next_cursor ?? undefined)}
            className="ml-auto"
          >
            Load older
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Main Approval Inbox ───────────────────────────────────────────────────────

export function ApprovalInbox() {
  const { workspaceId } = useWorkspace();
  const [filters, setFilters] = useState<Filters>({});

  if (!workspaceId) {
    return (
      <div data-testid="approvals-no-workspace" className="text-sm text-muted-foreground">
        Select a workspace to view approvals.
      </div>
    );
  }

  return (
    <div data-testid="approval-inbox" className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Approval Inbox</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs defaultValue="all">
            <TabsList data-testid="approval-tabs">
              <TabsTrigger value="all" data-testid="tab-all">
                All Requests
              </TabsTrigger>
              <TabsTrigger value="my-reviews" data-testid="tab-my-reviews">
                My Reviews
              </TabsTrigger>
            </TabsList>

            <TabsContent value="all" className="mt-4 space-y-4">
              <FilterBar filters={filters} onChange={setFilters} />
              <ApprovalList
                workspaceId={workspaceId}
                filters={filters}
                testId="all-approvals-list"
              />
            </TabsContent>

            <TabsContent value="my-reviews" className="mt-4">
              <MyReviewsList workspaceId={workspaceId} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
