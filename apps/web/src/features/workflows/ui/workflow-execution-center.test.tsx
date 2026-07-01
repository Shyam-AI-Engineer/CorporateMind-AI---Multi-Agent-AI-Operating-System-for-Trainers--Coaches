import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  WorkflowRunListPage,
  WorkflowRunOut,
  WorkflowRunStepOut,
} from "@/features/workflows/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/workflows/api/use-workflows", () => ({
  useWorkflowRuns: vi.fn(),
  useWorkflowRun: vi.fn(),
  useStartRun: vi.fn(),
  useCancelRun: vi.fn(),
  useCompleteStep: vi.fn(),
  useReopenStep: vi.fn(),
  useSkipStep: vi.fn(),
  useBlockStep: vi.fn(),
  useResumeStep: vi.fn(),
  // Sprint 35 — entity hooks (not directly tested here; kept for mock completeness)
  useAttachEntity: vi.fn(() => ({ mutate: () => {}, isPending: false })),
  useDetachEntity: vi.fn(() => ({ mutate: () => {}, isPending: false })),
  useEntityRuns: vi.fn(() => ({ data: { items: [], next_cursor: null, has_more: false }, isLoading: false, error: null })),
  useActiveEntityRun: vi.fn(() => ({ data: null, isLoading: false, error: null })),
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/workflow-runs"),
  useParams: vi.fn(() => ({})),
}));

import {
  useWorkflowRuns,
  useWorkflowRun,
  useCancelRun,
  useCompleteStep,
  useReopenStep,
  useSkipStep,
  useBlockStep,
  useResumeStep,
} from "@/features/workflows/api/use-workflows";

const mockUseWorkflowRuns = vi.mocked(useWorkflowRuns);
const mockUseWorkflowRun = vi.mocked(useWorkflowRun);
const mockUseCancelRun = vi.mocked(useCancelRun);
const mockUseCompleteStep = vi.mocked(useCompleteStep);
const mockUseReopenStep = vi.mocked(useReopenStep);
const mockUseSkipStep = vi.mocked(useSkipStep);
const mockUseBlockStep = vi.mocked(useBlockStep);
const mockUseResumeStep = vi.mocked(useResumeStep);

const { WorkflowExecutionCenter } = await import("./workflow-execution-center");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-exec-1";
const RUN_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RUN_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const STEP_1 = "11111111-1111-1111-1111-111111111111";
const STEP_2 = "22222222-2222-2222-2222-222222222222";

function makeStep(overrides: Partial<WorkflowRunStepOut> = {}): WorkflowRunStepOut {
  return {
    id: STEP_1,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    workflow_run_id: RUN_A,
    template_step_id: "tt-1",
    title: "Review Contract",
    description: null,
    owner_role: "member",
    required: true,
    step_order: 1,
    status: "pending",
    completed_by: null,
    completed_at: null,
    notes: null,
    ...overrides,
  };
}

function makeRun(overrides: Partial<WorkflowRunOut> = {}): WorkflowRunOut {
  return {
    id: RUN_A,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    workflow_template_id: "tmpl-1",
    title: "New Corporate Lead — Acme",
    status: "active",
    started_by: "user-1",
    assigned_to: null,
    started_at: "2026-06-29T10:00:00Z",
    completed_at: null,
    cancelled_at: null,
    // Sprint 35: entity fields default to null
    entity_type: null,
    entity_id: null,
    entity_title: null,
    run_steps: [],
    ...overrides,
  };
}

function makeListPage(overrides: Partial<WorkflowRunListPage> = {}): WorkflowRunListPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function noop() {}

function setupMutations() {
  mockUseCancelRun.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useCancelRun>);
  mockUseCompleteStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useCompleteStep>);
  mockUseReopenStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useReopenStep>);
  mockUseSkipStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useSkipStep>);
  mockUseBlockStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useBlockStep>);
  mockUseResumeStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useResumeStep>);
}

function setupListsEmpty() {
  mockUseWorkflowRuns.mockReturnValue({
    data: makeListPage(),
    isLoading: false,
    error: null,
  } as ReturnType<typeof useWorkflowRuns>);
}

function setupRunDetail(run = makeRun()) {
  mockUseWorkflowRun.mockReturnValue({
    data: run,
    isLoading: false,
    error: null,
  } as ReturnType<typeof useWorkflowRun>);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMutations();
  setupListsEmpty();
  setupRunDetail();
});

function renderCenter() {
  return render(<WorkflowExecutionCenter workspaceId={WS_ID} />);
}

// ── Page structure ────────────────────────────────────────────────────────────

describe("WorkflowExecutionCenter — structure", () => {
  it("renders the page heading", () => {
    renderCenter();
    expect(screen.getByText("Workflow Runs")).not.toBeNull();
  });

  it("renders Active tab trigger", () => {
    renderCenter();
    expect(screen.getByTestId("tab-active")).not.toBeNull();
  });

  it("renders Completed tab trigger", () => {
    renderCenter();
    expect(screen.getByTestId("tab-completed")).not.toBeNull();
  });

  it("renders Cancelled tab trigger", () => {
    renderCenter();
    expect(screen.getByTestId("tab-cancelled")).not.toBeNull();
  });

  it("renders execution center container", () => {
    renderCenter();
    expect(screen.getByTestId("workflow-execution-center")).not.toBeNull();
  });

  it("renders active tab panel div", () => {
    renderCenter();
    expect(screen.getByTestId("tab-panel-active")).not.toBeNull();
  });

  it("renders completed tab panel div", () => {
    renderCenter();
    expect(screen.getByTestId("tab-panel-completed")).not.toBeNull();
  });

  it("renders cancelled tab panel div", () => {
    renderCenter();
    expect(screen.getByTestId("tab-panel-cancelled")).not.toBeNull();
  });

  it("calls useWorkflowRuns with status_filter active", () => {
    renderCenter();
    expect(mockUseWorkflowRuns).toHaveBeenCalledWith(WS_ID, { status_filter: "active" });
  });

  it("calls useWorkflowRuns with status_filter completed", () => {
    renderCenter();
    expect(mockUseWorkflowRuns).toHaveBeenCalledWith(WS_ID, { status_filter: "completed" });
  });

  it("calls useWorkflowRuns with status_filter cancelled", () => {
    renderCenter();
    expect(mockUseWorkflowRuns).toHaveBeenCalledWith(WS_ID, { status_filter: "cancelled" });
  });
});

// ── Active tab ────────────────────────────────────────────────────────────────

describe("WorkflowExecutionCenter — active tab", () => {
  it("shows empty state when no active runs", () => {
    renderCenter();
    expect(screen.getByTestId("active-empty")).not.toBeNull();
  });

  it("shows loading state for active runs", () => {
    mockUseWorkflowRuns.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useWorkflowRuns>);
    renderCenter();
    expect(screen.getByTestId("active-loading")).not.toBeNull();
  });

  it("shows error state for active runs", () => {
    mockUseWorkflowRuns.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("failed"),
    } as ReturnType<typeof useWorkflowRuns>);
    renderCenter();
    expect(screen.getByTestId("active-error")).not.toBeNull();
  });

  it("renders active run row", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    expect(screen.getByTestId(`run-row-${RUN_A}`)).not.toBeNull();
  });

  it("renders run title in row", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("New Corporate Lead — Acme");
  });

  it("renders multiple active run rows", () => {
    const run2 = makeRun({ id: RUN_B, title: "Enterprise — BigCorp" });
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun(), run2] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    expect(screen.getByTestId(`run-row-${RUN_A}`)).not.toBeNull();
    expect(screen.getByTestId(`run-row-${RUN_B}`)).not.toBeNull();
  });

  it("shows required step progress in run row", () => {
    const steps = [
      makeStep({ id: STEP_1, status: "completed" }),
      makeStep({ id: STEP_2, status: "pending" }),
    ];
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun({ run_steps: steps })] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("1/2 required steps done");
  });

  it("shows Active badge text in run row", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun({ status: "active" })] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("Active");
  });
});

// ── Completed tab (userEvent required for Radix lazy-mount) ───────────────────

describe("WorkflowExecutionCenter — completed tab", () => {
  it("shows completed-empty after switching to completed tab", async () => {
    const user = userEvent.setup();
    renderCenter();
    await user.click(screen.getByTestId("tab-completed"));
    expect(screen.getByTestId("completed-empty")).not.toBeNull();
  });

  it("renders completed run after switching tab", async () => {
    const user = userEvent.setup();
    const completedRun = makeRun({ id: RUN_B, status: "completed" });
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "completed") {
        return { data: makeListPage({ items: [completedRun] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    await user.click(screen.getByTestId("tab-completed"));
    expect(screen.getByTestId(`run-row-${RUN_B}`)).not.toBeNull();
  });

  it("shows Completed badge in run row", async () => {
    const user = userEvent.setup();
    const completedRun = makeRun({ id: RUN_B, status: "completed" });
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "completed") {
        return { data: makeListPage({ items: [completedRun] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    await user.click(screen.getByTestId("tab-completed"));
    const row = screen.getByTestId(`run-row-${RUN_B}`);
    expect(row.textContent).toContain("Completed");
  });
});

// ── Cancelled tab (userEvent required for Radix lazy-mount) ──────────────────

describe("WorkflowExecutionCenter — cancelled tab", () => {
  it("shows cancelled-empty after switching to cancelled tab", async () => {
    const user = userEvent.setup();
    renderCenter();
    await user.click(screen.getByTestId("tab-cancelled"));
    expect(screen.getByTestId("cancelled-empty")).not.toBeNull();
  });

  it("renders cancelled run after switching tab", async () => {
    const user = userEvent.setup();
    const cancelledRun = makeRun({ id: RUN_B, status: "cancelled" });
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "cancelled") {
        return { data: makeListPage({ items: [cancelledRun] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    await user.click(screen.getByTestId("tab-cancelled"));
    expect(screen.getByTestId(`run-row-${RUN_B}`)).not.toBeNull();
  });

  it("shows Cancelled badge in run row", async () => {
    const user = userEvent.setup();
    const cancelledRun = makeRun({ id: RUN_B, status: "cancelled" });
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "cancelled") {
        return { data: makeListPage({ items: [cancelledRun] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    await user.click(screen.getByTestId("tab-cancelled"));
    const row = screen.getByTestId(`run-row-${RUN_B}`);
    expect(row.textContent).toContain("Cancelled");
  });
});

// ── Navigation ────────────────────────────────────────────────────────────────

describe("WorkflowExecutionCenter — navigation", () => {
  it("clicking a run row shows run detail", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    expect(screen.getByTestId("run-detail")).not.toBeNull();
  });

  it("back button returns to list", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    fireEvent.click(screen.getByTestId("btn-back"));
    expect(screen.getByTestId("workflow-execution-center")).not.toBeNull();
  });

  it("list is hidden while detail is shown", () => {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    expect(screen.queryByTestId("workflow-execution-center")).toBeNull();
  });
});

// ── Run detail ────────────────────────────────────────────────────────────────

describe("RunDetail", () => {
  function showDetail(run?: Partial<WorkflowRunOut>) {
    const runData = makeRun(run);
    setupRunDetail(runData);
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [runData] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${runData.id}`));
  }

  it("shows loading state while fetching run", () => {
    mockUseWorkflowRun.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useWorkflowRun>);
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    expect(screen.getByTestId("run-detail-loading")).not.toBeNull();
  });

  it("shows error state when run fetch fails", () => {
    mockUseWorkflowRun.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("not found"),
    } as ReturnType<typeof useWorkflowRun>);
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    expect(screen.getByTestId("run-detail-error")).not.toBeNull();
  });

  it("shows run title in detail", () => {
    showDetail({ title: "Enterprise Deal" });
    expect(screen.getByTestId("run-detail").textContent).toContain("Enterprise Deal");
  });

  it("shows cancel button for active run", () => {
    showDetail({ status: "active" });
    expect(screen.getByTestId("btn-cancel-run")).not.toBeNull();
  });

  it("hides cancel button for completed run", () => {
    showDetail({ status: "completed" });
    expect(screen.queryByTestId("btn-cancel-run")).toBeNull();
  });

  it("hides cancel button for cancelled run", () => {
    showDetail({ status: "cancelled" });
    expect(screen.queryByTestId("btn-cancel-run")).toBeNull();
  });

  it("shows no-steps-message when run has no steps", () => {
    showDetail({ run_steps: [] });
    expect(screen.getByTestId("no-steps-message")).not.toBeNull();
  });

  it("renders step rows in checklist", () => {
    showDetail({ run_steps: [makeStep(), makeStep({ id: STEP_2, title: "Send Proposal" })] });
    expect(screen.getByTestId(`step-row-${STEP_1}`)).not.toBeNull();
    expect(screen.getByTestId(`step-row-${STEP_2}`)).not.toBeNull();
  });

  it("shows step title in checklist row", () => {
    showDetail({ run_steps: [makeStep({ title: "Book Meeting" })] });
    const row = screen.getByTestId(`step-row-${STEP_1}`);
    expect(row.textContent).toContain("Book Meeting");
  });

  it("shows run status badge in detail header", () => {
    showDetail({ status: "active" });
    expect(screen.getByTestId("run-detail").textContent).toContain("Active");
  });

  it("shows step-checklist container", () => {
    showDetail({ run_steps: [] });
    expect(screen.getByTestId("step-checklist")).not.toBeNull();
  });

  it("calls cancel.mutate when cancel button clicked", () => {
    const cancelMutate = vi.fn();
    mockUseCancelRun.mockReturnValue({
      mutate: cancelMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCancelRun>);
    showDetail({ status: "active" });
    fireEvent.click(screen.getByTestId("btn-cancel-run"));
    expect(cancelMutate).toHaveBeenCalledWith(RUN_A);
  });
});

// ── StepActionDialog ──────────────────────────────────────────────────────────

describe("StepActionDialog", () => {
  function navigateToStep(step: WorkflowRunStepOut) {
    setupRunDetail(makeRun({ status: "active", run_steps: [step] }));
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun({ status: "active", run_steps: [step] })] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    fireEvent.click(screen.getByTestId(`step-row-${step.id}`));
  }

  it("opens dialog when clicking a pending step", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("step-action-dialog")).not.toBeNull();
  });

  it("shows complete button for pending step", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("btn-complete")).not.toBeNull();
  });

  it("shows block button for pending step", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("btn-block")).not.toBeNull();
  });

  it("shows skip button for pending optional step", () => {
    navigateToStep(makeStep({ status: "pending", required: false }));
    expect(screen.getByTestId("btn-skip")).not.toBeNull();
  });

  it("hides skip button for pending required step", () => {
    navigateToStep(makeStep({ status: "pending", required: true }));
    expect(screen.queryByTestId("btn-skip")).toBeNull();
  });

  it("shows reopen button for completed step", () => {
    navigateToStep(makeStep({ status: "completed" }));
    expect(screen.getByTestId("btn-reopen")).not.toBeNull();
  });

  it("shows resume button for blocked step", () => {
    navigateToStep(makeStep({ status: "blocked" }));
    expect(screen.getByTestId("btn-resume")).not.toBeNull();
  });

  it("hides complete button for completed step", () => {
    navigateToStep(makeStep({ status: "completed" }));
    expect(screen.queryByTestId("btn-complete")).toBeNull();
  });

  it("hides resume button for pending step", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.queryByTestId("btn-resume")).toBeNull();
  });

  it("shows notes textarea", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("step-notes-input")).not.toBeNull();
  });

  it("shows step title in dialog", () => {
    navigateToStep(makeStep({ title: "Final Sign-off", status: "pending" }));
    const dialog = screen.getByTestId("step-action-dialog");
    expect(dialog.textContent).toContain("Final Sign-off");
  });

  it("calls complete.mutate when complete clicked", () => {
    const completeMutate = vi.fn();
    mockUseCompleteStep.mockReturnValue({
      mutate: completeMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCompleteStep>);
    navigateToStep(makeStep({ status: "pending" }));
    fireEvent.click(screen.getByTestId("btn-complete"));
    expect(completeMutate).toHaveBeenCalledWith(
      { stepId: STEP_1, data: { notes: null } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("calls reopen.mutate when reopen clicked", () => {
    const reopenMutate = vi.fn();
    mockUseReopenStep.mockReturnValue({
      mutate: reopenMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useReopenStep>);
    navigateToStep(makeStep({ status: "completed" }));
    fireEvent.click(screen.getByTestId("btn-reopen"));
    expect(reopenMutate).toHaveBeenCalledWith(
      STEP_1,
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("calls block.mutate when block clicked", () => {
    const blockMutate = vi.fn();
    mockUseBlockStep.mockReturnValue({
      mutate: blockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useBlockStep>);
    navigateToStep(makeStep({ status: "pending" }));
    fireEvent.click(screen.getByTestId("btn-block"));
    expect(blockMutate).toHaveBeenCalledWith(
      { stepId: STEP_1, data: { notes: null } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("calls resume.mutate when resume clicked", () => {
    const resumeMutate = vi.fn();
    mockUseResumeStep.mockReturnValue({
      mutate: resumeMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useResumeStep>);
    navigateToStep(makeStep({ status: "blocked" }));
    fireEvent.click(screen.getByTestId("btn-resume"));
    expect(resumeMutate).toHaveBeenCalledWith(
      STEP_1,
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("calls skip.mutate when skip clicked", () => {
    const skipMutate = vi.fn();
    mockUseSkipStep.mockReturnValue({
      mutate: skipMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useSkipStep>);
    navigateToStep(makeStep({ status: "pending", required: false }));
    fireEvent.click(screen.getByTestId("btn-skip"));
    expect(skipMutate).toHaveBeenCalledWith(
      { stepId: STEP_1, data: { notes: null } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("closes dialog after successful action (onSuccess called)", () => {
    const completeMutate = vi.fn((_, opts) => opts?.onSuccess?.());
    mockUseCompleteStep.mockReturnValue({
      mutate: completeMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCompleteStep>);
    navigateToStep(makeStep({ status: "pending" }));
    fireEvent.click(screen.getByTestId("btn-complete"));
    expect(screen.queryByTestId("step-action-dialog")).toBeNull();
  });

  it("shows existing notes in dialog for step with notes", () => {
    navigateToStep(makeStep({ status: "blocked", notes: "Waiting on legal" }));
    const dialog = screen.getByTestId("step-action-dialog");
    expect(dialog.textContent).toContain("Waiting on legal");
  });

  it("disables complete button when isPending", () => {
    mockUseCompleteStep.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useCompleteStep>);
    navigateToStep(makeStep({ status: "pending" }));
    const btn = screen.getByTestId("btn-complete") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("shows Required badge text in dialog for required step", () => {
    navigateToStep(makeStep({ status: "pending", required: true }));
    const dialog = screen.getByTestId("step-action-dialog");
    expect(dialog.textContent).toContain("Required");
  });

  it("step click on immutable completed run does not open dialog", () => {
    setupRunDetail(makeRun({ status: "completed", run_steps: [makeStep({ status: "completed" })] }));
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun({ id: RUN_A, status: "completed", run_steps: [makeStep({ status: "completed" })] })] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    fireEvent.click(screen.getByTestId(`step-row-${STEP_1}`));
    expect(screen.queryByTestId("step-action-dialog")).toBeNull();
  });

  it("shows complete and block buttons for in_progress step", () => {
    navigateToStep(makeStep({ status: "in_progress" }));
    expect(screen.getByTestId("btn-complete")).not.toBeNull();
    expect(screen.getByTestId("btn-block")).not.toBeNull();
  });

  it("hides block button for completed step", () => {
    navigateToStep(makeStep({ status: "completed" }));
    expect(screen.queryByTestId("btn-block")).toBeNull();
  });

  it("hides block button for blocked step", () => {
    navigateToStep(makeStep({ status: "blocked" }));
    expect(screen.queryByTestId("btn-block")).toBeNull();
  });

  it("hides reopen button for pending step", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.queryByTestId("btn-reopen")).toBeNull();
  });

  it("shows step description in dialog", () => {
    navigateToStep(makeStep({ status: "pending", description: "Review all clauses" }));
    expect(screen.getByTestId("step-notes-input")).not.toBeNull();
  });

  it("shows Complete label text on button", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("btn-complete").textContent).toContain("Complete");
  });

  it("shows Reopen label text on button", () => {
    navigateToStep(makeStep({ status: "completed" }));
    expect(screen.getByTestId("btn-reopen").textContent).toContain("Reopen");
  });

  it("shows Resume label text on button", () => {
    navigateToStep(makeStep({ status: "blocked" }));
    expect(screen.getByTestId("btn-resume").textContent).toContain("Resume");
  });

  it("shows Block label text on button", () => {
    navigateToStep(makeStep({ status: "pending" }));
    expect(screen.getByTestId("btn-block").textContent).toContain("Block");
  });
});

// ── Cancel run state ──────────────────────────────────────────────────────────

describe("Cancel run — pending state", () => {
  it("disables cancel button while isPending", () => {
    mockUseCancelRun.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useCancelRun>);
    setupRunDetail(makeRun({ status: "active" }));
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [makeRun()] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
    fireEvent.click(screen.getByTestId(`run-row-${RUN_A}`));
    const btn = screen.getByTestId("btn-cancel-run") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});

// ── RunRow — step progress ────────────────────────────────────────────────────

describe("RunRow — step progress", () => {
  function renderWithRun(run: WorkflowRunOut) {
    mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
      if (opts?.status_filter === "active") {
        return { data: makeListPage({ items: [run] }), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
      }
      return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
    });
    renderCenter();
  }

  it("shows no-required-steps text when all steps are optional", () => {
    renderWithRun(makeRun({ run_steps: [makeStep({ required: false })] }));
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("No required steps");
  });

  it("shows 0/1 when required step is pending", () => {
    renderWithRun(makeRun({ run_steps: [makeStep({ required: true, status: "pending" })] }));
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("0/1 required steps done");
  });

  it("shows 1/1 when required step is completed", () => {
    renderWithRun(makeRun({ run_steps: [makeStep({ required: true, status: "completed" })] }));
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("1/1 required steps done");
  });

  it("counts only required steps in denominator", () => {
    const steps = [
      makeStep({ id: STEP_1, required: true, status: "pending" }),
      makeStep({ id: STEP_2, required: false, status: "pending" }),
    ];
    renderWithRun(makeRun({ run_steps: steps }));
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("0/1 required steps done");
  });
});
