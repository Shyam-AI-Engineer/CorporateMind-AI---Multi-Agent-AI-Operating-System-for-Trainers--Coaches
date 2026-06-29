import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { OperationsCenter } from "./operations-center";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-123" }),
}));

vi.mock("@/features/operations/api/use-operations", () => ({
  useOperationsTasks: vi.fn(),
  useOperationsWorkload: vi.fn(),
  useCreateTask: vi.fn(),
  useUpdateTask: vi.fn(),
  useDeleteTask: vi.fn(),
}));

import {
  useOperationsTasks,
  useOperationsWorkload,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
} from "@/features/operations/api/use-operations";

// ── Factories ─────────────────────────────────────────────────────────────────

const makeTask = (overrides: Partial<Record<string, unknown>> = {}) => ({
  id: "task-1",
  workspace_id: "ws-123",
  title: "Test Task",
  description: null,
  priority: "medium",
  status: "backlog",
  assignee: null,
  due_date: null,
  completed_at: null,
  source_type: null,
  source_id: null,
  created_by: "user-1",
  created_at: "2026-06-27T10:00:00Z",
  updated_at: "2026-06-27T10:00:00Z",
  ...overrides,
});

const makeGrouped = (overrides: Partial<Record<string, unknown>> = {}) => ({
  backlog: [],
  in_progress: [],
  blocked: [],
  completed: [],
  total: 0,
  ...overrides,
});

const makeWorkload = (overrides: Partial<Record<string, unknown>> = {}) => ({
  total_open: 0,
  overdue: 0,
  completed_today: 0,
  blocked: 0,
  by_priority: {},
  by_assignee: {},
  ...overrides,
});

// ── Setup ─────────────────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function setupMocks({
  tasksData = makeGrouped(),
  workloadData = makeWorkload(),
  tasksLoading = false,
  workloadLoading = false,
  tasksError = false,
  workloadError = false,
} = {}) {
  vi.mocked(useOperationsTasks).mockReturnValue({
    data: tasksData,
    isLoading: tasksLoading,
    isError: tasksError,
  } as ReturnType<typeof useOperationsTasks>);

  vi.mocked(useOperationsWorkload).mockReturnValue({
    data: workloadData,
    isLoading: workloadLoading,
    isError: workloadError,
  } as ReturnType<typeof useOperationsWorkload>);

  vi.mocked(useCreateTask).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useCreateTask>);

  vi.mocked(useUpdateTask).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateTask>);

  vi.mocked(useDeleteTask).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteTask>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Loading state ─────────────────────────────────────────────────────────────

describe("loading state", () => {
  it("renders skeleton when tasks loading", () => {
    setupMocks({ tasksLoading: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-skeleton")).not.toBeNull();
  });

  it("renders skeleton when workload loading", () => {
    setupMocks({ workloadLoading: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-skeleton")).not.toBeNull();
  });

  it("does not render main content while loading", () => {
    setupMocks({ tasksLoading: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-center")).toBeNull();
  });
});

// ── Error state ───────────────────────────────────────────────────────────────

describe("error state", () => {
  it("renders error message on tasks error", () => {
    setupMocks({ tasksError: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-error")).not.toBeNull();
  });

  it("renders error message on workload error", () => {
    setupMocks({ workloadError: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-error")).not.toBeNull();
  });

  it("does not render main content on error", () => {
    setupMocks({ tasksError: true });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-center")).toBeNull();
  });
});

// ── Main container ────────────────────────────────────────────────────────────

describe("main container", () => {
  it("renders operations-center root on success", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("operations-center")).not.toBeNull();
  });

  it("renders new task button", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("new-task-btn")).not.toBeNull();
  });
});

// ── KPI row ───────────────────────────────────────────────────────────────────

describe("KPI row", () => {
  it("renders kpi-row section", () => {
    setupMocks({ workloadData: makeWorkload({ total_open: 5 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-row")).not.toBeNull();
  });

  it("shows correct total_open", () => {
    setupMocks({ workloadData: makeWorkload({ total_open: 7 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-open")?.textContent).toContain("7");
  });

  it("shows correct overdue count", () => {
    setupMocks({ workloadData: makeWorkload({ overdue: 3 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-overdue")?.textContent).toContain("3");
  });

  it("shows correct completed_today count", () => {
    setupMocks({ workloadData: makeWorkload({ completed_today: 4 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-completed-today")?.textContent).toContain("4");
  });

  it("shows correct blocked count", () => {
    setupMocks({ workloadData: makeWorkload({ blocked: 2 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-blocked")?.textContent).toContain("2");
  });

  it("all four KPI cards present", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kpi-open")).not.toBeNull();
    expect(screen.queryByTestId("kpi-overdue")).not.toBeNull();
    expect(screen.queryByTestId("kpi-completed-today")).not.toBeNull();
    expect(screen.queryByTestId("kpi-blocked")).not.toBeNull();
  });
});

// ── Kanban board ──────────────────────────────────────────────────────────────

describe("Kanban board", () => {
  it("renders kanban-board section", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kanban-board")).not.toBeNull();
  });

  it("renders all four columns", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kanban-backlog")).not.toBeNull();
    expect(screen.queryByTestId("kanban-in-progress")).not.toBeNull();
    expect(screen.queryByTestId("kanban-blocked")).not.toBeNull();
    expect(screen.queryByTestId("kanban-completed")).not.toBeNull();
  });

  it("renders empty state in columns with no tasks", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kanban-backlog-empty")).not.toBeNull();
  });

  it("renders task card in backlog column", () => {
    const task = makeTask({ id: "t1", status: "backlog" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-card-t1")).not.toBeNull();
  });

  it("renders task in in-progress column", () => {
    const task = makeTask({ id: "t2", status: "in_progress" });
    setupMocks({ tasksData: makeGrouped({ in_progress: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-card-t2")).not.toBeNull();
  });

  it("renders task in blocked column", () => {
    const task = makeTask({ id: "t3", status: "blocked" });
    setupMocks({ tasksData: makeGrouped({ blocked: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-card-t3")).not.toBeNull();
  });

  it("renders task in completed column", () => {
    const task = makeTask({ id: "t4", status: "completed" });
    setupMocks({ tasksData: makeGrouped({ completed: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-card-t4")).not.toBeNull();
  });

  it("shows task title in card", () => {
    const task = makeTask({ id: "t5", title: "My Important Task" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-card-t5")?.textContent).toContain("My Important Task");
  });

  it("shows task priority badge", () => {
    const task = makeTask({ id: "t6", priority: "high" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-priority-t6")).not.toBeNull();
  });

  it("shows due date on task card", () => {
    const task = makeTask({ id: "t7", due_date: "2026-07-01" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-due-t7")).not.toBeNull();
  });

  it("shows assignee on task card", () => {
    const task = makeTask({ id: "t8", assignee: "alice" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("task-assignee-t8")?.textContent).toContain("alice");
  });

  it("does not show empty state when tasks present", () => {
    const task = makeTask({ id: "t-full" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("kanban-backlog-empty")).toBeNull();
  });
});

// ── Calendar section ──────────────────────────────────────────────────────────

describe("calendar section", () => {
  it("renders due-calendar section", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("due-calendar")).not.toBeNull();
  });

  it("shows empty state when no due dates", () => {
    setupMocks({ tasksData: makeGrouped({ backlog: [makeTask()], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("calendar-empty")).not.toBeNull();
  });

  it("shows calendar item for task with due date", () => {
    const task = makeTask({ id: "t9", due_date: "2026-07-15", status: "backlog" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("calendar-item-0")).not.toBeNull();
  });

  it("excludes completed tasks from calendar", () => {
    const task = makeTask({ id: "t10", due_date: "2026-07-15", status: "completed" });
    setupMocks({ tasksData: makeGrouped({ completed: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("calendar-item-0")).toBeNull();
  });

  it("shows task title in calendar item", () => {
    const task = makeTask({ id: "t11", due_date: "2026-07-15", title: "Cal Task" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("calendar-item-0")?.textContent).toContain("Cal Task");
  });
});

// ── Workload section ──────────────────────────────────────────────────────────

describe("workload section", () => {
  it("renders workload-section", () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-section")).not.toBeNull();
  });

  it("shows empty priority state when no breakdown", () => {
    setupMocks({ workloadData: makeWorkload({ by_priority: {} }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-priority-empty")).not.toBeNull();
  });

  it("shows priority breakdown when data present", () => {
    setupMocks({
      workloadData: makeWorkload({ by_priority: { high: 2, medium: 1 } }),
    });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-priority")).not.toBeNull();
  });

  it("shows empty assignee state when no breakdown", () => {
    setupMocks({ workloadData: makeWorkload({ by_assignee: {} }) });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-assignee-empty")).not.toBeNull();
  });

  it("shows assignee breakdown when data present", () => {
    setupMocks({
      workloadData: makeWorkload({ by_assignee: { alice: 3 } }),
    });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-assignee")).not.toBeNull();
  });

  it("shows priority counts in breakdown", () => {
    setupMocks({
      workloadData: makeWorkload({ by_priority: { high: 4 } }),
    });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-priority")?.textContent).toContain("4");
  });

  it("shows assignee counts in breakdown", () => {
    setupMocks({
      workloadData: makeWorkload({ by_assignee: { bob: 5 } }),
    });
    render(<OperationsCenter />, { wrapper });
    expect(screen.queryByTestId("workload-assignee")?.textContent).toContain("5");
  });
});

// ── Create task dialog ────────────────────────────────────────────────────────

describe("create task dialog", () => {
  it("opens dialog when new task button clicked", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("create-task-form")).not.toBeNull();
    });
  });

  it("shows title input in create form", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-title-input")).not.toBeNull();
    });
  });

  it("shows priority select in create form", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-priority-select")).not.toBeNull();
    });
  });

  it("shows assignee input in create form", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-assignee-input")).not.toBeNull();
    });
  });

  it("shows due date input in create form", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-due-date-input")).not.toBeNull();
    });
  });

  it("submit button disabled when title empty", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      const btn = screen.queryByTestId("create-task-submit") as HTMLButtonElement | null;
      expect(btn?.disabled).toBe(true);
    });
  });

  it("submit button enabled when title filled", async () => {
    setupMocks();
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-title-input")).not.toBeNull();
    });
    fireEvent.change(screen.getByTestId("task-title-input"), {
      target: { value: "New task title" },
    });
    const btn = screen.queryByTestId("create-task-submit") as HTMLButtonElement | null;
    expect(btn?.disabled).toBe(false);
  });

  it("calls create mutate on submit", async () => {
    const mutateFn = vi.fn();
    setupMocks();
    vi.mocked(useCreateTask).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useCreateTask>);
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => expect(screen.queryByTestId("create-task-form")).not.toBeNull());

    fireEvent.change(screen.getByTestId("task-title-input"), {
      target: { value: "My new task" },
    });
    fireEvent.submit(screen.getByTestId("create-task-form"));

    await waitFor(() => {
      expect(mutateFn).toHaveBeenCalled();
    });
  });

  it("mutate called with correct title", async () => {
    const mutateFn = vi.fn();
    setupMocks();
    vi.mocked(useCreateTask).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof useCreateTask>);
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("new-task-btn"));
    await waitFor(() => expect(screen.queryByTestId("create-task-form")).not.toBeNull());

    fireEvent.change(screen.getByTestId("task-title-input"), {
      target: { value: "Specific Title" },
    });
    fireEvent.submit(screen.getByTestId("create-task-form"));

    await waitFor(() => {
      const [callArg] = mutateFn.mock.calls[0] ?? [];
      expect(callArg?.title).toBe("Specific Title");
    });
  });
});

// ── Task detail dialog ────────────────────────────────────────────────────────

describe("task detail dialog", () => {
  it("opens task detail when card clicked", async () => {
    const task = makeTask({ id: "t-detail", title: "Detail Task" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-detail"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-detail-dialog")).not.toBeNull();
    });
  });

  it("shows task title in detail dialog", async () => {
    const task = makeTask({ id: "t-dtl2", title: "My Detail Task" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl2"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-detail-title")?.textContent).toContain("My Detail Task");
    });
  });

  it("shows mark complete button for non-completed task", async () => {
    const task = makeTask({ id: "t-dtl3", status: "backlog" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl3"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-complete-btn")).not.toBeNull();
    });
  });

  it("does not show mark complete for completed task", async () => {
    const task = makeTask({ id: "t-dtl4", status: "completed" });
    setupMocks({ tasksData: makeGrouped({ completed: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl4"));
    await waitFor(() => {
      // Give the dialog time to appear
      expect(screen.queryByTestId("task-detail-title")).not.toBeNull();
    });
    expect(screen.queryByTestId("task-complete-btn")).toBeNull();
  });

  it("shows delete button", async () => {
    const task = makeTask({ id: "t-dtl5" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl5"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-delete-btn")).not.toBeNull();
    });
  });

  it("calls delete mutate when delete clicked", async () => {
    const deleteMutate = vi.fn();
    const task = makeTask({ id: "t-del1" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    vi.mocked(useDeleteTask).mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDeleteTask>);
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-del1"));
    await waitFor(() => expect(screen.queryByTestId("task-delete-btn")).not.toBeNull());
    fireEvent.click(screen.getByTestId("task-delete-btn"));
    expect(deleteMutate).toHaveBeenCalledWith("t-del1");
  });

  it("shows description when present", async () => {
    const task = makeTask({ id: "t-dtl6", description: "Some description text" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl6"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-detail-description")?.textContent).toContain("Some description text");
    });
  });

  it("shows start button for backlog task", async () => {
    const task = makeTask({ id: "t-dtl7", status: "backlog" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-dtl7"));
    await waitFor(() => {
      expect(screen.queryByTestId("task-start-btn")).not.toBeNull();
    });
  });

  it("calls update mutate when complete clicked", async () => {
    const updateMutate = vi.fn();
    const task = makeTask({ id: "t-upd1", status: "backlog" });
    setupMocks({ tasksData: makeGrouped({ backlog: [task], total: 1 }) });
    vi.mocked(useUpdateTask).mockReturnValue({
      mutate: updateMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useUpdateTask>);
    render(<OperationsCenter />, { wrapper });
    fireEvent.click(screen.getByTestId("task-card-t-upd1"));
    await waitFor(() => expect(screen.queryByTestId("task-complete-btn")).not.toBeNull());
    fireEvent.click(screen.getByTestId("task-complete-btn"));
    expect(updateMutate).toHaveBeenCalled();
    const [callArg] = updateMutate.mock.calls[0] ?? [];
    expect(callArg?.data?.status).toBe("completed");
  });
});
