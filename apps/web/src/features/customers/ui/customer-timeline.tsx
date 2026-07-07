"use client";

import { useState } from "react";
import {
  useCustomerTimeline,
  useCustomer360,
  useRelationshipSummary,
} from "@/features/customers/api/use-timeline";
import type {
  CustomerTimelineEvent,
  CustomerRelationshipSummary,
  TimelineEventType,
  TimelineFilters,
} from "@/features/customers/types-timeline";
import { TIMELINE_EVENT_TYPES } from "@/features/customers/types-timeline";

// ── EventIcon ─────────────────────────────────────────────────────────────────

function eventIcon(eventType: TimelineEventType): string {
  switch (eventType) {
    case "customer_created": return "🏢";
    case "training_engagement_created": return "📋";
    case "training_session_started": return "▶";
    case "training_session_completed": return "✅";
    case "attendance_recorded": return "👤";
    case "certificate_issued": return "🎓";
    case "feedback_submitted": return "⭐";
    case "customer_health_updated": return "💙";
    case "renewal_created": return "🔄";
    case "renewal_status_changed": return "📝";
  }
}

function eventColor(eventType: TimelineEventType): string {
  switch (eventType) {
    case "customer_created": return "bg-blue-100 text-blue-800";
    case "training_engagement_created": return "bg-purple-100 text-purple-800";
    case "training_session_started": return "bg-indigo-100 text-indigo-800";
    case "training_session_completed": return "bg-green-100 text-green-800";
    case "attendance_recorded": return "bg-cyan-100 text-cyan-800";
    case "certificate_issued": return "bg-yellow-100 text-yellow-800";
    case "feedback_submitted": return "bg-orange-100 text-orange-800";
    case "customer_health_updated": return "bg-sky-100 text-sky-800";
    case "renewal_created": return "bg-teal-100 text-teal-800";
    case "renewal_status_changed": return "bg-violet-100 text-violet-800";
  }
}

// ── EventTypeBadge ────────────────────────────────────────────────────────────

export function EventTypeBadge({ eventType }: { eventType: TimelineEventType }) {
  return (
    <span
      data-testid={`event-type-badge-${eventType}`}
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${eventColor(eventType)}`}
    >
      <span>{eventIcon(eventType)}</span>
      <span>{eventType.replace(/_/g, " ")}</span>
    </span>
  );
}

// ── TimelineFilters ───────────────────────────────────────────────────────────

interface TimelineFilterBarProps {
  selected: TimelineEventType[];
  onChange: (types: TimelineEventType[]) => void;
}

export function TimelineFilterBar({ selected, onChange }: TimelineFilterBarProps) {
  function toggle(type: TimelineEventType) {
    if (selected.includes(type)) {
      onChange(selected.filter((t) => t !== type));
    } else {
      onChange([...selected, type]);
    }
  }

  return (
    <div data-testid="timeline-filter-bar" className="flex flex-wrap gap-1.5">
      <button
        data-testid="filter-clear-all"
        onClick={() => onChange([])}
        className={`rounded px-2 py-0.5 text-xs ${
          selected.length === 0
            ? "bg-gray-900 text-white"
            : "border text-muted-foreground hover:bg-muted"
        }`}
      >
        All
      </button>
      {TIMELINE_EVENT_TYPES.map((type) => (
        <button
          key={type}
          data-testid={`filter-type-${type}`}
          onClick={() => toggle(type)}
          className={`rounded px-2 py-0.5 text-xs ${
            selected.includes(type)
              ? "bg-blue-600 text-white"
              : "border text-muted-foreground hover:bg-muted"
          }`}
        >
          {eventIcon(type)} {type.replace(/_/g, " ")}
        </button>
      ))}
    </div>
  );
}

// ── TimelineEventItem ─────────────────────────────────────────────────────────

interface TimelineEventItemProps {
  event: CustomerTimelineEvent;
  onClick: (e: CustomerTimelineEvent) => void;
}

export function TimelineEventItem({ event, onClick }: TimelineEventItemProps) {
  return (
    <button
      data-testid={`timeline-event-${event.event_id}`}
      onClick={() => onClick(event)}
      className="flex w-full items-start gap-3 rounded-lg border bg-white p-3 text-left hover:bg-muted/30 transition-colors"
    >
      <div className="mt-0.5 flex-shrink-0">
        <EventTypeBadge eventType={event.event_type} />
      </div>
      <div className="min-w-0 flex-1">
        <p
          data-testid={`event-title-${event.event_id}`}
          className="truncate text-sm font-medium"
        >
          {event.title}
        </p>
        <p
          data-testid={`event-date-${event.event_id}`}
          className="mt-0.5 text-xs text-muted-foreground"
        >
          {new Date(event.occurred_at).toLocaleString()}
        </p>
      </div>
    </button>
  );
}

// ── TimelineDrawer ────────────────────────────────────────────────────────────

interface TimelineDrawerProps {
  event: CustomerTimelineEvent;
  onClose: () => void;
}

export function TimelineEventDrawer({ event, onClose }: TimelineDrawerProps) {
  const detailEntries = Object.entries(event.detail ?? {});
  return (
    <div
      data-testid="timeline-event-drawer"
      className="fixed right-0 top-0 z-50 h-full w-80 overflow-y-auto border-l bg-white p-5 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold" data-testid="drawer-event-title">
          {event.title}
        </h3>
        <button
          onClick={onClose}
          data-testid="drawer-close"
          className="text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </div>
      <div className="mb-3">
        <EventTypeBadge eventType={event.event_type} />
      </div>
      <p className="mb-4 text-xs text-muted-foreground" data-testid="drawer-occurred-at">
        {new Date(event.occurred_at).toLocaleString()}
      </p>
      {event.entity_type && (
        <p className="mb-1 text-xs text-muted-foreground" data-testid="drawer-entity-type">
          {event.entity_type}
        </p>
      )}
      {detailEntries.length > 0 && (
        <div data-testid="drawer-detail" className="mt-4 space-y-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Details
          </p>
          {detailEntries.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-xs">
              <span className="font-medium">{k.replace(/_/g, " ")}:</span>
              <span className="text-muted-foreground">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── RelationshipSummaryCard ────────────────────────────────────────────────────

export function RelationshipSummaryCard({
  summary,
}: {
  summary: CustomerRelationshipSummary;
}) {
  return (
    <div
      data-testid="relationship-summary-card"
      className="grid grid-cols-2 gap-3 rounded-lg border bg-white p-4 md:grid-cols-4"
    >
      <div className="text-center">
        <p className="text-xs text-muted-foreground">Trainings</p>
        <p className="text-xl font-semibold" data-testid="summary-total-trainings">
          {summary.total_trainings}
        </p>
        <p className="text-xs text-muted-foreground" data-testid="summary-completed-trainings">
          {summary.completed_trainings} completed
        </p>
      </div>
      <div className="text-center">
        <p className="text-xs text-muted-foreground">Certificates</p>
        <p className="text-xl font-semibold" data-testid="summary-certificates">
          {summary.total_certificates}
        </p>
      </div>
      <div className="text-center">
        <p className="text-xs text-muted-foreground">Avg Rating</p>
        <p className="text-xl font-semibold" data-testid="summary-avg-rating">
          {summary.avg_feedback_rating != null
            ? `★ ${summary.avg_feedback_rating.toFixed(1)}`
            : "—"}
        </p>
      </div>
      <div className="text-center">
        <p className="text-xs text-muted-foreground">Last Activity</p>
        <p className="text-sm font-medium" data-testid="summary-days-since">
          {summary.days_since_last_interaction != null
            ? `${summary.days_since_last_interaction}d ago`
            : "—"}
        </p>
        {summary.current_health && (
          <span
            data-testid="summary-health"
            className="mt-1 inline-block rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800"
          >
            {summary.current_health.replace(/_/g, " ")}
          </span>
        )}
      </div>
    </div>
  );
}

// ── CustomerTimeline ──────────────────────────────────────────────────────────

interface CustomerTimelineProps {
  customerId: string;
  workspaceId: string;
}

export function CustomerTimeline({ customerId, workspaceId }: CustomerTimelineProps) {
  const [activeFilters, setActiveFilters] = useState<TimelineEventType[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [selectedEvent, setSelectedEvent] = useState<CustomerTimelineEvent | null>(null);

  const opts: TimelineFilters = {
    event_types: activeFilters.length > 0 ? activeFilters : undefined,
    cursor,
    limit: 20,
  };

  const { data, isLoading, isError } = useCustomerTimeline(
    customerId,
    workspaceId,
    opts
  );

  const { data: summaryData, isLoading: summaryLoading } = useRelationshipSummary(
    customerId,
    workspaceId
  );

  const items = data?.data?.items ?? [];
  const hasMore = data?.data?.has_more ?? false;
  const nextCursor = data?.data?.next_cursor ?? undefined;
  const total = data?.data?.total ?? 0;
  const summary = summaryData?.data ?? null;

  return (
    <div data-testid="customer-timeline" className="space-y-4">
      {/* Summary card */}
      {summaryLoading && (
        <p data-testid="summary-loading" className="text-xs text-muted-foreground">
          Loading summary…
        </p>
      )}
      {!summaryLoading && summary && (
        <RelationshipSummaryCard summary={summary} />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium" data-testid="timeline-total">
          {total} event{total !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Filters */}
      <TimelineFilterBar
        selected={activeFilters}
        onChange={(types) => {
          setActiveFilters(types);
          setCursor(undefined);
        }}
      />

      {/* Loading / error */}
      {isLoading && (
        <p data-testid="timeline-loading" className="py-4 text-center text-sm text-muted-foreground">
          Loading timeline…
        </p>
      )}
      {isError && (
        <p data-testid="timeline-error" className="py-4 text-center text-sm text-red-600">
          Failed to load timeline.
        </p>
      )}

      {/* Events */}
      {!isLoading && !isError && items.length === 0 && (
        <p data-testid="timeline-empty" className="py-8 text-center text-sm text-muted-foreground">
          No events yet.
        </p>
      )}
      {!isLoading && !isError && items.length > 0 && (
        <div data-testid="timeline-events-list" className="space-y-2">
          {items.map((event) => (
            <TimelineEventItem
              key={event.event_id}
              event={event}
              onClick={setSelectedEvent}
            />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasMore && nextCursor && (
        <div className="flex justify-center">
          <button
            data-testid="timeline-load-more"
            onClick={() => setCursor(nextCursor)}
            className="rounded border px-4 py-2 text-sm hover:bg-muted"
          >
            Load more
          </button>
        </div>
      )}

      {/* Event detail drawer */}
      {selectedEvent && (
        <TimelineEventDrawer
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}

// ── Customer360Tab ─────────────────────────────────────────────────────────────

export function Customer360Tab({
  customerId,
  workspaceId,
}: {
  customerId: string;
  workspaceId: string;
}) {
  const { data, isLoading, isError } = useCustomer360(customerId, workspaceId);
  const [selectedEvent, setSelectedEvent] = useState<CustomerTimelineEvent | null>(null);

  const view = data?.data ?? null;

  return (
    <div data-testid="customer-360-tab" className="space-y-4">
      {isLoading && (
        <p data-testid="360-loading" className="text-xs text-muted-foreground">
          Loading 360 view…
        </p>
      )}
      {isError && (
        <p data-testid="360-error" className="text-xs text-red-600">
          Failed to load customer view.
        </p>
      )}
      {!isLoading && !isError && view && (
        <>
          <RelationshipSummaryCard summary={view.summary} />
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Recent Activity
            </p>
            {view.recent_events.length === 0 && (
              <p data-testid="360-no-events" className="text-xs text-muted-foreground">
                No recent activity.
              </p>
            )}
            {view.recent_events.length > 0 && (
              <div data-testid="360-recent-events" className="space-y-2">
                {view.recent_events.map((event) => (
                  <TimelineEventItem
                    key={event.event_id}
                    event={event}
                    onClick={setSelectedEvent}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
      {selectedEvent && (
        <TimelineEventDrawer
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}
