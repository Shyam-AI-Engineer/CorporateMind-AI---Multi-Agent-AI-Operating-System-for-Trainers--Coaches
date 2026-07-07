/**
 * Tests for customer-timeline.tsx — Sprint 49
 * Pattern: no jest-dom; use .not.toBeNull() / .toBeNull() / .textContent
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type {
  CustomerTimelineEvent,
  CustomerRelationshipSummary,
  Customer360,
} from "@/features/customers/types-timeline";
import { TIMELINE_EVENT_TYPES } from "@/features/customers/types-timeline";

// ── Mocks must be declared before await import ────────────────────────────────

vi.mock("@/features/customers/api/use-timeline", () => ({
  useCustomerTimeline: vi.fn(),
  useRelationshipSummary: vi.fn(),
  useCustomer360: vi.fn(),
}));

const {
  EventTypeBadge,
  TimelineFilterBar,
  TimelineEventItem,
  TimelineEventDrawer,
  RelationshipSummaryCard,
  CustomerTimeline,
  Customer360Tab,
} = await import("./customer-timeline");

const {
  useCustomerTimeline,
  useRelationshipSummary,
  useCustomer360,
} = await import("@/features/customers/api/use-timeline");

const mockUseTimeline = vi.mocked(useCustomerTimeline);
const mockUseSummary = vi.mocked(useRelationshipSummary);
const mockUse360 = vi.mocked(useCustomer360);

// ── Helpers ───────────────────────────────────────────────────────────────────

type QueryResult = { data?: unknown; isLoading: boolean; isError: boolean };

function idleQuery<T>(data: T): QueryResult {
  return { data: { data }, isLoading: false, isError: false };
}

function loadingQuery(): QueryResult {
  return { data: undefined, isLoading: true, isError: false };
}

function errorQuery(): QueryResult {
  return { data: undefined, isLoading: false, isError: true };
}

function makeEvent(overrides: Partial<CustomerTimelineEvent> = {}): CustomerTimelineEvent {
  return {
    event_id: "evt-1",
    event_type: "customer_created",
    occurred_at: "2026-07-01T10:00:00Z",
    title: "Customer created",
    entity_type: "customer",
    entity_id: "cid-1",
    detail: {},
    ...overrides,
  };
}

function makeSummary(
  overrides: Partial<CustomerRelationshipSummary> = {}
): CustomerRelationshipSummary {
  return {
    customer_id: "cid-1",
    total_trainings: 3,
    completed_trainings: 2,
    total_certificates: 1,
    avg_feedback_rating: 4.5,
    current_health: "healthy",
    renewal_status: "active",
    latest_activity_at: "2026-07-01T10:00:00Z",
    days_since_last_interaction: 6,
    ...overrides,
  };
}

function makeTimeline(
  items: CustomerTimelineEvent[],
  opts?: { has_more?: boolean; next_cursor?: string | null; total?: number }
) {
  return {
    items,
    has_more: opts?.has_more ?? false,
    next_cursor: opts?.next_cursor ?? null,
    total: opts?.total ?? items.length,
  };
}

function make360(
  summary: CustomerRelationshipSummary,
  events: CustomerTimelineEvent[]
): Customer360 {
  return { customer_id: "cid-1", summary, recent_events: events };
}

function setupDefaultMocks() {
  mockUseTimeline.mockReturnValue(
    idleQuery(makeTimeline([])) as ReturnType<typeof useCustomerTimeline>
  );
  mockUseSummary.mockReturnValue(
    idleQuery(makeSummary()) as ReturnType<typeof useRelationshipSummary>
  );
  mockUse360.mockReturnValue(
    idleQuery(make360(makeSummary(), [])) as ReturnType<typeof useCustomer360>
  );
}

// ── EventTypeBadge ────────────────────────────────────────────────────────────

describe("EventTypeBadge", () => {
  it.each(TIMELINE_EVENT_TYPES)("renders badge for %s", (type) => {
    render(<EventTypeBadge eventType={type} />);
    expect(screen.getByTestId(`event-type-badge-${type}`)).not.toBeNull();
  });

  it("renders customer_created badge text", () => {
    render(<EventTypeBadge eventType="customer_created" />);
    const badge = screen.getByTestId("event-type-badge-customer_created");
    expect(badge.textContent).toContain("customer created");
  });

  it("renders training_session_completed badge text", () => {
    render(<EventTypeBadge eventType="training_session_completed" />);
    const badge = screen.getByTestId("event-type-badge-training_session_completed");
    expect(badge.textContent).toContain("training session completed");
  });

  it("renders certificate_issued badge text", () => {
    render(<EventTypeBadge eventType="certificate_issued" />);
    const badge = screen.getByTestId("event-type-badge-certificate_issued");
    expect(badge.textContent).toContain("certificate issued");
  });

  it("renders renewal_created badge text", () => {
    render(<EventTypeBadge eventType="renewal_created" />);
    const badge = screen.getByTestId("event-type-badge-renewal_created");
    expect(badge.textContent).toContain("renewal created");
  });

  it("renders feedback_submitted badge text", () => {
    render(<EventTypeBadge eventType="feedback_submitted" />);
    const badge = screen.getByTestId("event-type-badge-feedback_submitted");
    expect(badge.textContent).toContain("feedback submitted");
  });
});

// ── TimelineFilterBar ─────────────────────────────────────────────────────────

describe("TimelineFilterBar", () => {
  it("renders all 10 filter type buttons", () => {
    render(<TimelineFilterBar selected={[]} onChange={vi.fn()} />);
    TIMELINE_EVENT_TYPES.forEach((type) => {
      expect(screen.getByTestId(`filter-type-${type}`)).not.toBeNull();
    });
  });

  it("renders 'All' clear button", () => {
    render(<TimelineFilterBar selected={[]} onChange={vi.fn()} />);
    expect(screen.getByTestId("filter-clear-all")).not.toBeNull();
  });

  it("calls onChange with selected type when clicked", () => {
    const onChange = vi.fn();
    render(<TimelineFilterBar selected={[]} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("filter-type-renewal_created"));
    expect(onChange).toHaveBeenCalledWith(["renewal_created"]);
  });

  it("deselects type when clicked again", () => {
    const onChange = vi.fn();
    render(
      <TimelineFilterBar selected={["renewal_created"]} onChange={onChange} />
    );
    fireEvent.click(screen.getByTestId("filter-type-renewal_created"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("adds to existing selection", () => {
    const onChange = vi.fn();
    render(
      <TimelineFilterBar selected={["customer_created"]} onChange={onChange} />
    );
    fireEvent.click(screen.getByTestId("filter-type-renewal_created"));
    expect(onChange).toHaveBeenCalledWith(["customer_created", "renewal_created"]);
  });

  it("clear-all calls onChange with empty array", () => {
    const onChange = vi.fn();
    render(
      <TimelineFilterBar
        selected={["customer_created", "renewal_created"]}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByTestId("filter-clear-all"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("selected button has active style", () => {
    render(
      <TimelineFilterBar selected={["customer_created"]} onChange={vi.fn()} />
    );
    const btn = screen.getByTestId("filter-type-customer_created");
    expect(btn.className).toContain("bg-blue-600");
  });

  it("unselected button does not have active style", () => {
    render(<TimelineFilterBar selected={[]} onChange={vi.fn()} />);
    const btn = screen.getByTestId("filter-type-customer_created");
    expect(btn.className).not.toContain("bg-blue-600");
  });
});

// ── TimelineEventItem ─────────────────────────────────────────────────────────

describe("TimelineEventItem", () => {
  it("renders event by test id", () => {
    const event = makeEvent({ event_id: "unique-id-123" });
    render(<TimelineEventItem event={event} onClick={vi.fn()} />);
    expect(screen.getByTestId("timeline-event-unique-id-123")).not.toBeNull();
  });

  it("renders event title text", () => {
    const event = makeEvent({ event_id: "e1", title: "My test event" });
    render(<TimelineEventItem event={event} onClick={vi.fn()} />);
    const titleEl = screen.getByTestId("event-title-e1");
    expect(titleEl.textContent).toContain("My test event");
  });

  it("renders event date element", () => {
    const event = makeEvent({ event_id: "e2" });
    render(<TimelineEventItem event={event} onClick={vi.fn()} />);
    expect(screen.getByTestId("event-date-e2")).not.toBeNull();
  });

  it("renders event type badge", () => {
    const event = makeEvent({ event_type: "certificate_issued" });
    render(<TimelineEventItem event={event} onClick={vi.fn()} />);
    expect(screen.getByTestId("event-type-badge-certificate_issued")).not.toBeNull();
  });

  it("calls onClick when item clicked", () => {
    const onClick = vi.fn();
    const event = makeEvent({ event_id: "e3" });
    render(<TimelineEventItem event={event} onClick={onClick} />);
    fireEvent.click(screen.getByTestId("timeline-event-e3"));
    expect(onClick).toHaveBeenCalledWith(event);
  });

  it("renders renewal_status_changed type badge", () => {
    const event = makeEvent({
      event_id: "e4",
      event_type: "renewal_status_changed",
    });
    render(<TimelineEventItem event={event} onClick={vi.fn()} />);
    expect(screen.getByTestId("event-type-badge-renewal_status_changed")).not.toBeNull();
  });
});

// ── TimelineEventDrawer ───────────────────────────────────────────────────────

describe("TimelineEventDrawer", () => {
  it("renders drawer", () => {
    render(<TimelineEventDrawer event={makeEvent()} onClose={vi.fn()} />);
    expect(screen.getByTestId("timeline-event-drawer")).not.toBeNull();
  });

  it("renders event title", () => {
    const event = makeEvent({ title: "Drawer title" });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-event-title").textContent).toContain("Drawer title");
  });

  it("renders occurred_at element", () => {
    render(<TimelineEventDrawer event={makeEvent()} onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-occurred-at")).not.toBeNull();
  });

  it("renders event type badge", () => {
    const event = makeEvent({ event_type: "feedback_submitted" });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    expect(screen.getByTestId("event-type-badge-feedback_submitted")).not.toBeNull();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(<TimelineEventDrawer event={makeEvent()} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders entity type when present", () => {
    const event = makeEvent({ entity_type: "training_session" });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-entity-type").textContent).toContain("training_session");
  });

  it("renders detail section when detail present", () => {
    const event = makeEvent({ detail: { status: "completed" } });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-detail")).not.toBeNull();
  });

  it("does not render detail section when detail empty", () => {
    const event = makeEvent({ detail: {} });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-detail")).toBeNull();
  });

  it("renders all detail entries", () => {
    const event = makeEvent({
      detail: { program_name: "Leadership", status: "active" },
    });
    render(<TimelineEventDrawer event={event} onClose={vi.fn()} />);
    const detail = screen.getByTestId("drawer-detail");
    expect(detail.textContent).toContain("Leadership");
    expect(detail.textContent).toContain("active");
  });
});

// ── RelationshipSummaryCard ────────────────────────────────────────────────────

describe("RelationshipSummaryCard", () => {
  it("renders the card", () => {
    render(<RelationshipSummaryCard summary={makeSummary()} />);
    expect(screen.getByTestId("relationship-summary-card")).not.toBeNull();
  });

  it("renders total trainings", () => {
    render(<RelationshipSummaryCard summary={makeSummary({ total_trainings: 5 })} />);
    expect(screen.getByTestId("summary-total-trainings").textContent).toContain("5");
  });

  it("renders completed trainings", () => {
    render(
      <RelationshipSummaryCard summary={makeSummary({ completed_trainings: 3 })} />
    );
    expect(
      screen.getByTestId("summary-completed-trainings").textContent
    ).toContain("3 completed");
  });

  it("renders certificates count", () => {
    render(
      <RelationshipSummaryCard summary={makeSummary({ total_certificates: 7 })} />
    );
    expect(screen.getByTestId("summary-certificates").textContent).toContain("7");
  });

  it("renders avg rating when present", () => {
    render(
      <RelationshipSummaryCard summary={makeSummary({ avg_feedback_rating: 4.3 })} />
    );
    expect(screen.getByTestId("summary-avg-rating").textContent).toContain("4.3");
  });

  it("renders dash when avg rating null", () => {
    render(
      <RelationshipSummaryCard
        summary={makeSummary({ avg_feedback_rating: null })}
      />
    );
    expect(screen.getByTestId("summary-avg-rating").textContent).toContain("—");
  });

  it("renders days since when present", () => {
    render(
      <RelationshipSummaryCard
        summary={makeSummary({ days_since_last_interaction: 6 })}
      />
    );
    expect(screen.getByTestId("summary-days-since").textContent).toContain("6d ago");
  });

  it("renders dash when days since null", () => {
    render(
      <RelationshipSummaryCard
        summary={makeSummary({ days_since_last_interaction: null })}
      />
    );
    expect(screen.getByTestId("summary-days-since").textContent).toContain("—");
  });

  it("renders current health badge when present", () => {
    render(
      <RelationshipSummaryCard summary={makeSummary({ current_health: "at_risk" })} />
    );
    expect(screen.getByTestId("summary-health").textContent).toContain("at risk");
  });

  it("does not render health badge when null", () => {
    render(
      <RelationshipSummaryCard summary={makeSummary({ current_health: null })} />
    );
    expect(screen.queryByTestId("summary-health")).toBeNull();
  });

  it("renders zero trainings", () => {
    render(<RelationshipSummaryCard summary={makeSummary({ total_trainings: 0 })} />);
    expect(screen.getByTestId("summary-total-trainings").textContent).toContain("0");
  });
});

// ── CustomerTimeline ──────────────────────────────────────────────────────────

describe("CustomerTimeline", () => {
  beforeEach(() => {
    setupDefaultMocks();
  });

  it("renders the timeline container", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("customer-timeline")).not.toBeNull();
  });

  it("shows loading state when timeline loading", () => {
    mockUseTimeline.mockReturnValue(
      loadingQuery() as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-loading")).not.toBeNull();
  });

  it("shows error state when timeline errors", () => {
    mockUseTimeline.mockReturnValue(
      errorQuery() as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-error")).not.toBeNull();
  });

  it("shows empty state when no events", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-empty")).not.toBeNull();
  });

  it("does not show empty state when events present", () => {
    mockUseTimeline.mockReturnValue(
      idleQuery(makeTimeline([makeEvent({ event_id: "e1" })])) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("timeline-empty")).toBeNull();
  });

  it("renders events list when events present", () => {
    const events = [makeEvent({ event_id: "e1" }), makeEvent({ event_id: "e2" })];
    mockUseTimeline.mockReturnValue(
      idleQuery(makeTimeline(events)) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-events-list")).not.toBeNull();
    expect(screen.getByTestId("timeline-event-e1")).not.toBeNull();
    expect(screen.getByTestId("timeline-event-e2")).not.toBeNull();
  });

  it("shows load more button when has_more is true", () => {
    mockUseTimeline.mockReturnValue(
      idleQuery(
        makeTimeline([makeEvent()], { has_more: true, next_cursor: "cursor-abc" })
      ) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-load-more")).not.toBeNull();
  });

  it("does not show load more when has_more is false", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("timeline-load-more")).toBeNull();
  });

  it("shows total count with plural wording", () => {
    mockUseTimeline.mockReturnValue(
      idleQuery(makeTimeline([], { total: 42 })) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-total").textContent).toContain("42");
    expect(screen.getByTestId("timeline-total").textContent).toContain("events");
  });

  it("shows singular event wording when total is 1", () => {
    mockUseTimeline.mockReturnValue(
      idleQuery(
        makeTimeline([makeEvent()], { total: 1 })
      ) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    const total = screen.getByTestId("timeline-total").textContent ?? "";
    expect(total).toContain("1");
    expect(total).not.toContain("1 events");
  });

  it("shows summary loading state", () => {
    mockUseSummary.mockReturnValue(
      loadingQuery() as ReturnType<typeof useRelationshipSummary>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("summary-loading")).not.toBeNull();
  });

  it("shows relationship summary card when loaded", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("relationship-summary-card")).not.toBeNull();
  });

  it("does not show summary card when summary loading", () => {
    mockUseSummary.mockReturnValue(
      loadingQuery() as ReturnType<typeof useRelationshipSummary>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("relationship-summary-card")).toBeNull();
  });

  it("renders filter bar", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("timeline-filter-bar")).not.toBeNull();
  });

  it("opens event drawer when event clicked", () => {
    const events = [makeEvent({ event_id: "e1", title: "Event One" })];
    mockUseTimeline.mockReturnValue(
      idleQuery(makeTimeline(events)) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("timeline-event-e1"));
    expect(screen.getByTestId("timeline-event-drawer")).not.toBeNull();
    expect(
      screen.getByTestId("drawer-event-title").textContent
    ).toContain("Event One");
  });

  it("closes event drawer when close clicked", () => {
    const events = [makeEvent({ event_id: "e1" })];
    mockUseTimeline.mockReturnValue(
      idleQuery(makeTimeline(events)) as ReturnType<typeof useCustomerTimeline>
    );
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("timeline-event-e1"));
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("timeline-event-drawer")).toBeNull();
  });

  it("no drawer initially", () => {
    render(<CustomerTimeline customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("timeline-event-drawer")).toBeNull();
  });
});

// ── Customer360Tab ────────────────────────────────────────────────────────────

describe("Customer360Tab", () => {
  beforeEach(() => {
    setupDefaultMocks();
  });

  it("renders the 360 tab container", () => {
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("customer-360-tab")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockUse360.mockReturnValue(
      loadingQuery() as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("360-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockUse360.mockReturnValue(
      errorQuery() as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("360-error")).not.toBeNull();
  });

  it("renders summary card when loaded", () => {
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("relationship-summary-card")).not.toBeNull();
  });

  it("shows no events message when recent_events empty", () => {
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("360-no-events")).not.toBeNull();
  });

  it("renders recent events section when events present", () => {
    const events = [makeEvent({ event_id: "re1" }), makeEvent({ event_id: "re2" })];
    mockUse360.mockReturnValue(
      idleQuery(make360(makeSummary(), events)) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.getByTestId("360-recent-events")).not.toBeNull();
    expect(screen.getByTestId("timeline-event-re1")).not.toBeNull();
    expect(screen.getByTestId("timeline-event-re2")).not.toBeNull();
  });

  it("does not show no-events message when events present", () => {
    const events = [makeEvent({ event_id: "re1" })];
    mockUse360.mockReturnValue(
      idleQuery(make360(makeSummary(), events)) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("360-no-events")).toBeNull();
  });

  it("opens event drawer when recent event clicked", () => {
    const events = [makeEvent({ event_id: "re1", title: "Recent event" })];
    mockUse360.mockReturnValue(
      idleQuery(make360(makeSummary(), events)) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("timeline-event-re1"));
    expect(screen.getByTestId("timeline-event-drawer")).not.toBeNull();
    expect(
      screen.getByTestId("drawer-event-title").textContent
    ).toContain("Recent event");
  });

  it("closes event drawer when close clicked", () => {
    const events = [makeEvent({ event_id: "re1" })];
    mockUse360.mockReturnValue(
      idleQuery(make360(makeSummary(), events)) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    fireEvent.click(screen.getByTestId("timeline-event-re1"));
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("timeline-event-drawer")).toBeNull();
  });

  it("renders summary training count from 360 view", () => {
    const summary = makeSummary({ total_trainings: 10 });
    mockUse360.mockReturnValue(
      idleQuery(make360(summary, [])) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(
      screen.getByTestId("summary-total-trainings").textContent
    ).toContain("10");
  });

  it("renders summary certificate count from 360 view", () => {
    const summary = makeSummary({ total_certificates: 4 });
    mockUse360.mockReturnValue(
      idleQuery(make360(summary, [])) as ReturnType<typeof useCustomer360>
    );
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(
      screen.getByTestId("summary-certificates").textContent
    ).toContain("4");
  });

  it("no drawer initially in 360 tab", () => {
    render(<Customer360Tab customerId="cid-1" workspaceId="ws-1" />);
    expect(screen.queryByTestId("timeline-event-drawer")).toBeNull();
  });
});

// ── TIMELINE_EVENT_TYPES constants ────────────────────────────────────────────

describe("TIMELINE_EVENT_TYPES", () => {
  it("has 10 entries", () => {
    expect(TIMELINE_EVENT_TYPES).toHaveLength(10);
  });

  it("all event types are distinct", () => {
    const unique = new Set(TIMELINE_EVENT_TYPES);
    expect(unique.size).toBe(10);
  });

  it("includes customer_created", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("customer_created");
  });

  it("includes training_engagement_created", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("training_engagement_created");
  });

  it("includes training_session_started", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("training_session_started");
  });

  it("includes training_session_completed", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("training_session_completed");
  });

  it("includes attendance_recorded", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("attendance_recorded");
  });

  it("includes certificate_issued", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("certificate_issued");
  });

  it("includes feedback_submitted", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("feedback_submitted");
  });

  it("includes customer_health_updated", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("customer_health_updated");
  });

  it("includes renewal_created", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("renewal_created");
  });

  it("includes renewal_status_changed", () => {
    expect(TIMELINE_EVENT_TYPES).toContain("renewal_status_changed");
  });
});
