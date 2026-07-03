import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  TrainingCenter,
  TrainingStatusBadge,
  TrainingPriorityBadge,
} from "./training-center";

// ── Mock hooks ────────────────────────────────────────────────────────────────

vi.mock("@/features/training/api/use-training", () => ({
  useTrainingEngagements:         vi.fn(),
  useTrainingEngagement:          vi.fn(),
  useCreateTrainingEngagement:    vi.fn(),
  useUpdateTrainingEngagement:    vi.fn(),
  useStartEngagement:             vi.fn(),
  useCompleteEngagement:          vi.fn(),
  useCancelEngagement:            vi.fn(),
  useAssignTrainer:               vi.fn(),
  useAssignCoordinator:           vi.fn(),
}));

import {
  useTrainingEngagements,
  useCreateTrainingEngagement,
  useUpdateTrainingEngagement,
  useStartEngagement,
  useCompleteEngagement,
  useCancelEngagement,
  useAssignTrainer,
  useAssignCoordinator,
} from "@/features/training/api/use-training";
import type { TrainingEngagement } from "@/features/training/types";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const E1: TrainingEngagement = {
  id: "eid-1",
  tenant_id: "org-1",
  workspace_id: "ws-1",
  customer_id: "cid-1",
  program_name: "Leadership Bootcamp",
  description: "A 3-day leadership workshop",
  training_type: "Leadership",
  delivery_mode: "onsite",
  status: "planned",
  priority: "high",
  planned_start_date: "2026-08-01",
  planned_end_date: "2026-08-03",
  actual_start_date: null,
  actual_end_date: null,
  estimated_participants: 20,
  actual_participants: null,
  assigned_trainer_id: "tid-1",
  coordinator_id: "coid-1",
  location: "Mumbai",
  meeting_link: null,
  notes: "Priority client",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
};

const E2: TrainingEngagement = {
  ...E1,
  id: "eid-2",
  program_name: "Sales Mastery",
  training_type: "Sales",
  delivery_mode: "online",
  status: "in_progress",
  priority: "medium",
  planned_start_date: null,
  actual_start_date: "2026-07-10",
  assigned_trainer_id: null,
  coordinator_id: null,
  location: null,
  meeting_link: "https://meet.example.com/1",
  notes: null,
};

const E3_COMPLETED: TrainingEngagement = {
  ...E1,
  id: "eid-3",
  program_name: "Excel Workshop",
  status: "completed",
  priority: "low",
  actual_end_date: "2026-06-30",
  actual_participants: 18,
};

const E4_CANCELLED: TrainingEngagement = {
  ...E1,
  id: "eid-4",
  program_name: "Cancelled Program",
  status: "cancelled",
  priority: "urgent",
};

const E5_SCHEDULED: TrainingEngagement = {
  ...E1,
  id: "eid-5",
  program_name: "Scheduled Training",
  status: "scheduled",
  priority: "medium",
};

const LIST_OUT = {
  items: [E1, E2],
  next_cursor: null,
  has_more: false,
  total: 2,
};

const LIST_WITH_MORE = {
  items: [E1],
  next_cursor: "tok123",
  has_more: true,
  total: 10,
};

const EMPTY_LIST = { items: [], next_cursor: null, has_more: false, total: 0 };

const NOOP_MUTATE = vi.fn();

function mockAll(opts: {
  listOut?: object | null;
  loading?: boolean;
  error?: boolean;
} = {}) {
  const { loading = false, error = false } = opts;
  const listData = opts.listOut !== undefined ? opts.listOut : LIST_OUT;

  vi.mocked(useTrainingEngagements).mockReturnValue({
    data: listData ? { data: listData } : undefined,
    isLoading: loading,
    isError: error,
  } as ReturnType<typeof useTrainingEngagements>);

  vi.mocked(useCreateTrainingEngagement).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useCreateTrainingEngagement>);

  vi.mocked(useUpdateTrainingEngagement).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useUpdateTrainingEngagement>);

  vi.mocked(useStartEngagement).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useStartEngagement>);

  vi.mocked(useCompleteEngagement).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useCompleteEngagement>);

  vi.mocked(useCancelEngagement).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useCancelEngagement>);

  vi.mocked(useAssignTrainer).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useAssignTrainer>);

  vi.mocked(useAssignCoordinator).mockReturnValue({
    mutate: NOOP_MUTATE, isPending: false,
  } as ReturnType<typeof useAssignCoordinator>);
}

const WS = "ws-1";

function renderCenter() {
  return render(<TrainingCenter workspaceId={WS} />);
}

// ─────────────────────────────────────────────────────────────────────────────

describe("TrainingStatusBadge", () => {
  it("renders planned badge", () => {
    render(<TrainingStatusBadge status="planned" />);
    expect(screen.getByTestId("status-badge-planned")).toBeTruthy();
    expect(screen.getByText("planned")).toBeTruthy();
  });

  it("renders scheduled badge", () => {
    render(<TrainingStatusBadge status="scheduled" />);
    expect(screen.getByTestId("status-badge-scheduled")).toBeTruthy();
  });

  it("renders in_progress badge with space", () => {
    render(<TrainingStatusBadge status="in_progress" />);
    expect(screen.getByTestId("status-badge-in_progress")).toBeTruthy();
    expect(screen.getByText("in progress")).toBeTruthy();
  });

  it("renders completed badge", () => {
    render(<TrainingStatusBadge status="completed" />);
    expect(screen.getByTestId("status-badge-completed")).toBeTruthy();
  });

  it("renders cancelled badge", () => {
    render(<TrainingStatusBadge status="cancelled" />);
    expect(screen.getByTestId("status-badge-cancelled")).toBeTruthy();
  });
});

describe("TrainingPriorityBadge", () => {
  it("renders low badge", () => {
    render(<TrainingPriorityBadge priority="low" />);
    expect(screen.getByTestId("priority-badge-low")).toBeTruthy();
    expect(screen.getByText("low")).toBeTruthy();
  });

  it("renders medium badge", () => {
    render(<TrainingPriorityBadge priority="medium" />);
    expect(screen.getByTestId("priority-badge-medium")).toBeTruthy();
  });

  it("renders high badge", () => {
    render(<TrainingPriorityBadge priority="high" />);
    expect(screen.getByTestId("priority-badge-high")).toBeTruthy();
  });

  it("renders urgent badge", () => {
    render(<TrainingPriorityBadge priority="urgent" />);
    expect(screen.getByTestId("priority-badge-urgent")).toBeTruthy();
  });
});

describe("TrainingCenter — loading state", () => {
  beforeEach(() => mockAll({ loading: true }));

  it("renders loading indicator", () => {
    renderCenter();
    expect(screen.getByTestId("loading-state")).toBeTruthy();
  });

  it("does not render table while loading", () => {
    renderCenter();
    expect(screen.queryByTestId("engagement-table")).toBeNull();
  });
});

describe("TrainingCenter — error state", () => {
  beforeEach(() => mockAll({ error: true }));

  it("renders error message", () => {
    renderCenter();
    expect(screen.getByTestId("error-state")).toBeTruthy();
  });

  it("does not render table on error", () => {
    renderCenter();
    expect(screen.queryByTestId("engagement-table")).toBeNull();
  });
});

describe("TrainingCenter — empty state", () => {
  beforeEach(() => mockAll({ listOut: EMPTY_LIST }));

  it("renders empty state message", () => {
    renderCenter();
    expect(screen.getByTestId("empty-state")).toBeTruthy();
  });

  it("shows 0 engagements in total", () => {
    renderCenter();
    expect(screen.getByTestId("engagement-total").textContent).toContain("0");
  });

  it("KPI section shows all zeros", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-in-progress").textContent).toBe("0");
    expect(screen.getByTestId("kpi-planned").textContent).toBe("0");
    expect(screen.getByTestId("kpi-completed").textContent).toBe("0");
    expect(screen.getByTestId("kpi-cancelled").textContent).toBe("0");
  });
});

describe("TrainingCenter — data state", () => {
  beforeEach(() => mockAll());

  it("renders training center container", () => {
    renderCenter();
    expect(screen.getByTestId("training-center")).toBeTruthy();
  });

  it("renders the heading", () => {
    renderCenter();
    expect(screen.getByText("Training Engagements")).toBeTruthy();
  });

  it("shows total count", () => {
    renderCenter();
    expect(screen.getByTestId("engagement-total").textContent).toContain("2");
  });

  it("renders engagement table", () => {
    renderCenter();
    expect(screen.getByTestId("engagement-table")).toBeTruthy();
  });

  it("renders first engagement row", () => {
    renderCenter();
    expect(screen.getByTestId("engagement-row-eid-1")).toBeTruthy();
  });

  it("renders second engagement row", () => {
    renderCenter();
    expect(screen.getByTestId("engagement-row-eid-2")).toBeTruthy();
  });

  it("shows program name in table", () => {
    renderCenter();
    expect(screen.getByText("Leadership Bootcamp")).toBeTruthy();
    expect(screen.getByText("Sales Mastery")).toBeTruthy();
  });

  it("shows training type in table", () => {
    renderCenter();
    expect(screen.getByText("Leadership")).toBeTruthy();
    expect(screen.getByText("Sales")).toBeTruthy();
  });

  it("shows delivery mode in table", () => {
    renderCenter();
    expect(screen.getAllByText("onsite").length).toBeGreaterThan(0);
    expect(screen.getAllByText("online").length).toBeGreaterThan(0);
  });

  it("shows planned start date in table", () => {
    renderCenter();
    expect(screen.getByText("2026-08-01")).toBeTruthy();
  });
});

describe("TrainingCenter — KPI counts", () => {
  beforeEach(() =>
    mockAll({
      listOut: {
        ...LIST_OUT,
        items: [E1, E2, E3_COMPLETED, E4_CANCELLED, E5_SCHEDULED],
      },
    })
  );

  it("counts in-progress correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-in-progress").textContent).toBe("1");
  });

  it("counts planned correctly", () => {
    renderCenter();
    // E1 is planned, E5 is scheduled (not planned)
    expect(screen.getByTestId("kpi-planned").textContent).toBe("1");
  });

  it("counts completed correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-completed").textContent).toBe("1");
  });

  it("counts cancelled correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-cancelled").textContent).toBe("1");
  });
});

describe("TrainingCenter — add engagement button", () => {
  beforeEach(() => mockAll());

  it("renders add engagement button", () => {
    renderCenter();
    expect(screen.getByTestId("add-engagement-btn")).toBeTruthy();
  });

  it("opens create dialog on click", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-dialog")).toBeTruthy();
  });

  it("create dialog has program name field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-program-name")).toBeTruthy();
  });

  it("create dialog has customer id field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-customer-id")).toBeTruthy();
  });

  it("create dialog has training type field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-training-type")).toBeTruthy();
  });

  it("create dialog has delivery mode select", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-delivery-mode")).toBeTruthy();
  });

  it("create dialog has priority select", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-priority")).toBeTruthy();
  });

  it("create dialog has planned start date", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-planned-start")).toBeTruthy();
  });

  it("create dialog has planned end date", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    expect(screen.getByTestId("create-planned-end")).toBeTruthy();
  });

  it("cancel button closes dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    fireEvent.click(screen.getByTestId("create-cancel"));
    expect(screen.queryByTestId("create-dialog")).toBeNull();
  });

  it("submit button disabled when fields empty", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    const submit = screen.getByTestId("create-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("submit button enables when required fields filled", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    fireEvent.change(screen.getByTestId("create-program-name"), { target: { value: "Test" } });
    fireEvent.change(screen.getByTestId("create-customer-id"), { target: { value: "cid-x" } });
    fireEvent.change(screen.getByTestId("create-training-type"), { target: { value: "Sales" } });
    expect((screen.getByTestId("create-submit") as HTMLButtonElement).disabled).toBe(false);
  });

  it("submitting calls createMut.mutate", () => {
    NOOP_MUTATE.mockClear();
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    fireEvent.change(screen.getByTestId("create-program-name"), { target: { value: "Test" } });
    fireEvent.change(screen.getByTestId("create-customer-id"), { target: { value: "cid-x" } });
    fireEvent.change(screen.getByTestId("create-training-type"), { target: { value: "Sales" } });
    fireEvent.submit(screen.getByTestId("create-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });

  it("create dialog shows all delivery modes", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    const sel = screen.getByTestId("create-delivery-mode") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("onsite");
    expect(values).toContain("online");
    expect(values).toContain("hybrid");
  });

  it("create dialog shows all priorities", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-engagement-btn"));
    const sel = screen.getByTestId("create-priority") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("low");
    expect(values).toContain("medium");
    expect(values).toContain("high");
    expect(values).toContain("urgent");
  });
});

describe("TrainingCenter — filters", () => {
  beforeEach(() => { NOOP_MUTATE.mockClear(); mockAll(); });

  it("renders filter bar", () => {
    renderCenter();
    expect(screen.getByTestId("filter-bar")).toBeTruthy();
  });

  it("renders search input", () => {
    renderCenter();
    expect(screen.getByTestId("search-input")).toBeTruthy();
  });

  it("renders status select", () => {
    renderCenter();
    expect(screen.getByTestId("status-select")).toBeTruthy();
  });

  it("renders delivery mode select", () => {
    renderCenter();
    expect(screen.getByTestId("delivery-mode-select")).toBeTruthy();
  });

  it("status select has all training statuses", () => {
    renderCenter();
    const sel = screen.getByTestId("status-select") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("planned");
    expect(values).toContain("scheduled");
    expect(values).toContain("in_progress");
    expect(values).toContain("completed");
    expect(values).toContain("cancelled");
  });

  it("delivery mode select has all modes", () => {
    renderCenter();
    const sel = screen.getByTestId("delivery-mode-select") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("onsite");
    expect(values).toContain("online");
    expect(values).toContain("hybrid");
  });

  it("typing in search updates input value", () => {
    renderCenter();
    const input = screen.getByTestId("search-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "bootcamp" } });
    expect(input.value).toBe("bootcamp");
  });

  it("selecting status updates select", () => {
    renderCenter();
    const sel = screen.getByTestId("status-select") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "in_progress" } });
    expect(sel.value).toBe("in_progress");
  });

  it("selecting delivery mode updates select", () => {
    renderCenter();
    const sel = screen.getByTestId("delivery-mode-select") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "online" } });
    expect(sel.value).toBe("online");
  });
});

describe("TrainingCenter — pagination", () => {
  it("load more button appears when has_more is true", () => {
    mockAll({ listOut: LIST_WITH_MORE });
    renderCenter();
    expect(screen.getByTestId("load-more-btn")).toBeTruthy();
  });

  it("load more button hidden when no more pages", () => {
    mockAll({ listOut: LIST_OUT });
    renderCenter();
    expect(screen.queryByTestId("load-more-btn")).toBeNull();
  });

  it("clicking load more triggers refetch", () => {
    mockAll({ listOut: LIST_WITH_MORE });
    renderCenter();
    fireEvent.click(screen.getByTestId("load-more-btn"));
    expect(vi.mocked(useTrainingEngagements)).toHaveBeenCalled();
  });
});

describe("TrainingCenter — detail drawer", () => {
  beforeEach(() => mockAll());

  it("drawer hidden initially", () => {
    renderCenter();
    expect(screen.queryByTestId("detail-drawer")).toBeNull();
  });

  it("clicking row opens drawer", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("detail-drawer")).toBeTruthy();
  });

  it("drawer shows program name", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-program-name").textContent).toBe("Leadership Bootcamp");
  });

  it("drawer shows training type", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-training-type").textContent).toBe("Leadership");
  });

  it("drawer shows delivery mode", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-delivery-mode").textContent).toBe("onsite");
  });

  it("drawer shows planned start date", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-planned-start").textContent).toBe("2026-08-01");
  });

  it("drawer shows planned end date", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-planned-end").textContent).toBe("2026-08-03");
  });

  it("drawer shows estimated participants", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-estimated-participants").textContent).toBe("20");
  });

  it("drawer shows location", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-location").textContent).toBe("Mumbai");
  });

  it("drawer shows trainer id", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-trainer-id").textContent).toBe("tid-1");
  });

  it("drawer shows coordinator id", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-coordinator-id").textContent).toBe("coid-1");
  });

  it("drawer shows notes", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("drawer-notes").textContent).toBe("Priority client");
  });

  it("close button hides drawer", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("detail-drawer")).toBeNull();
  });

  it("drawer hides optional fields when null", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    expect(screen.queryByTestId("drawer-notes")).toBeNull();
    expect(screen.queryByTestId("drawer-location")).toBeNull();
    expect(screen.queryByTestId("drawer-trainer-id")).toBeNull();
  });

  it("drawer shows meeting link when present", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    expect(screen.getByTestId("drawer-meeting-link").textContent).toContain("meet.example.com");
  });

  it("completed engagement shows actual end date", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E3_COMPLETED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-3"));
    expect(screen.getByTestId("drawer-actual-end").textContent).toBe("2026-06-30");
  });

  it("completed engagement shows actual participants", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E3_COMPLETED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-3"));
    expect(screen.getByTestId("drawer-actual-participants").textContent).toBe("18");
  });
});

describe("TrainingCenter — status action buttons", () => {
  beforeEach(() => { NOOP_MUTATE.mockClear(); mockAll(); });

  it("planned engagement shows start button", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("start-btn")).toBeTruthy();
  });

  it("planned engagement shows cancel button", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("cancel-btn")).toBeTruthy();
  });

  it("planned engagement does NOT show complete button", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.queryByTestId("complete-btn")).toBeNull();
  });

  it("in_progress engagement shows complete button", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    expect(screen.getByTestId("complete-btn")).toBeTruthy();
  });

  it("in_progress engagement shows cancel button", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    expect(screen.getByTestId("cancel-btn")).toBeTruthy();
  });

  it("in_progress engagement shows NO start button", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    expect(screen.queryByTestId("start-btn")).toBeNull();
  });

  it("completed engagement shows no status actions", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E3_COMPLETED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-3"));
    expect(screen.queryByTestId("status-actions")).toBeNull();
  });

  it("cancelled engagement shows no status actions", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E4_CANCELLED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-4"));
    expect(screen.queryByTestId("status-actions")).toBeNull();
  });

  it("scheduled engagement shows start button", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E5_SCHEDULED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-5"));
    expect(screen.getByTestId("start-btn")).toBeTruthy();
  });

  it("clicking start calls startMut.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("start-btn"));
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });
});

describe("TrainingCenter — complete dialog", () => {
  beforeEach(() => {
    NOOP_MUTATE.mockClear();
    mockAll({ listOut: { ...LIST_OUT, items: [E2] } });
  });

  it("clicking complete opens complete dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    expect(screen.getByTestId("complete-dialog")).toBeTruthy();
  });

  it("complete dialog has end date field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    expect(screen.getByTestId("complete-end-date")).toBeTruthy();
  });

  it("complete dialog has participants field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    expect(screen.getByTestId("complete-participants")).toBeTruthy();
  });

  it("complete dialog has notes field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    expect(screen.getByTestId("complete-notes")).toBeTruthy();
  });

  it("complete dialog cancel button closes it", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    fireEvent.click(screen.getByTestId("complete-cancel"));
    expect(screen.queryByTestId("complete-dialog")).toBeNull();
  });

  it("submitting complete calls completeMut.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-2"));
    fireEvent.click(screen.getByTestId("complete-btn"));
    fireEvent.submit(screen.getByTestId("complete-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });
});

describe("TrainingCenter — cancel dialog", () => {
  beforeEach(() => { NOOP_MUTATE.mockClear(); mockAll(); });

  it("clicking cancel opens cancel dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("cancel-btn"));
    expect(screen.getByTestId("cancel-dialog")).toBeTruthy();
  });

  it("cancel dialog has notes field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("cancel-btn"));
    expect(screen.getByTestId("cancel-notes")).toBeTruthy();
  });

  it("cancel dialog back button closes it", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("cancel-btn"));
    fireEvent.click(screen.getByTestId("cancel-dialog-close"));
    expect(screen.queryByTestId("cancel-dialog")).toBeNull();
  });

  it("submitting cancel calls cancelMut.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("cancel-btn"));
    fireEvent.submit(screen.getByTestId("cancel-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });
});

describe("TrainingCenter — assignment dialogs", () => {
  beforeEach(() => { NOOP_MUTATE.mockClear(); mockAll(); });

  it("drawer has assign trainer button", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("assign-trainer-btn")).toBeTruthy();
  });

  it("drawer has assign coordinator button", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    expect(screen.getByTestId("assign-coordinator-btn")).toBeTruthy();
  });

  it("clicking assign trainer opens trainer dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    expect(screen.getByTestId("assign-trainer-dialog")).toBeTruthy();
  });

  it("trainer dialog has id input", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    expect(screen.getByTestId("trainer-id-input")).toBeTruthy();
  });

  it("trainer dialog cancel button closes it", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    fireEvent.click(screen.getByTestId("assign-trainer-cancel"));
    expect(screen.queryByTestId("assign-trainer-dialog")).toBeNull();
  });

  it("trainer submit disabled when id empty", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    expect((screen.getByTestId("assign-trainer-submit") as HTMLButtonElement).disabled).toBe(true);
  });

  it("trainer submit enabled when id filled", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    fireEvent.change(screen.getByTestId("trainer-id-input"), { target: { value: "tid-x" } });
    expect((screen.getByTestId("assign-trainer-submit") as HTMLButtonElement).disabled).toBe(false);
  });

  it("submitting trainer assign calls assignTrainer.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-trainer-btn"));
    fireEvent.change(screen.getByTestId("trainer-id-input"), { target: { value: "tid-x" } });
    fireEvent.submit(screen.getByTestId("assign-trainer-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });

  it("clicking assign coordinator opens coordinator dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-coordinator-btn"));
    expect(screen.getByTestId("assign-coordinator-dialog")).toBeTruthy();
  });

  it("coordinator dialog has id input", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-coordinator-btn"));
    expect(screen.getByTestId("coordinator-id-input")).toBeTruthy();
  });

  it("coordinator dialog cancel closes it", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-coordinator-btn"));
    fireEvent.click(screen.getByTestId("assign-coordinator-cancel"));
    expect(screen.queryByTestId("assign-coordinator-dialog")).toBeNull();
  });

  it("submitting coordinator assign calls assignCoord.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-1"));
    fireEvent.click(screen.getByTestId("assign-coordinator-btn"));
    fireEvent.change(screen.getByTestId("coordinator-id-input"), { target: { value: "coid-x" } });
    fireEvent.submit(screen.getByTestId("assign-coordinator-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });

  it("assignment actions visible even for completed engagement", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E3_COMPLETED] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("engagement-row-eid-3"));
    expect(screen.getByTestId("assignment-actions")).toBeTruthy();
  });
});

describe("TrainingCenter — KPI section structure", () => {
  beforeEach(() => mockAll());

  it("renders KPI section", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-section")).toBeTruthy();
  });

  it("in-progress KPI card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-in-progress")).toBeTruthy();
  });

  it("planned KPI card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-planned")).toBeTruthy();
  });

  it("completed KPI card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-completed")).toBeTruthy();
  });

  it("cancelled KPI card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-cancelled")).toBeTruthy();
  });
});

describe("TrainingCenter — singular/plural total", () => {
  it("shows singular for 1 engagement", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [E1], total: 1 } });
    renderCenter();
    expect(screen.getByTestId("engagement-total").textContent).toContain("1 engagement");
  });

  it("shows plural for more than 1", () => {
    mockAll();
    renderCenter();
    expect(screen.getByTestId("engagement-total").textContent).toContain("engagements");
  });
});
