import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  EntityRunListPage,
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
  useAttachEntity: vi.fn(),
  useDetachEntity: vi.fn(),
  useEntityRuns: vi.fn(),
  useActiveEntityRun: vi.fn(),
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
  useAttachEntity,
  useDetachEntity,
  useEntityRuns,
} from "@/features/workflows/api/use-workflows";

const mockUseWorkflowRuns = vi.mocked(useWorkflowRuns);
const mockUseWorkflowRun = vi.mocked(useWorkflowRun);
const mockUseCancelRun = vi.mocked(useCancelRun);
const mockUseCompleteStep = vi.mocked(useCompleteStep);
const mockUseReopenStep = vi.mocked(useReopenStep);
const mockUseSkipStep = vi.mocked(useSkipStep);
const mockUseBlockStep = vi.mocked(useBlockStep);
const mockUseResumeStep = vi.mocked(useResumeStep);
const mockUseAttachEntity = vi.mocked(useAttachEntity);
const mockUseDetachEntity = vi.mocked(useDetachEntity);
const mockUseEntityRuns = vi.mocked(useEntityRuns);

const { WorkflowExecutionCenter } = await import("./workflow-execution-center");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-entity-1";
const RUN_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RUN_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const RUN_C = "cccccccc-cccc-cccc-cccc-cccccccccccc";
const STEP_1 = "11111111-1111-1111-1111-111111111111";
const ENTITY_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";

function makeStep(overrides: Partial<WorkflowRunStepOut> = {}): WorkflowRunStepOut {
  return {
    id: STEP_1,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    workflow_run_id: RUN_A,
    template_step_id: null,
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
    started_at: "2026-06-30T10:00:00Z",
    completed_at: null,
    cancelled_at: null,
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

function makeEntityPage(overrides: Partial<EntityRunListPage> = {}): EntityRunListPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function noop() {}

// ── Setup helpers ─────────────────────────────────────────────────────────────

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
  mockUseAttachEntity.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useAttachEntity>);
  mockUseDetachEntity.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useDetachEntity>);
}

function setupEntityRuns(items: WorkflowRunOut[] = [], loading = false) {
  mockUseEntityRuns.mockReturnValue({
    data: loading ? undefined : makeEntityPage({ items }),
    isLoading: loading,
    error: null,
  } as ReturnType<typeof useEntityRuns>);
}

function setupRunDetail(run: WorkflowRunOut) {
  mockUseWorkflowRun.mockReturnValue({
    data: run,
    isLoading: false,
    error: null,
  } as ReturnType<typeof useWorkflowRun>);
}

function setupListWithRun(run: WorkflowRunOut) {
  mockUseWorkflowRuns.mockImplementation((_ws, opts) => {
    if (opts?.status_filter === "active") {
      return {
        data: makeListPage({ items: [run] }),
        isLoading: false,
        error: null,
      } as ReturnType<typeof useWorkflowRuns>;
    }
    return { data: makeListPage(), isLoading: false, error: null } as ReturnType<typeof useWorkflowRuns>;
  });
}

function setupEmptyLists() {
  mockUseWorkflowRuns.mockReturnValue({
    data: makeListPage(),
    isLoading: false,
    error: null,
  } as ReturnType<typeof useWorkflowRuns>);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMutations();
  setupEmptyLists();
  setupEntityRuns([]);
});

function renderCenter() {
  return render(<WorkflowExecutionCenter workspaceId={WS_ID} />);
}

function navigateToDetail(run: WorkflowRunOut) {
  setupRunDetail(run);
  setupListWithRun(run);
  renderCenter();
  fireEvent.click(screen.getByTestId(`run-row-${run.id}`));
}

// ── RunRow — entity fields in list ────────────────────────────────────────────

describe("RunRow — Sprint 35 entity fields", () => {
  it("shows entity_type badge in run row when entity is attached", () => {
    const run = makeRun({ entity_type: "lead", entity_id: ENTITY_ID, entity_title: "Acme Corp" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("lead");
  });

  it("does not show entity badge in run row when no entity", () => {
    const run = makeRun({ entity_type: null });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).not.toContain("lead");
    expect(row.textContent).not.toContain("proposal");
  });

  it("shows entity_title in run row subtitle when entity is attached", () => {
    const run = makeRun({ entity_type: "proposal", entity_id: ENTITY_ID, entity_title: "Acme Training Deal" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("Acme Training Deal");
  });

  it("does not show entity title in subtitle when no entity", () => {
    const run = makeRun({ entity_type: null, entity_title: null });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).not.toContain("Acme Training Deal");
  });

  it("shows campaign entity type badge text in run row", () => {
    const run = makeRun({ entity_type: "campaign", entity_id: ENTITY_ID, entity_title: "Q3 Outreach" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("campaign");
  });

  it("shows customer entity type badge text in run row", () => {
    const run = makeRun({ entity_type: "customer", entity_id: ENTITY_ID, entity_title: "Big Co" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("customer");
  });

  it("shows training entity type badge text in run row", () => {
    const run = makeRun({ entity_type: "training", entity_id: ENTITY_ID, entity_title: "Leadership Boot" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("training");
  });

  it("shows other entity type badge text in run row", () => {
    const run = makeRun({ entity_type: "other", entity_id: ENTITY_ID, entity_title: "Misc entity" });
    setupListWithRun(run);
    renderCenter();
    const row = screen.getByTestId(`run-row-${RUN_A}`);
    expect(row.textContent).toContain("other");
  });
});

// ── BusinessContextSection — no entity attached ───────────────────────────────

describe("BusinessContextSection — no entity", () => {
  it("renders business-context-section in run detail", () => {
    navigateToDetail(makeRun());
    expect(screen.getByTestId("business-context-section")).not.toBeNull();
  });

  it("shows Business Context heading", () => {
    navigateToDetail(makeRun());
    const section = screen.getByTestId("business-context-section");
    expect(section.textContent).toContain("Business Context");
  });

  it("shows no-entity placeholder text", () => {
    navigateToDetail(makeRun());
    const section = screen.getByTestId("business-context-section");
    expect(section.textContent).toContain("No entity linked to this run");
  });

  it("shows btn-attach-entity when run is active and no entity", () => {
    navigateToDetail(makeRun({ status: "active", entity_type: null }));
    expect(screen.getByTestId("btn-attach-entity")).not.toBeNull();
  });

  it("shows btn-attach-entity when run is pending and no entity", () => {
    navigateToDetail(makeRun({ status: "pending", entity_type: null }));
    expect(screen.getByTestId("btn-attach-entity")).not.toBeNull();
  });

  it("hides btn-attach-entity when run is completed", () => {
    navigateToDetail(makeRun({ status: "completed", entity_type: null }));
    expect(screen.queryByTestId("btn-attach-entity")).toBeNull();
  });

  it("hides btn-attach-entity when run is cancelled", () => {
    navigateToDetail(makeRun({ status: "cancelled", entity_type: null }));
    expect(screen.queryByTestId("btn-attach-entity")).toBeNull();
  });

  it("hides entity-type-badge when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null }));
    expect(screen.queryByTestId("entity-type-badge")).toBeNull();
  });

  it("hides entity-title-text when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null }));
    expect(screen.queryByTestId("entity-title-text")).toBeNull();
  });

  it("hides btn-open-entity when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null }));
    expect(screen.queryByTestId("btn-open-entity")).toBeNull();
  });

  it("hides btn-detach-entity when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null }));
    expect(screen.queryByTestId("btn-detach-entity")).toBeNull();
  });

  it("hides entity-history-panel when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null }));
    expect(screen.queryByTestId("entity-history-panel")).toBeNull();
  });

  it("btn-attach-entity label contains Link Entity text", () => {
    navigateToDetail(makeRun({ status: "active", entity_type: null }));
    expect(screen.getByTestId("btn-attach-entity").textContent).toContain("Link Entity");
  });
});

// ── BusinessContextSection — entity attached ──────────────────────────────────

describe("BusinessContextSection — entity attached", () => {
  const entityRun = () =>
    makeRun({
      status: "active",
      entity_type: "lead",
      entity_id: ENTITY_ID,
      entity_title: "Acme Corp",
    });

  it("renders entity-type-badge when entity is attached", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-type-badge")).not.toBeNull();
  });

  it("entity-type-badge shows entity type text", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-type-badge").textContent).toContain("lead");
  });

  it("entity-title-text shows entity title", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-title-text").textContent).toContain("Acme Corp");
  });

  it("btn-open-entity is shown when entity is attached", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("btn-open-entity")).not.toBeNull();
  });

  it("btn-open-entity href points to entity route", () => {
    navigateToDetail(entityRun());
    const link = screen.getByTestId("btn-open-entity") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/leads/${ENTITY_ID}`);
  });

  it("btn-open-entity label contains entity type", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("btn-open-entity").textContent).toContain("lead");
  });

  it("hides no-entity placeholder text when entity is attached", () => {
    navigateToDetail(entityRun());
    const section = screen.getByTestId("business-context-section");
    expect(section.textContent).not.toContain("No entity linked to this run");
  });

  it("hides btn-attach-entity when entity is already attached", () => {
    navigateToDetail(entityRun());
    expect(screen.queryByTestId("btn-attach-entity")).toBeNull();
  });

  it("shows btn-detach-entity when run is active and entity attached", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("btn-detach-entity")).not.toBeNull();
  });

  it("shows btn-detach-entity when run is pending and entity attached", () => {
    navigateToDetail(makeRun({ status: "pending", entity_type: "proposal", entity_id: ENTITY_ID, entity_title: "Deal" }));
    expect(screen.getByTestId("btn-detach-entity")).not.toBeNull();
  });

  it("hides btn-detach-entity when run is completed", () => {
    navigateToDetail(makeRun({ status: "completed", entity_type: "lead", entity_id: ENTITY_ID, entity_title: "Acme" }));
    expect(screen.queryByTestId("btn-detach-entity")).toBeNull();
  });

  it("hides btn-detach-entity when run is cancelled", () => {
    navigateToDetail(makeRun({ status: "cancelled", entity_type: "lead", entity_id: ENTITY_ID, entity_title: "Acme" }));
    expect(screen.queryByTestId("btn-detach-entity")).toBeNull();
  });

  it("entity-history-panel renders when entity is attached", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-history-panel")).not.toBeNull();
  });

  it("btn-open-entity href uses proposal route for proposal entity type", () => {
    navigateToDetail(makeRun({ status: "active", entity_type: "proposal", entity_id: ENTITY_ID, entity_title: "Deal" }));
    const link = screen.getByTestId("btn-open-entity") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/proposals/${ENTITY_ID}`);
  });
});

// ── AttachEntityDialog ────────────────────────────────────────────────────────

describe("AttachEntityDialog", () => {
  function openAttachDialog() {
    navigateToDetail(makeRun({ status: "active", entity_type: null }));
    fireEvent.click(screen.getByTestId("btn-attach-entity"));
  }

  it("opens dialog when btn-attach-entity is clicked", () => {
    openAttachDialog();
    expect(screen.getByTestId("attach-entity-dialog")).not.toBeNull();
  });

  it("shows entity-type-select in dialog", () => {
    openAttachDialog();
    expect(screen.getByTestId("entity-type-select")).not.toBeNull();
  });

  it("entity-type-select has 6 options", () => {
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.options.length).toBe(6);
  });

  it("entity-type-select defaults to lead", () => {
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.value).toBe("lead");
  });

  it("entity-type-select contains lead option", () => {
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("lead");
  });

  it("entity-type-select contains proposal option", () => {
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("proposal");
  });

  it("entity-type-select contains campaign, customer, training, other options", () => {
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("campaign");
    expect(options).toContain("customer");
    expect(options).toContain("training");
    expect(options).toContain("other");
  });

  it("shows entity-id-input", () => {
    openAttachDialog();
    expect(screen.getByTestId("entity-id-input")).not.toBeNull();
  });

  it("entity-id-input is empty initially", () => {
    openAttachDialog();
    const input = screen.getByTestId("entity-id-input") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("shows entity-title-input", () => {
    openAttachDialog();
    expect(screen.getByTestId("entity-title-input")).not.toBeNull();
  });

  it("entity-title-input is empty initially", () => {
    openAttachDialog();
    const input = screen.getByTestId("entity-title-input") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("btn-attach-confirm is disabled when both fields empty", () => {
    openAttachDialog();
    const btn = screen.getByTestId("btn-attach-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("btn-attach-confirm is disabled when only entity-id filled", () => {
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-id-input"), { target: { value: ENTITY_ID } });
    const btn = screen.getByTestId("btn-attach-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("btn-attach-confirm is disabled when only entity-title filled", () => {
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-title-input"), { target: { value: "Acme Corp" } });
    const btn = screen.getByTestId("btn-attach-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("btn-attach-confirm is enabled when both entity-id and entity-title filled", () => {
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-id-input"), { target: { value: ENTITY_ID } });
    fireEvent.change(screen.getByTestId("entity-title-input"), { target: { value: "Acme Corp" } });
    const btn = screen.getByTestId("btn-attach-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("changing entity-type-select updates its value", () => {
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-type-select"), { target: { value: "proposal" } });
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.value).toBe("proposal");
  });

  it("calls attach.mutate with correct entity data when confirmed", () => {
    const attachMutate = vi.fn();
    mockUseAttachEntity.mockReturnValue({
      mutate: attachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-type-select"), { target: { value: "proposal" } });
    fireEvent.change(screen.getByTestId("entity-id-input"), { target: { value: ENTITY_ID } });
    fireEvent.change(screen.getByTestId("entity-title-input"), { target: { value: "New Deal" } });
    fireEvent.click(screen.getByTestId("btn-attach-confirm"));
    expect(attachMutate).toHaveBeenCalledWith(
      { entity_type: "proposal", entity_id: ENTITY_ID, entity_title: "New Deal" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("calls attach.mutate with leading/trailing whitespace trimmed", () => {
    const attachMutate = vi.fn();
    mockUseAttachEntity.mockReturnValue({
      mutate: attachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-id-input"), { target: { value: "  uuid-123  " } });
    fireEvent.change(screen.getByTestId("entity-title-input"), { target: { value: "  Acme Corp  " } });
    fireEvent.click(screen.getByTestId("btn-attach-confirm"));
    expect(attachMutate).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: "uuid-123", entity_title: "Acme Corp" }),
      expect.any(Object),
    );
  });

  it("disables entity-id-input while isPending", () => {
    mockUseAttachEntity.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    const input = screen.getByTestId("entity-id-input") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("disables entity-title-input while isPending", () => {
    mockUseAttachEntity.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    const input = screen.getByTestId("entity-title-input") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("disables entity-type-select while isPending", () => {
    mockUseAttachEntity.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    const select = screen.getByTestId("entity-type-select") as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });

  it("btn-attach-confirm shows Link Entity text", () => {
    openAttachDialog();
    expect(screen.getByTestId("btn-attach-confirm").textContent).toContain("Link Entity");
  });

  it("closes dialog after successful attach (onSuccess called)", () => {
    const attachMutate = vi.fn((_, opts) => opts?.onSuccess?.());
    mockUseAttachEntity.mockReturnValue({
      mutate: attachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useAttachEntity>);
    openAttachDialog();
    fireEvent.change(screen.getByTestId("entity-id-input"), { target: { value: ENTITY_ID } });
    fireEvent.change(screen.getByTestId("entity-title-input"), { target: { value: "Acme Corp" } });
    fireEvent.click(screen.getByTestId("btn-attach-confirm"));
    expect(screen.queryByTestId("attach-entity-dialog")).toBeNull();
  });
});

// ── DetachEntityDialog ────────────────────────────────────────────────────────

describe("DetachEntityDialog", () => {
  function openDetachDialog() {
    navigateToDetail(
      makeRun({
        status: "active",
        entity_type: "lead",
        entity_id: ENTITY_ID,
        entity_title: "Acme Corp",
      }),
    );
    fireEvent.click(screen.getByTestId("btn-detach-entity"));
  }

  it("opens dialog when btn-detach-entity is clicked", () => {
    openDetachDialog();
    expect(screen.getByTestId("detach-entity-dialog")).not.toBeNull();
  });

  it("shows entity title in dialog confirmation text", () => {
    openDetachDialog();
    const dialog = screen.getByTestId("detach-entity-dialog");
    expect(dialog.textContent).toContain("Acme Corp");
  });

  it("shows btn-detach-confirm in dialog", () => {
    openDetachDialog();
    expect(screen.getByTestId("btn-detach-confirm")).not.toBeNull();
  });

  it("btn-detach-confirm shows Unlink text", () => {
    openDetachDialog();
    expect(screen.getByTestId("btn-detach-confirm").textContent).toContain("Unlink");
  });

  it("calls detach.mutate when btn-detach-confirm is clicked", () => {
    const detachMutate = vi.fn();
    mockUseDetachEntity.mockReturnValue({
      mutate: detachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDetachEntity>);
    openDetachDialog();
    fireEvent.click(screen.getByTestId("btn-detach-confirm"));
    expect(detachMutate).toHaveBeenCalled();
  });

  it("disables btn-detach-confirm while isPending", () => {
    mockUseDetachEntity.mockReturnValue({
      mutate: noop,
      isPending: true,
    } as unknown as ReturnType<typeof useDetachEntity>);
    openDetachDialog();
    const btn = screen.getByTestId("btn-detach-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("dialog contains Unlink from Entity heading text", () => {
    openDetachDialog();
    const dialog = screen.getByTestId("detach-entity-dialog");
    expect(dialog.textContent).toContain("Unlink from Entity");
  });

  it("closes dialog after successful detach (onSuccess called)", () => {
    const detachMutate = vi.fn((_, opts) => opts?.onSuccess?.());
    mockUseDetachEntity.mockReturnValue({
      mutate: detachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDetachEntity>);
    openDetachDialog();
    fireEvent.click(screen.getByTestId("btn-detach-confirm"));
    expect(screen.queryByTestId("detach-entity-dialog")).toBeNull();
  });

  it("calls detach.mutate with undefined (no payload) as first arg", () => {
    const detachMutate = vi.fn();
    mockUseDetachEntity.mockReturnValue({
      mutate: detachMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDetachEntity>);
    openDetachDialog();
    fireEvent.click(screen.getByTestId("btn-detach-confirm"));
    expect(detachMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

// ── EntityWorkflowHistoryPanel ────────────────────────────────────────────────

describe("EntityWorkflowHistoryPanel", () => {
  const entityRun = (overrides: Partial<WorkflowRunOut> = {}) =>
    makeRun({
      status: "active",
      entity_type: "lead",
      entity_id: ENTITY_ID,
      entity_title: "Acme Corp",
      ...overrides,
    });

  it("renders entity-history-panel when entity is attached", () => {
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-history-panel")).not.toBeNull();
  });

  it("does not render entity-history-panel when no entity", () => {
    navigateToDetail(makeRun({ entity_type: null, entity_id: null }));
    expect(screen.queryByTestId("entity-history-panel")).toBeNull();
  });

  it("shows entity-history-loading when data is loading", () => {
    setupEntityRuns([], true);
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-history-loading")).not.toBeNull();
  });

  it("shows entity-history-empty when entity has no other runs", () => {
    setupEntityRuns([]);
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-history-empty")).not.toBeNull();
  });

  it("shows entity-history-empty text content", () => {
    setupEntityRuns([]);
    navigateToDetail(entityRun());
    expect(screen.getByTestId("entity-history-empty").textContent).toContain("No other runs for this entity");
  });

  it("renders entity-history-run-{id} for a history run", () => {
    const historyRun = makeRun({ id: RUN_B, title: "Prior Lead Follow-Up" });
    setupEntityRuns([historyRun]);
    navigateToDetail(entityRun());
    expect(screen.getByTestId(`entity-history-run-${RUN_B}`)).not.toBeNull();
  });

  it("filters out the current run from entity history", () => {
    const currentRun = entityRun();
    setupEntityRuns([currentRun]);
    navigateToDetail(currentRun);
    expect(screen.queryByTestId(`entity-history-run-${RUN_A}`)).toBeNull();
  });

  it("shows multiple history runs when entity has multiple", () => {
    const run1 = makeRun({ id: RUN_B, title: "First Attempt" });
    const run2 = makeRun({ id: RUN_C, title: "Second Attempt" });
    setupEntityRuns([run1, run2]);
    navigateToDetail(entityRun());
    expect(screen.getByTestId(`entity-history-run-${RUN_B}`)).not.toBeNull();
    expect(screen.getByTestId(`entity-history-run-${RUN_C}`)).not.toBeNull();
  });

  it("history run row shows run title", () => {
    const historyRun = makeRun({ id: RUN_B, title: "Prior Lead Follow-Up" });
    setupEntityRuns([historyRun]);
    navigateToDetail(entityRun());
    const row = screen.getByTestId(`entity-history-run-${RUN_B}`);
    expect(row.textContent).toContain("Prior Lead Follow-Up");
  });

  it("calls useEntityRuns with correct workspace, entity type and entity id", () => {
    navigateToDetail(entityRun());
    expect(mockUseEntityRuns).toHaveBeenCalledWith(WS_ID, "lead", ENTITY_ID);
  });

  it("panel heading contains Run History text", () => {
    navigateToDetail(entityRun());
    const panel = screen.getByTestId("entity-history-panel");
    expect(panel.textContent).toContain("Run History");
  });

  it("history panel does not show entity-history-empty when loading", () => {
    setupEntityRuns([], true);
    navigateToDetail(entityRun());
    expect(screen.queryByTestId("entity-history-empty")).toBeNull();
  });

  it("clicking a history run navigates into that run's detail", () => {
    const historyRun = makeRun({ id: RUN_B, title: "Prior Lead Follow-Up" });
    setupEntityRuns([historyRun]);
    setupRunDetail(historyRun);
    navigateToDetail(entityRun());
    fireEvent.click(screen.getByTestId(`entity-history-run-${RUN_B}`));
    expect(screen.getByTestId("run-detail")).not.toBeNull();
  });

  it("history run rendered as a button element", () => {
    const historyRun = makeRun({ id: RUN_B, title: "Prior" });
    setupEntityRuns([historyRun]);
    navigateToDetail(entityRun());
    const el = screen.getByTestId(`entity-history-run-${RUN_B}`);
    expect(el.tagName.toLowerCase()).toBe("button");
  });
});
