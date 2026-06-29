import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type {
  WorkflowTemplateListPage,
  WorkflowTemplateOut,
  WorkflowStepOut,
} from "@/features/workflows/types";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("@/features/workflows/api/use-workflows", () => ({
  useWorkflowTemplates: vi.fn(),
  useWorkflowTemplate: vi.fn(),
  useCreateTemplate: vi.fn(),
  useUpdateTemplate: vi.fn(),
  useDeleteTemplate: vi.fn(),
  useDuplicateTemplate: vi.fn(),
  useAddStep: vi.fn(),
  useUpdateStep: vi.fn(),
  useDeleteStep: vi.fn(),
  useReorderSteps: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/"),
  useParams: vi.fn(() => ({})),
}));

import { useWorkspace } from "@/hooks/use-workspace";
import {
  useWorkflowTemplates,
  useWorkflowTemplate,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useDuplicateTemplate,
  useAddStep,
  useDeleteStep,
  useReorderSteps,
} from "@/features/workflows/api/use-workflows";

const mockUseWorkspace = vi.mocked(useWorkspace);
const mockUseWorkflowTemplates = vi.mocked(useWorkflowTemplates);
const mockUseWorkflowTemplate = vi.mocked(useWorkflowTemplate);
const mockUseCreateTemplate = vi.mocked(useCreateTemplate);
const mockUseUpdateTemplate = vi.mocked(useUpdateTemplate);
const mockUseDeleteTemplate = vi.mocked(useDeleteTemplate);
const mockUseDuplicateTemplate = vi.mocked(useDuplicateTemplate);
const mockUseAddStep = vi.mocked(useAddStep);
const mockUseDeleteStep = vi.mocked(useDeleteStep);
const mockUseReorderSteps = vi.mocked(useReorderSteps);

const { WorkflowTemplateCenter } = await import("./workflow-template-center");

// ── Factories ─────────────────────────────────────────────────────────────────

const WS_ID = "ws-wf-1";
const TMPL_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const TMPL_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const STEP_1 = "11111111-1111-1111-1111-111111111111";
const STEP_2 = "22222222-2222-2222-2222-222222222222";

function makeStep(overrides: Partial<WorkflowStepOut> = {}): WorkflowStepOut {
  return {
    id: STEP_1,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    workflow_template_id: TMPL_A,
    step_order: 1,
    title: "Initial Contact",
    description: null,
    owner_role: "member",
    estimated_hours: "2.00",
    required: true,
    created_at: "2026-06-29T10:00:00Z",
    ...overrides,
  };
}

function makeTemplate(overrides: Partial<WorkflowTemplateOut> = {}): WorkflowTemplateOut {
  return {
    id: TMPL_A,
    tenant_id: "org-1",
    workspace_id: WS_ID,
    name: "New Corporate Lead",
    description: "Standard onboarding",
    category: "new_corporate_lead",
    is_active: true,
    created_by: "user-1",
    created_at: "2026-06-29T10:00:00Z",
    steps: [],
    ...overrides,
  };
}

function makeListPage(overrides: Partial<WorkflowTemplateListPage> = {}): WorkflowTemplateListPage {
  return {
    items: [],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function noop() {}
function noopMutate(arg?: unknown, opts?: { onSuccess?: () => void }) {
  opts?.onSuccess?.();
}

function setupMocks() {
  mockUseWorkspace.mockReturnValue({ workspaceId: WS_ID });
  mockUseWorkflowTemplates.mockReturnValue({
    data: makeListPage(),
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useWorkflowTemplates>);
  mockUseWorkflowTemplate.mockReturnValue({
    data: makeTemplate(),
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useWorkflowTemplate>);
  mockUseCreateTemplate.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateTemplate>);
  mockUseUpdateTemplate.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateTemplate>);
  mockUseDeleteTemplate.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteTemplate>);
  mockUseDuplicateTemplate.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useDuplicateTemplate>);
  mockUseAddStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useAddStep>);
  mockUseDeleteStep.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteStep>);
  mockUseReorderSteps.mockReturnValue({
    mutate: noop,
    isPending: false,
  } as unknown as ReturnType<typeof useReorderSteps>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Workspace guard ────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — workspace guard", () => {
  it("shows no-workspace message when workspaceId is null", () => {
    mockUseWorkspace.mockReturnValue({ workspaceId: null });
    mockUseWorkflowTemplates.mockReturnValue({ data: undefined, isLoading: false, isError: false } as ReturnType<typeof useWorkflowTemplates>);
    mockUseCreateTemplate.mockReturnValue({ mutate: noop, isPending: false } as unknown as ReturnType<typeof useCreateTemplate>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("workflows-no-workspace")).not.toBeNull();
  });

  it("does not render template list without workspace", () => {
    mockUseWorkspace.mockReturnValue({ workspaceId: null });
    mockUseWorkflowTemplates.mockReturnValue({ data: undefined, isLoading: false, isError: false } as ReturnType<typeof useWorkflowTemplates>);
    mockUseCreateTemplate.mockReturnValue({ mutate: noop, isPending: false } as unknown as ReturnType<typeof useCreateTemplate>);
    render(<WorkflowTemplateCenter />);
    expect(screen.queryByTestId("workflow-template-center")).toBeNull();
  });
});

// ── Loading state ──────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — loading", () => {
  it("shows skeleton while loading", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("template-list-skeleton")).not.toBeNull();
  });

  it("does not show list while loading", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.queryByTestId("template-list")).toBeNull();
  });
});

// ── Error state ────────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — error", () => {
  it("shows error message on failure", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("template-list-error")).not.toBeNull();
  });
});

// ── Empty state ────────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — empty", () => {
  it("shows empty message when no templates", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("template-list-empty")).not.toBeNull();
  });

  it("shows new template button", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("new-template-btn")).not.toBeNull();
  });
});

// ── Template list ──────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — template list", () => {
  it("renders template cards", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId(`template-card-${TMPL_A}`)).not.toBeNull();
    expect(screen.getByTestId(`template-name-${TMPL_A}`)).not.toBeNull();
  });

  it("renders category badge on template card", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("category-badge-new_corporate_lead")).not.toBeNull();
  });

  it("renders step count on card", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate({ steps: [makeStep()] })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId(`template-steps-count-${TMPL_A}`).textContent).toContain("1 step");
  });

  it("renders hours on card", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate({ steps: [makeStep({ estimated_hours: "3.00" })] })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId(`template-hours-${TMPL_A}`).textContent).toContain("3.0h");
  });

  it("shows inactive indicator on inactive template", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate({ is_active: false })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId(`template-inactive-${TMPL_A}`)).not.toBeNull();
  });

  it("shows next button when has_more=true", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()], has_more: true, next_cursor: "cursor123" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("template-list-next-btn")).not.toBeNull();
  });

  it("does not show next button when has_more=false", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.queryByTestId("template-list-next-btn")).toBeNull();
  });

  it("renders multiple templates", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({
        items: [makeTemplate({ id: TMPL_A }), makeTemplate({ id: TMPL_B, name: "B" })],
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId(`template-card-${TMPL_A}`)).not.toBeNull();
    expect(screen.getByTestId(`template-card-${TMPL_B}`)).not.toBeNull();
  });
});

// ── Category filter ────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — category filter", () => {
  it("renders category filter select", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    expect(screen.getByTestId("category-filter")).not.toBeNull();
  });

  it("shows clear button when category is selected", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    const select = screen.getByTestId("category-filter") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "enterprise_sales" } });
    expect(screen.getByTestId("clear-category-filter")).not.toBeNull();
  });

  it("clears filter when clear button clicked", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    const select = screen.getByTestId("category-filter") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "other" } });
    fireEvent.click(screen.getByTestId("clear-category-filter"));
    expect(screen.queryByTestId("clear-category-filter")).toBeNull();
  });
});

// ── Create template form ───────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — create template form", () => {
  it("shows form when new template button clicked", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    expect(screen.getByTestId("create-template-form")).not.toBeNull();
  });

  it("hides form after cancel", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    fireEvent.click(screen.getByTestId("create-template-cancel"));
    expect(screen.queryByTestId("create-template-form")).toBeNull();
  });

  it("submit button disabled when name empty", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    const submit = screen.getByTestId("create-template-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("submit button enabled when name filled", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    fireEvent.change(screen.getByTestId("template-name-input"), { target: { value: "My Template" } });
    const submit = screen.getByTestId("create-template-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });

  it("calls createTemplate.mutate on submit", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseCreateTemplate.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useCreateTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    fireEvent.change(screen.getByTestId("template-name-input"), { target: { value: "Test" } });
    fireEvent.click(screen.getByTestId("create-template-submit"));
    expect(mutateMock).toHaveBeenCalledOnce();
  });

  it("category select has all options", () => {
    setupMocks();
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("new-template-btn"));
    const select = screen.getByTestId("template-category-select") as HTMLSelectElement;
    expect(select.options.length).toBe(8); // 8 valid categories
  });
});

// ── Delete template ────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — delete template", () => {
  it("calls deleteTemplate.mutate when delete button clicked", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseDeleteTemplate.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useDeleteTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`delete-template-btn-${TMPL_A}`));
    expect(mutateMock).toHaveBeenCalledWith(TMPL_A);
  });
});

// ── Template detail ────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — template detail", () => {
  it("navigates to detail when template card clicked", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-detail")).not.toBeNull();
  });

  it("shows template name in detail", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-detail-name").textContent).toBe("New Corporate Lead");
  });

  it("back button returns to list", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("back-to-list-btn"));
    expect(screen.getByTestId("workflow-template-center")).not.toBeNull();
    expect(screen.queryByTestId("template-detail")).toBeNull();
  });

  it("shows detail skeleton while loading", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseWorkflowTemplate.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useWorkflowTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-detail-skeleton")).not.toBeNull();
  });

  it("shows detail error on failure", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseWorkflowTemplate.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useWorkflowTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-detail-error")).not.toBeNull();
  });

  it("shows duplicate button in detail", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("duplicate-template-btn")).not.toBeNull();
  });

  it("shows step count and total hours in detail", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ estimated_hours: "4.50" })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-step-count").textContent).toContain("1 step");
    expect(screen.getByTestId("template-total-hours").textContent).toContain("4.5h");
  });

  it("toggle-active button calls updateTemplate", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseUpdateTemplate.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useUpdateTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("toggle-active-btn"));
    expect(mutateMock).toHaveBeenCalledOnce();
  });

  it("shows inactive badge for inactive template in detail", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ is_active: false }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate({ is_active: false })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("template-inactive-badge")).not.toBeNull();
  });
});

// ── Duplicate dialog ───────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — duplicate dialog", () => {
  it("opens duplicate dialog on button click", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("duplicate-template-btn"));
    expect(screen.getByTestId("duplicate-dialog")).not.toBeNull();
  });

  it("closes dialog on cancel", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("duplicate-template-btn"));
    fireEvent.click(screen.getByTestId("duplicate-dialog-cancel"));
    expect(screen.queryByTestId("duplicate-dialog")).toBeNull();
  });

  it("calls duplicate mutate on confirm", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseDuplicateTemplate.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useDuplicateTemplate>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("duplicate-template-btn"));
    fireEvent.click(screen.getByTestId("duplicate-dialog-confirm"));
    expect(mutateMock).toHaveBeenCalledWith(TMPL_A, expect.any(Object));
  });
});

// ── Step list ──────────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — step list", () => {
  function navigateToDetail() {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
  }

  it("renders step list section", () => {
    navigateToDetail();
    expect(screen.getByTestId("step-list")).not.toBeNull();
  });

  it("shows no-steps message when empty", () => {
    navigateToDetail();
    expect(screen.getByTestId("no-steps-message")).not.toBeNull();
  });

  it("shows step items when template has steps", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId(`step-item-${STEP_1}`)).not.toBeNull();
    expect(screen.getByTestId(`step-title-${STEP_1}`).textContent).toBe("Initial Contact");
  });

  it("renders owner role badge on step", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ owner_role: "admin" })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("owner-role-badge-admin")).not.toBeNull();
  });

  it("renders required badge on required step", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ required: true })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId(`step-required-badge-${STEP_1}`)).not.toBeNull();
  });

  it("shows step hours", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ estimated_hours: "3.50" })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId(`step-hours-${STEP_1}`).textContent).toContain("3.50h");
  });

  it("shows add step button", () => {
    navigateToDetail();
    expect(screen.getByTestId("add-step-btn")).not.toBeNull();
  });

  it("shows add step form when add button clicked", () => {
    navigateToDetail();
    fireEvent.click(screen.getByTestId("add-step-btn"));
    expect(screen.getByTestId("add-step-form")).not.toBeNull();
  });

  it("hides add step form after cancel", () => {
    navigateToDetail();
    fireEvent.click(screen.getByTestId("add-step-btn"));
    fireEvent.click(screen.getByTestId("add-step-cancel"));
    expect(screen.queryByTestId("add-step-form")).toBeNull();
  });

  it("add step submit disabled when title empty", () => {
    navigateToDetail();
    fireEvent.click(screen.getByTestId("add-step-btn"));
    const submit = screen.getByTestId("add-step-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("add step submit enabled when title filled", () => {
    navigateToDetail();
    fireEvent.click(screen.getByTestId("add-step-btn"));
    fireEvent.change(screen.getByTestId("step-title-input"), { target: { value: "Step 1" } });
    const submit = screen.getByTestId("add-step-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });

  it("calls addStep.mutate on submit", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseAddStep.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useAddStep>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId("add-step-btn"));
    fireEvent.change(screen.getByTestId("step-title-input"), { target: { value: "New Step" } });
    fireEvent.click(screen.getByTestId("add-step-submit"));
    expect(mutateMock).toHaveBeenCalledOnce();
  });

  it("calls deleteStep.mutate on step delete", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseDeleteStep.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useDeleteStep>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId(`delete-step-btn-${STEP_1}`));
    expect(mutateMock).toHaveBeenCalledWith({ stepId: STEP_1, templateId: TMPL_A });
  });
});

// ── Step reorder ───────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — step reorder", () => {
  it("shows move-up/move-down buttons for each step", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2, title: "Step 2" })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId(`move-up-btn-${STEP_1}`)).not.toBeNull();
    expect(screen.getByTestId(`move-down-btn-${STEP_1}`)).not.toBeNull();
  });

  it("first step move-up button is disabled", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2 })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    const upBtn = screen.getByTestId(`move-up-btn-${STEP_1}`) as HTMLButtonElement;
    expect(upBtn.disabled).toBe(true);
  });

  it("last step move-down button is disabled", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2 })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    const downBtn = screen.getByTestId(`move-down-btn-${STEP_2}`) as HTMLButtonElement;
    expect(downBtn.disabled).toBe(true);
  });

  it("shows save-order button after moving a step", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2 })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId(`move-down-btn-${STEP_1}`));
    expect(screen.getByTestId("commit-order-btn")).not.toBeNull();
  });

  it("calls reorderSteps on save order click", () => {
    const mutateMock = vi.fn();
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2 })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    mockUseReorderSteps.mockReturnValue({ mutate: mutateMock, isPending: false } as unknown as ReturnType<typeof useReorderSteps>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    fireEvent.click(screen.getByTestId(`move-down-btn-${STEP_1}`));
    fireEvent.click(screen.getByTestId("commit-order-btn"));
    expect(mutateMock).toHaveBeenCalledOnce();
  });

  it("step count badge renders correctly", () => {
    setupMocks();
    mockUseWorkflowTemplate.mockReturnValue({
      data: makeTemplate({ steps: [makeStep({ id: STEP_1 }), makeStep({ id: STEP_2, step_order: 2 })] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplate>);
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()] }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId(`template-card-${TMPL_A}`));
    expect(screen.getByTestId("step-count").textContent).toContain("2");
  });
});

// ── Pagination ─────────────────────────────────────────────────────────────────

describe("WorkflowTemplateCenter — pagination", () => {
  it("shows prev button after navigating to next page", () => {
    setupMocks();
    mockUseWorkflowTemplates.mockReturnValue({
      data: makeListPage({ items: [makeTemplate()], has_more: true, next_cursor: "c1" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useWorkflowTemplates>);
    render(<WorkflowTemplateCenter />);
    fireEvent.click(screen.getByTestId("template-list-next-btn"));
    expect(screen.getByTestId("template-list-prev-btn")).not.toBeNull();
  });
});
