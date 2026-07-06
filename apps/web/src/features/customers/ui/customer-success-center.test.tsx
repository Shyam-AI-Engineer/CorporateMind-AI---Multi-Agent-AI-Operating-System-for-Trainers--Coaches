import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CustomerSuccess, CustomerSuccessListOut } from "@/features/customers/types-success";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/customers/api/use-renewal", () => ({
  useCustomerRenewalList: vi.fn(),
  useCustomerRenewalDetail: vi.fn(),
  useRenewalsByCustomer: vi.fn(),
  useCreateCustomerRenewal: vi.fn(),
  useUpdateCustomerRenewal: vi.fn(),
  useAssignRenewalOwner: vi.fn(),
  useUpdateRenewalStatus: vi.fn(),
  useAttachProposal: vi.fn(),
  useArchiveCustomerRenewal: vi.fn(),
}));

vi.mock("@/features/customers/api/use-customer-success", () => ({
  useCustomerSuccessList: vi.fn(),
  useCustomerSuccessDetail: vi.fn(),
  useCustomerSuccessByCustomer: vi.fn(),
  useCreateCustomerSuccess: vi.fn(),
  useUpdateCustomerSuccess: vi.fn(),
  useAssignSuccessOwner: vi.fn(),
  useUpdateSuccessHealth: vi.fn(),
  useScheduleFollowup: vi.fn(),
  useArchiveCustomerSuccess: vi.fn(),
}));

import {
  useCustomerSuccessList,
  useCustomerSuccessDetail,
  useCustomerSuccessByCustomer,
  useCreateCustomerSuccess,
  useUpdateCustomerSuccess,
  useAssignSuccessOwner,
  useUpdateSuccessHealth,
  useScheduleFollowup,
  useArchiveCustomerSuccess,
} from "@/features/customers/api/use-customer-success";

import { useRenewalsByCustomer } from "@/features/customers/api/use-renewal";

const mockList = vi.mocked(useCustomerSuccessList);
const mockDetail = vi.mocked(useCustomerSuccessDetail);
const mockByCustomer = vi.mocked(useCustomerSuccessByCustomer);
const mockCreate = vi.mocked(useCreateCustomerSuccess);
const mockUpdate = vi.mocked(useUpdateCustomerSuccess);
const mockAssignOwner = vi.mocked(useAssignSuccessOwner);
const mockUpdateHealth = vi.mocked(useUpdateSuccessHealth);
const mockScheduleFollowup = vi.mocked(useScheduleFollowup);
const mockArchive = vi.mocked(useArchiveCustomerSuccess);
const mockRenewalsByCustomer = vi.mocked(useRenewalsByCustomer);

const {
  HealthBadge,
  RiskBadge,
  KpiBar,
  FilterBar,
  SuccessTable,
  FollowupDialog,
  OwnerAssignmentDialog,
  CreateSuccessDialog,
  CustomerSuccessDrawer,
  CustomerSuccessCenter,
  CustomerSuccessSummary,
} = await import("./customer-success-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS = "ws-47";

function makeRecord(overrides: Partial<CustomerSuccess> = {}): CustomerSuccess {
  return {
    id: "rec-1",
    tenant_id: "org-1",
    workspace_id: WS,
    customer_id: "cust-1",
    health_status: "watch",
    health_score: null,
    risk_level: "medium",
    owner_user_id: null,
    renewal_date: null,
    last_contact_date: null,
    next_followup_date: null,
    expansion_opportunity: false,
    renewal_probability: null,
    notes: null,
    is_archived: false,
    created_at: "2026-07-05T10:00:00Z",
    updated_at: "2026-07-05T10:00:00Z",
    ...overrides,
  };
}

function makeListOut(
  items: CustomerSuccess[] = [],
  overrides: Partial<CustomerSuccessListOut> = {}
): CustomerSuccessListOut {
  return { items, next_cursor: null, has_more: false, total: items.length, ...overrides };
}

function idleMutation() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
}

function idleQuery() {
  return { data: undefined, isLoading: false, isError: false };
}

function setupMutations() {
  mockUpdateHealth.mockReturnValue(idleMutation() as ReturnType<typeof useUpdateSuccessHealth>);
  mockScheduleFollowup.mockReturnValue(idleMutation() as ReturnType<typeof useScheduleFollowup>);
  mockAssignOwner.mockReturnValue(idleMutation() as ReturnType<typeof useAssignSuccessOwner>);
  mockArchive.mockReturnValue(idleMutation() as ReturnType<typeof useArchiveCustomerSuccess>);
  mockCreate.mockReturnValue(idleMutation() as ReturnType<typeof useCreateCustomerSuccess>);
  mockUpdate.mockReturnValue(idleMutation() as ReturnType<typeof useUpdateCustomerSuccess>);
  mockRenewalsByCustomer.mockReturnValue(idleQuery() as ReturnType<typeof useRenewalsByCustomer>);
}

// ── HealthBadge ───────────────────────────────────────────────────────────────

describe("HealthBadge", () => {
  it("renders healthy badge", () => {
    render(<HealthBadge status="healthy" />);
    expect(screen.getByTestId("health-badge-healthy")).not.toBeNull();
  });

  it("renders watch badge", () => {
    render(<HealthBadge status="watch" />);
    expect(screen.getByTestId("health-badge-watch")).not.toBeNull();
  });

  it("renders at_risk badge", () => {
    render(<HealthBadge status="at_risk" />);
    expect(screen.getByTestId("health-badge-at_risk")).not.toBeNull();
  });

  it("healthy badge has label text", () => {
    render(<HealthBadge status="healthy" />);
    const el = screen.getByTestId("health-badge-healthy");
    expect(el.textContent?.toLowerCase()).toContain("healthy");
  });

  it("at_risk badge has label text", () => {
    render(<HealthBadge status="at_risk" />);
    const el = screen.getByTestId("health-badge-at_risk");
    expect(el.textContent?.toLowerCase()).toMatch(/at.?risk/);
  });

  it("watch badge has label text", () => {
    render(<HealthBadge status="watch" />);
    const el = screen.getByTestId("health-badge-watch");
    expect(el.textContent?.toLowerCase()).toContain("watch");
  });
});

// ── RiskBadge ─────────────────────────────────────────────────────────────────

describe("RiskBadge", () => {
  it("renders low badge", () => {
    render(<RiskBadge level="low" />);
    expect(screen.getByTestId("risk-badge-low")).not.toBeNull();
  });

  it("renders medium badge", () => {
    render(<RiskBadge level="medium" />);
    expect(screen.getByTestId("risk-badge-medium")).not.toBeNull();
  });

  it("renders high badge", () => {
    render(<RiskBadge level="high" />);
    expect(screen.getByTestId("risk-badge-high")).not.toBeNull();
  });

  it("high badge has text", () => {
    render(<RiskBadge level="high" />);
    expect(screen.getByTestId("risk-badge-high").textContent?.toLowerCase()).toContain("high");
  });

  it("low badge has text", () => {
    render(<RiskBadge level="low" />);
    expect(screen.getByTestId("risk-badge-low").textContent?.toLowerCase()).toContain("low");
  });

  it("medium badge has text", () => {
    render(<RiskBadge level="medium" />);
    expect(screen.getByTestId("risk-badge-medium").textContent?.toLowerCase()).toContain("medium");
  });
});

// ── KpiBar ────────────────────────────────────────────────────────────────────

describe("KpiBar", () => {
  const items = [
    makeRecord({ health_status: "healthy" }),
    makeRecord({ id: "r2", health_status: "watch" }),
    makeRecord({
      id: "r3",
      health_status: "at_risk",
      renewal_date: "2026-08-01",
      next_followup_date: "2026-07-10",
      expansion_opportunity: true,
    }),
  ];

  it("renders kpi-bar", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-bar")).not.toBeNull();
  });

  it("shows healthy count as 1", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-healthy").textContent).toContain("1");
  });

  it("shows watch count as 1", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-watch").textContent).toContain("1");
  });

  it("shows at-risk count as 1", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-at-risk").textContent).toContain("1");
  });

  it("shows renewal tile", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-renewal")).not.toBeNull();
  });

  it("shows followup tile", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-followup")).not.toBeNull();
  });

  it("shows expansion count as 1", () => {
    render(<KpiBar items={items} />);
    expect(screen.getByTestId("kpi-expansion").textContent).toContain("1");
  });

  it("zeros on empty list", () => {
    render(<KpiBar items={[]} />);
    expect(screen.getByTestId("kpi-healthy").textContent).toContain("0");
  });
});

// ── FilterBar ─────────────────────────────────────────────────────────────────

describe("FilterBar", () => {
  function renderFilterBar(onSearch = vi.fn(), onHealth = vi.fn(), onRisk = vi.fn()) {
    return render(
      <FilterBar
        search=""
        health=""
        risk=""
        onSearch={onSearch}
        onHealth={onHealth}
        onRisk={onRisk}
      />
    );
  }

  it("renders filter-bar", () => {
    renderFilterBar();
    expect(screen.getByTestId("filter-bar")).not.toBeNull();
  });

  it("renders search-input", () => {
    renderFilterBar();
    expect(screen.getByTestId("search-input")).not.toBeNull();
  });

  it("renders health-filter", () => {
    renderFilterBar();
    expect(screen.getByTestId("health-filter")).not.toBeNull();
  });

  it("renders risk-filter", () => {
    renderFilterBar();
    expect(screen.getByTestId("risk-filter")).not.toBeNull();
  });

  it("calls onSearch when typing", () => {
    const onSearch = vi.fn();
    renderFilterBar(onSearch);
    const input = screen.getByTestId("search-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "enterprise" } });
    expect(onSearch).toHaveBeenCalledWith("enterprise");
  });

  it("calls onHealth when health filter changes", () => {
    const onHealth = vi.fn();
    render(
      <FilterBar search="" health="" risk="" onSearch={vi.fn()} onHealth={onHealth} onRisk={vi.fn()} />
    );
    const sel = screen.getByTestId("health-filter") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "at_risk" } });
    expect(onHealth).toHaveBeenCalledWith("at_risk");
  });

  it("calls onRisk when risk filter changes", () => {
    const onRisk = vi.fn();
    render(
      <FilterBar search="" health="" risk="" onSearch={vi.fn()} onHealth={vi.fn()} onRisk={onRisk} />
    );
    const sel = screen.getByTestId("risk-filter") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "high" } });
    expect(onRisk).toHaveBeenCalledWith("high");
  });
});

// ── SuccessTable ──────────────────────────────────────────────────────────────

describe("SuccessTable", () => {
  it("renders success-table", () => {
    render(<SuccessTable records={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("success-table")).not.toBeNull();
  });

  it("shows empty-state when no items", () => {
    render(<SuccessTable records={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("empty-state")).not.toBeNull();
  });

  it("renders a row per item", () => {
    const items = [makeRecord(), makeRecord({ id: "r2", customer_id: "c2" })];
    render(<SuccessTable records={items} onSelect={vi.fn()} />);
    expect(screen.getAllByTestId("success-row").length).toBe(2);
  });

  it("calls onSelect with record on row click", async () => {
    const onSelect = vi.fn();
    render(<SuccessTable records={[makeRecord()]} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId("success-row"));
    expect(onSelect).toHaveBeenCalledWith(makeRecord());
  });

  it("renders health badge in row", () => {
    render(<SuccessTable records={[makeRecord()]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("health-badge-watch")).not.toBeNull();
  });

  it("renders risk badge in row", () => {
    render(<SuccessTable records={[makeRecord()]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("risk-badge-medium")).not.toBeNull();
  });

  it("no empty-state when items present", () => {
    render(<SuccessTable records={[makeRecord()]} onSelect={vi.fn()} />);
    expect(screen.queryByTestId("empty-state")).toBeNull();
  });
});

// ── FollowupDialog ────────────────────────────────────────────────────────────

describe("FollowupDialog", () => {
  it("renders followup-dialog", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("followup-dialog")).not.toBeNull();
  });

  it("renders date input", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("followup-date-input")).not.toBeNull();
  });

  it("renders cancel button", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("followup-cancel")).not.toBeNull();
  });

  it("renders submit button", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("followup-submit")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(<FollowupDialog onClose={onClose} onSchedule={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByTestId("followup-cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onSchedule with date when submitted", async () => {
    const onSchedule = vi.fn();
    render(<FollowupDialog onClose={vi.fn()} onSchedule={onSchedule} isPending={false} />);
    const input = screen.getByTestId("followup-date-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2026-09-01" } });
    await userEvent.click(screen.getByTestId("followup-submit"));
    expect(onSchedule).toHaveBeenCalledWith("2026-09-01");
  });

  it("submit is disabled when date empty", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={false} />);
    const btn = screen.getByTestId("followup-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit shows pending text when isPending", () => {
    render(<FollowupDialog onClose={vi.fn()} onSchedule={vi.fn()} isPending={true} />);
    const btn = screen.getByTestId("followup-submit");
    expect(btn.textContent).toContain("Saving");
  });
});

// ── OwnerAssignmentDialog ──────────────────────────────────────────────────────

describe("OwnerAssignmentDialog", () => {
  it("renders owner-dialog", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("owner-dialog")).not.toBeNull();
  });

  it("renders owner-id-input", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("owner-id-input")).not.toBeNull();
  });

  it("renders cancel button", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("owner-cancel")).not.toBeNull();
  });

  it("renders submit button", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("owner-submit")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(<OwnerAssignmentDialog onClose={onClose} onAssign={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByTestId("owner-cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onAssign with owner id when submitted", async () => {
    const onAssign = vi.fn();
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={onAssign} isPending={false} />);
    const input = screen.getByTestId("owner-id-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "user-abc" } });
    await userEvent.click(screen.getByTestId("owner-submit"));
    expect(onAssign).toHaveBeenCalledWith("user-abc");
  });

  it("submit disabled when input empty", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={false} />);
    const btn = screen.getByTestId("owner-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("shows pending text when isPending", () => {
    render(<OwnerAssignmentDialog onClose={vi.fn()} onAssign={vi.fn()} isPending={true} />);
    expect(screen.getByTestId("owner-submit").textContent).toContain("Saving");
  });
});

// ── CreateSuccessDialog ───────────────────────────────────────────────────────

describe("CreateSuccessDialog", () => {
  it("renders create-dialog", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-dialog")).not.toBeNull();
  });

  it("renders create-customer-id input", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-customer-id")).not.toBeNull();
  });

  it("renders create-health-status select", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-health-status")).not.toBeNull();
  });

  it("renders create-risk-level select", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-risk-level")).not.toBeNull();
  });

  it("renders create-notes textarea", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-notes")).not.toBeNull();
  });

  it("renders cancel button", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-cancel")).not.toBeNull();
  });

  it("renders submit button", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    expect(screen.getByTestId("create-submit")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(<CreateSuccessDialog workspaceId={WS} onClose={onClose} onCreate={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByTestId("create-cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onCreate with customer id and workspace id", async () => {
    const onCreate = vi.fn();
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={onCreate} isPending={false} />);
    fireEvent.change(screen.getByTestId("create-customer-id"), { target: { value: "cust-999" } });
    await userEvent.click(screen.getByTestId("create-submit"));
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ customer_id: "cust-999", workspace_id: WS })
    );
  });

  it("submit disabled when customer id empty", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={false} />);
    const btn = screen.getByTestId("create-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("shows pending text when isPending", () => {
    render(<CreateSuccessDialog workspaceId={WS} onClose={vi.fn()} onCreate={vi.fn()} isPending={true} />);
    expect(screen.getByTestId("create-submit").textContent).toContain("Creating");
  });
});

// ── CustomerSuccessDrawer ──────────────────────────────────────────────────────

describe("CustomerSuccessDrawer", () => {
  beforeEach(() => { setupMutations(); });

  it("renders success-drawer", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("success-drawer")).not.toBeNull();
  });

  it("renders drawer-close button", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("drawer-close")).not.toBeNull();
  });

  it("calls onClose when drawer-close clicked", async () => {
    const onClose = vi.fn();
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={onClose} />);
    await userEvent.click(screen.getByTestId("drawer-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders health-change buttons for all statuses", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("health-change-btn-healthy")).not.toBeNull();
    expect(screen.getByTestId("health-change-btn-watch")).not.toBeNull();
    expect(screen.getByTestId("health-change-btn-at_risk")).not.toBeNull();
  });

  it("renders schedule-followup-btn", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("schedule-followup-btn")).not.toBeNull();
  });

  it("renders assign-owner-btn", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("assign-owner-btn")).not.toBeNull();
  });

  it("renders archive-btn when not archived", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.getByTestId("archive-btn")).not.toBeNull();
  });

  it("archive-btn absent when already archived", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ is_archived: true })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("archive-btn")).toBeNull();
  });

  it("shows health badge for current status", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ health_status: "at_risk" })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("health-badge-at_risk")).not.toBeNull();
  });

  it("shows risk badge for current level", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ risk_level: "high" })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("risk-badge-high")).not.toBeNull();
  });

  it("opens followup dialog on schedule-followup-btn click", async () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("schedule-followup-btn"));
    expect(screen.getByTestId("followup-dialog")).not.toBeNull();
  });

  it("opens owner dialog on assign-owner-btn click", async () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("assign-owner-btn"));
    expect(screen.getByTestId("owner-dialog")).not.toBeNull();
  });

  it("shows health score when present", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ health_score: 82 })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-score").textContent).toContain("82");
  });

  it("shows renewal date when present", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ renewal_date: "2026-12-31" })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-renewal").textContent).toContain("2026-12-31");
  });

  it("shows followup date when present", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ next_followup_date: "2026-09-01" })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-followup").textContent).toContain("2026-09-01");
  });

  it("shows notes when present", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ notes: "Enterprise" })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-notes").textContent).toContain("Enterprise");
  });

  it("shows expansion tile when expansion_opportunity", () => {
    render(
      <CustomerSuccessDrawer record={makeRecord({ expansion_opportunity: true })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-expansion")).not.toBeNull();
  });

  it("no expansion tile when false", () => {
    render(<CustomerSuccessDrawer record={makeRecord()} workspaceId={WS} onClose={vi.fn()} />);
    expect(screen.queryByTestId("drawer-expansion")).toBeNull();
  });
});

// ── CustomerSuccessCenter ──────────────────────────────────────────────────────

describe("CustomerSuccessCenter", () => {
  beforeEach(() => { setupMutations(); });

  function setupCenter(items: CustomerSuccess[] = [], hasMore = false) {
    const listOut = makeListOut(items, { has_more: hasMore, total: items.length });
    mockList.mockReturnValue(
      { data: { data: listOut }, isLoading: false, isError: false } as ReturnType<
        typeof useCustomerSuccessList
      >
    );
    return render(<CustomerSuccessCenter workspaceId={WS} />);
  }

  it("renders customer-success-center", () => {
    setupCenter();
    expect(screen.getByTestId("customer-success-center")).not.toBeNull();
  });

  it("shows loading-state while loading", () => {
    mockList.mockReturnValue(
      { data: undefined, isLoading: true, isError: false } as ReturnType<typeof useCustomerSuccessList>
    );
    render(<CustomerSuccessCenter workspaceId={WS} />);
    expect(screen.getByTestId("loading-state")).not.toBeNull();
  });

  it("shows error-state on error", () => {
    mockList.mockReturnValue(
      { data: undefined, isLoading: false, isError: true } as ReturnType<typeof useCustomerSuccessList>
    );
    render(<CustomerSuccessCenter workspaceId={WS} />);
    expect(screen.getByTestId("error-state")).not.toBeNull();
  });

  it("success-total shows correct count", () => {
    setupCenter([makeRecord(), makeRecord({ id: "r2" })]);
    expect(screen.getByTestId("success-total").textContent).toContain("2");
  });

  it("renders add-record-btn", () => {
    setupCenter();
    expect(screen.getByTestId("add-record-btn")).not.toBeNull();
  });

  it("opens create-dialog on add-record-btn click", async () => {
    setupCenter();
    await userEvent.click(screen.getByTestId("add-record-btn"));
    expect(screen.getByTestId("create-dialog")).not.toBeNull();
  });

  it("renders kpi-bar", () => {
    setupCenter([makeRecord()]);
    expect(screen.getByTestId("kpi-bar")).not.toBeNull();
  });

  it("renders filter-bar", () => {
    setupCenter();
    expect(screen.getByTestId("filter-bar")).not.toBeNull();
  });

  it("renders success-table", () => {
    setupCenter();
    expect(screen.getByTestId("success-table")).not.toBeNull();
  });

  it("shows empty-state when no records", () => {
    setupCenter([]);
    expect(screen.getByTestId("empty-state")).not.toBeNull();
  });

  it("shows load-more-btn when has_more", () => {
    setupCenter(Array.from({ length: 50 }, (_, i) => makeRecord({ id: `r${i}` })), true);
    expect(screen.getByTestId("load-more-btn")).not.toBeNull();
  });

  it("no load-more-btn when no more pages", () => {
    setupCenter([makeRecord()], false);
    expect(screen.queryByTestId("load-more-btn")).toBeNull();
  });

  it("opens drawer on row click", async () => {
    setupCenter([makeRecord()]);
    await userEvent.click(screen.getByTestId("success-row"));
    expect(screen.getByTestId("success-drawer")).not.toBeNull();
  });

  it("shows correct row count", () => {
    setupCenter([makeRecord(), makeRecord({ id: "r2", customer_id: "c2" })]);
    expect(screen.getAllByTestId("success-row").length).toBe(2);
  });

  it("search filter input is functional", () => {
    setupCenter([makeRecord()]);
    const input = screen.getByTestId("search-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "enterprise" } });
    expect(input.value).toBe("enterprise");
  });

  it("no loading-state after data loaded", () => {
    setupCenter([makeRecord()]);
    expect(screen.queryByTestId("loading-state")).toBeNull();
  });

  it("no error-state after data loaded", () => {
    setupCenter([makeRecord()]);
    expect(screen.queryByTestId("error-state")).toBeNull();
  });

  it("total is zero when empty", () => {
    setupCenter([]);
    expect(screen.getByTestId("success-total").textContent).toContain("0");
  });

  it("health filter changes value", () => {
    setupCenter([makeRecord()]);
    const sel = screen.getByTestId("health-filter") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "at_risk" } });
    expect(sel.value).toBe("at_risk");
  });
});

// ── CustomerSuccessSummary ────────────────────────────────────────────────────

describe("CustomerSuccessSummary", () => {
  it("renders customer-success-summary", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ health_status: "at_risk", risk_level: "high" }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("customer-success-summary")).not.toBeNull();
  });

  it("shows at_risk badge", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ health_status: "at_risk" }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("health-badge-at_risk")).not.toBeNull();
  });

  it("shows high risk badge", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ risk_level: "high" }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("risk-badge-high")).not.toBeNull();
  });

  it("shows loading state while loading", () => {
    mockByCustomer.mockReturnValue(
      { data: undefined, isLoading: true, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-loading")).not.toBeNull();
  });

  it("shows empty state when no record", () => {
    mockByCustomer.mockReturnValue(
      { data: undefined, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-empty")).not.toBeNull();
  });

  it("shows success-summary-card", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord() }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-card")).not.toBeNull();
  });

  it("shows health score", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ health_score: 75 }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-score").textContent).toContain("75");
  });

  it("shows renewal date", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ renewal_date: "2026-12-31" }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-renewal")).not.toBeNull();
  });

  it("shows followup date", () => {
    mockByCustomer.mockReturnValue(
      { data: { data: makeRecord({ next_followup_date: "2026-09-01" }) }, isLoading: false, isError: false } as ReturnType<typeof useCustomerSuccessByCustomer>
    );
    render(<CustomerSuccessSummary customerId="cust-1" />);
    expect(screen.getByTestId("success-summary-followup")).not.toBeNull();
  });
});
