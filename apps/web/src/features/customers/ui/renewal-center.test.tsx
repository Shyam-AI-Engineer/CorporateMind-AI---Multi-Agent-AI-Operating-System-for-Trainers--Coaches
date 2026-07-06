import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  CustomerRenewal,
  CustomerRenewalListOut,
} from "@/features/customers/types-renewal";

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

import {
  useCustomerRenewalList,
  useRenewalsByCustomer,
  useCreateCustomerRenewal,
  useUpdateCustomerRenewal,
  useAssignRenewalOwner,
  useUpdateRenewalStatus,
  useAttachProposal,
  useArchiveCustomerRenewal,
} from "@/features/customers/api/use-renewal";

const mockList = vi.mocked(useCustomerRenewalList);
const mockByCustomer = vi.mocked(useRenewalsByCustomer);
const mockCreate = vi.mocked(useCreateCustomerRenewal);
const mockUpdate = vi.mocked(useUpdateCustomerRenewal);
const mockAssignOwner = vi.mocked(useAssignRenewalOwner);
const mockUpdateStatus = vi.mocked(useUpdateRenewalStatus);
const mockAttachProposal = vi.mocked(useAttachProposal);
const mockArchive = vi.mocked(useArchiveCustomerRenewal);

const {
  StatusBadge,
  ProbabilityBadge,
  RenewalKpiBar,
  RenewalFilterBar,
  RenewalTable,
  StatusUpdateDialog,
  ProposalAttachDialog,
  RenewalDrawer,
  RenewalDialog,
  RenewalCenter,
  NextRenewalCard,
} = await import("./renewal-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS = "ws-48";

function makeRenewal(overrides: Partial<CustomerRenewal> = {}): CustomerRenewal {
  return {
    id: "ren-1",
    tenant_id: "org-1",
    workspace_id: WS,
    customer_id: "cust-1",
    contract_name: "Annual SaaS Contract",
    contract_value: "120000.00",
    renewal_type: "annual",
    renewal_status: "planned",
    renewal_date: "2027-01-01",
    owner_user_id: null,
    probability: 80,
    expected_value: "100000.00",
    proposal_id: null,
    notes: null,
    is_archived: false,
    created_at: "2026-07-07T10:00:00Z",
    updated_at: "2026-07-07T10:00:00Z",
    ...overrides,
  };
}

function makeListOut(
  items: CustomerRenewal[] = [],
  overrides: Partial<CustomerRenewalListOut> = {}
): CustomerRenewalListOut {
  return { items, next_cursor: null, has_more: false, total: items.length, ...overrides };
}

function idleMutation() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
}

function setupMutations() {
  mockCreate.mockReturnValue(idleMutation() as ReturnType<typeof useCreateCustomerRenewal>);
  mockUpdate.mockReturnValue(idleMutation() as ReturnType<typeof useUpdateCustomerRenewal>);
  mockAssignOwner.mockReturnValue(idleMutation() as ReturnType<typeof useAssignRenewalOwner>);
  mockUpdateStatus.mockReturnValue(idleMutation() as ReturnType<typeof useUpdateRenewalStatus>);
  mockAttachProposal.mockReturnValue(idleMutation() as ReturnType<typeof useAttachProposal>);
  mockArchive.mockReturnValue(idleMutation() as ReturnType<typeof useArchiveCustomerRenewal>);
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

describe("StatusBadge", () => {
  it("renders planned badge", () => {
    render(<StatusBadge status="planned" />);
    expect(screen.getByTestId("status-badge-planned")).not.toBeNull();
  });

  it("renders in_progress badge", () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByTestId("status-badge-in_progress")).not.toBeNull();
  });

  it("renders negotiation badge", () => {
    render(<StatusBadge status="negotiation" />);
    expect(screen.getByTestId("status-badge-negotiation")).not.toBeNull();
  });

  it("renders won badge", () => {
    render(<StatusBadge status="won" />);
    expect(screen.getByTestId("status-badge-won")).not.toBeNull();
  });

  it("renders lost badge", () => {
    render(<StatusBadge status="lost" />);
    expect(screen.getByTestId("status-badge-lost")).not.toBeNull();
  });

  it("renders cancelled badge", () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByTestId("status-badge-cancelled")).not.toBeNull();
  });

  it("planned badge has label text", () => {
    render(<StatusBadge status="planned" />);
    expect(screen.getByTestId("status-badge-planned").textContent).toContain("planned");
  });

  it("in_progress badge replaces underscore", () => {
    render(<StatusBadge status="in_progress" />);
    const text = screen.getByTestId("status-badge-in_progress").textContent ?? "";
    expect(text).toContain("in progress");
  });

  it("won badge text is won", () => {
    render(<StatusBadge status="won" />);
    expect(screen.getByTestId("status-badge-won").textContent).toContain("won");
  });
});

// ── ProbabilityBadge ──────────────────────────────────────────────────────────

describe("ProbabilityBadge", () => {
  it("renders null as em-dash", () => {
    render(<ProbabilityBadge probability={null} />);
    expect(screen.getByTestId("probability-badge-null")).not.toBeNull();
  });

  it("renders 80 percent", () => {
    render(<ProbabilityBadge probability={80} />);
    expect(screen.getByTestId("probability-badge-80").textContent).toContain("80%");
  });

  it("renders 0 percent", () => {
    render(<ProbabilityBadge probability={0} />);
    expect(screen.getByTestId("probability-badge-0").textContent).toContain("0%");
  });

  it("renders 100 percent", () => {
    render(<ProbabilityBadge probability={100} />);
    expect(screen.getByTestId("probability-badge-100").textContent).toContain("100%");
  });

  it("high probability uses green color class", () => {
    render(<ProbabilityBadge probability={75} />);
    const el = screen.getByTestId("probability-badge-75");
    expect(el.className).toContain("green");
  });

  it("medium probability uses yellow color class", () => {
    render(<ProbabilityBadge probability={50} />);
    const el = screen.getByTestId("probability-badge-50");
    expect(el.className).toContain("yellow");
  });

  it("low probability uses red color class", () => {
    render(<ProbabilityBadge probability={20} />);
    const el = screen.getByTestId("probability-badge-20");
    expect(el.className).toContain("red");
  });

  it("probability at threshold 75 is green", () => {
    render(<ProbabilityBadge probability={75} />);
    expect(screen.getByTestId("probability-badge-75").className).toContain("green");
  });

  it("probability at threshold 40 is yellow", () => {
    render(<ProbabilityBadge probability={40} />);
    expect(screen.getByTestId("probability-badge-40").className).toContain("yellow");
  });
});

// ── RenewalKpiBar ─────────────────────────────────────────────────────────────

describe("RenewalKpiBar", () => {
  it("renders kpi bar", () => {
    render(<RenewalKpiBar items={[]} />);
    expect(screen.getByTestId("renewal-kpi-bar")).not.toBeNull();
  });

  it("shows zero values for empty items", () => {
    render(<RenewalKpiBar items={[]} />);
    expect(screen.getByTestId("kpi-due-soon").textContent).toBe("0");
    expect(screen.getByTestId("kpi-won").textContent).toBe("0");
    expect(screen.getByTestId("kpi-lost").textContent).toBe("0");
  });

  it("counts renewals due when renewal_date present", () => {
    const items = [
      makeRenewal({ renewal_date: "2027-01-01" }),
      makeRenewal({ id: "ren-2", renewal_date: "2027-06-01" }),
      makeRenewal({ id: "ren-3", renewal_date: null }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-due-soon").textContent).toBe("2");
  });

  it("aggregates pipeline value", () => {
    const items = [
      makeRenewal({ contract_value: "100000.00" }),
      makeRenewal({ id: "ren-2", contract_value: "50000.00" }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-pipeline-value").textContent).toContain("150");
  });

  it("aggregates expected revenue", () => {
    const items = [
      makeRenewal({ expected_value: "80000.00" }),
      makeRenewal({ id: "ren-2", expected_value: "20000.00" }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-expected-revenue").textContent).toContain("100");
  });

  it("counts won renewals", () => {
    const items = [
      makeRenewal({ renewal_status: "won" }),
      makeRenewal({ id: "ren-2", renewal_status: "won" }),
      makeRenewal({ id: "ren-3", renewal_status: "lost" }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-won").textContent).toBe("2");
  });

  it("counts in-progress renewals (in_progress + negotiation)", () => {
    const items = [
      makeRenewal({ renewal_status: "in_progress" }),
      makeRenewal({ id: "ren-2", renewal_status: "negotiation" }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-in-progress").textContent).toBe("2");
  });

  it("counts lost renewals", () => {
    const items = [
      makeRenewal({ renewal_status: "lost" }),
    ];
    render(<RenewalKpiBar items={items} />);
    expect(screen.getByTestId("kpi-lost").textContent).toBe("1");
  });
});

// ── RenewalFilterBar ──────────────────────────────────────────────────────────

describe("RenewalFilterBar", () => {
  it("renders filter bar", () => {
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={vi.fn()}
        onType={vi.fn()}
      />
    );
    expect(screen.getByTestId("renewal-filter-bar")).not.toBeNull();
  });

  it("calls onSearch when input changes", async () => {
    const onSearch = vi.fn();
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={onSearch}
        onStatus={vi.fn()}
        onType={vi.fn()}
      />
    );
    await userEvent.type(screen.getByTestId("renewal-search-input"), "Q4");
    expect(onSearch).toHaveBeenCalled();
  });

  it("calls onStatus when status filter changes", async () => {
    const onStatus = vi.fn();
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={onStatus}
        onType={vi.fn()}
      />
    );
    await userEvent.selectOptions(screen.getByTestId("renewal-status-filter"), "won");
    expect(onStatus).toHaveBeenCalledWith("won");
  });

  it("calls onType when type filter changes", async () => {
    const onType = vi.fn();
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={vi.fn()}
        onType={onType}
      />
    );
    await userEvent.selectOptions(screen.getByTestId("renewal-type-filter"), "quarterly");
    expect(onType).toHaveBeenCalledWith("quarterly");
  });

  it("displays current search value", () => {
    render(
      <RenewalFilterBar
        search="my search"
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={vi.fn()}
        onType={vi.fn()}
      />
    );
    const input = screen.getByTestId("renewal-search-input") as HTMLInputElement;
    expect(input.value).toBe("my search");
  });

  it("displays all status options", () => {
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={vi.fn()}
        onType={vi.fn()}
      />
    );
    const sel = screen.getByTestId("renewal-status-filter") as HTMLSelectElement;
    const optionValues = Array.from(sel.options).map((o) => o.value);
    expect(optionValues).toContain("planned");
    expect(optionValues).toContain("won");
    expect(optionValues).toContain("lost");
    expect(optionValues).toContain("cancelled");
  });

  it("displays all type options", () => {
    render(
      <RenewalFilterBar
        search=""
        status=""
        type=""
        onSearch={vi.fn()}
        onStatus={vi.fn()}
        onType={vi.fn()}
      />
    );
    const sel = screen.getByTestId("renewal-type-filter") as HTMLSelectElement;
    const optionValues = Array.from(sel.options).map((o) => o.value);
    expect(optionValues).toContain("annual");
    expect(optionValues).toContain("quarterly");
    expect(optionValues).toContain("monthly");
    expect(optionValues).toContain("custom");
  });
});

// ── RenewalTable ──────────────────────────────────────────────────────────────

describe("RenewalTable", () => {
  it("renders table", () => {
    render(<RenewalTable records={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("renewal-table")).not.toBeNull();
  });

  it("shows empty state when no records", () => {
    render(<RenewalTable records={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("renewal-empty-state")).not.toBeNull();
  });

  it("renders rows for each record", () => {
    const records = [
      makeRenewal(),
      makeRenewal({ id: "ren-2", contract_name: "Q4 Contract" }),
    ];
    render(<RenewalTable records={records} onSelect={vi.fn()} />);
    expect(screen.getAllByTestId("renewal-row")).toHaveLength(2);
  });

  it("calls onSelect when row clicked", async () => {
    const onSelect = vi.fn();
    const record = makeRenewal();
    render(<RenewalTable records={[record]} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId("renewal-row"));
    expect(onSelect).toHaveBeenCalledWith(record);
  });

  it("displays contract name in row", () => {
    const record = makeRenewal({ contract_name: "Enterprise Deal" });
    render(<RenewalTable records={[record]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-contract-name").textContent).toContain("Enterprise Deal");
  });

  it("shows dash for null contract name", () => {
    render(<RenewalTable records={[makeRenewal({ contract_name: null })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-contract-name").textContent).toBe("—");
  });

  it("displays renewal type in row", () => {
    render(<RenewalTable records={[makeRenewal({ renewal_type: "quarterly" })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-type").textContent).toBe("quarterly");
  });

  it("displays renewal date in row", () => {
    render(<RenewalTable records={[makeRenewal({ renewal_date: "2027-06-01" })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-renewal-date").textContent).toBe("2027-06-01");
  });

  it("shows dash for null renewal date", () => {
    render(<RenewalTable records={[makeRenewal({ renewal_date: null })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-renewal-date").textContent).toBe("—");
  });

  it("shows status badge in row", () => {
    render(<RenewalTable records={[makeRenewal({ renewal_status: "won" })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("status-badge-won")).not.toBeNull();
  });

  it("shows probability badge in row", () => {
    render(<RenewalTable records={[makeRenewal({ probability: 85 })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("probability-badge-85")).not.toBeNull();
  });

  it("displays contract value formatted", () => {
    render(<RenewalTable records={[makeRenewal({ contract_value: "50000.00" })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-value").textContent).toContain("50");
  });

  it("shows dash for null contract value", () => {
    render(<RenewalTable records={[makeRenewal({ contract_value: null })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("row-value").textContent).toBe("—");
  });
});

// ── StatusUpdateDialog ────────────────────────────────────────────────────────

describe("StatusUpdateDialog", () => {
  it("renders dialog", () => {
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        isPending={false}
      />
    );
    expect(screen.getByTestId("status-update-dialog")).not.toBeNull();
  });

  it("shows current status pre-selected", () => {
    render(
      <StatusUpdateDialog
        currentStatus="negotiation"
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        isPending={false}
      />
    );
    const sel = screen.getByTestId("status-select") as HTMLSelectElement;
    expect(sel.value).toBe("negotiation");
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={onClose}
        onUpdate={vi.fn()}
        isPending={false}
      />
    );
    await userEvent.click(screen.getByTestId("status-cancel"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onUpdate with selected status when submit clicked", async () => {
    const onUpdate = vi.fn();
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={vi.fn()}
        onUpdate={onUpdate}
        isPending={false}
      />
    );
    await userEvent.selectOptions(screen.getByTestId("status-select"), "won");
    await userEvent.click(screen.getByTestId("status-submit"));
    expect(onUpdate).toHaveBeenCalledWith("won");
  });

  it("submit button is disabled when isPending", () => {
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        isPending={true}
      />
    );
    const btn = screen.getByTestId("status-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit button shows saving when pending", () => {
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        isPending={true}
      />
    );
    expect(screen.getByTestId("status-submit").textContent).toContain("Saving");
  });

  it("submit button shows Update when not pending", () => {
    render(
      <StatusUpdateDialog
        currentStatus="planned"
        onClose={vi.fn()}
        onUpdate={vi.fn()}
        isPending={false}
      />
    );
    expect(screen.getByTestId("status-submit").textContent).toContain("Update");
  });
});

// ── ProposalAttachDialog ──────────────────────────────────────────────────────

describe("ProposalAttachDialog", () => {
  it("renders dialog", () => {
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={vi.fn()} isPending={false} />
    );
    expect(screen.getByTestId("proposal-attach-dialog")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(<ProposalAttachDialog onClose={onClose} onAttach={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByTestId("proposal-cancel"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("submit button disabled when input empty", () => {
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={vi.fn()} isPending={false} />
    );
    const btn = screen.getByTestId("proposal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit button enabled when input has value", async () => {
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={vi.fn()} isPending={false} />
    );
    await userEvent.type(screen.getByTestId("proposal-id-input"), "some-uuid");
    const btn = screen.getByTestId("proposal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("calls onAttach with trimmed proposal id", async () => {
    const onAttach = vi.fn();
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={onAttach} isPending={false} />
    );
    await userEvent.type(screen.getByTestId("proposal-id-input"), "  my-proposal-id  ");
    await userEvent.click(screen.getByTestId("proposal-submit"));
    expect(onAttach).toHaveBeenCalledWith("my-proposal-id");
  });

  it("submit shows Attaching when pending", () => {
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={vi.fn()} isPending={true} />
    );
    expect(screen.getByTestId("proposal-submit").textContent).toContain("Attaching");
  });

  it("submit shows Attach when not pending", () => {
    render(
      <ProposalAttachDialog onClose={vi.fn()} onAttach={vi.fn()} isPending={false} />
    );
    expect(screen.getByTestId("proposal-submit").textContent).toContain("Attach");
  });
});

// ── RenewalDrawer ─────────────────────────────────────────────────────────────

describe("RenewalDrawer", () => {
  beforeEach(() => {
    setupMutations();
  });

  it("renders drawer", () => {
    render(
      <RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("renewal-drawer")).not.toBeNull();
  });

  it("shows contract name in header", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ contract_name: "My Contract" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-contract-name").textContent).toContain("My Contract");
  });

  it("shows Renewal when contract_name is null", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ contract_name: null })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-contract-name").textContent).toContain("Renewal");
  });

  it("calls onClose when close button clicked", async () => {
    const onClose = vi.fn();
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={onClose} />);
    await userEvent.click(screen.getByTestId("renewal-drawer-close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows renewal type", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ renewal_type: "quarterly" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-renewal-type").textContent).toBe("quarterly");
  });

  it("shows renewal date when present", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ renewal_date: "2027-06-30" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-renewal-date").textContent).toBe("2027-06-30");
  });

  it("hides renewal date when null", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ renewal_date: null })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByTestId("drawer-renewal-date")).toBeNull();
  });

  it("shows contract value when present", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ contract_value: "75000.00" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-contract-value").textContent).toContain("75");
  });

  it("hides contract value when null", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ contract_value: null })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByTestId("drawer-contract-value")).toBeNull();
  });

  it("shows expected value when present", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ expected_value: "60000.00" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-expected-value").textContent).toContain("60");
  });

  it("shows proposal id when present", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ proposal_id: "abc12345-def6-7890-abcd-ef1234567890" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-proposal-id")).not.toBeNull();
  });

  it("shows notes when present", () => {
    render(
      <RenewalDrawer
        record={makeRenewal({ notes: "Important renewal" })}
        workspaceId={WS}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("drawer-notes").textContent).toContain("Important renewal");
  });

  it("shows archive button for non-archived record", () => {
    render(
      <RenewalDrawer record={makeRenewal({ is_archived: false })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("renewal-archive-btn")).not.toBeNull();
  });

  it("hides archive button for archived record", () => {
    render(
      <RenewalDrawer record={makeRenewal({ is_archived: true })} workspaceId={WS} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("renewal-archive-btn")).toBeNull();
  });

  it("calls archive mutate when archive btn clicked", async () => {
    const mutateFn = vi.fn();
    mockArchive.mockReturnValue({ mutate: mutateFn, mutateAsync: vi.fn(), isPending: false } as ReturnType<typeof useArchiveCustomerRenewal>);
    const record = makeRenewal();
    render(<RenewalDrawer record={record} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("renewal-archive-btn"));
    expect(mutateFn).toHaveBeenCalledWith(record.id);
  });

  it("shows status update dialog when button clicked", async () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("update-status-btn"));
    expect(screen.getByTestId("status-update-dialog")).not.toBeNull();
  });

  it("shows proposal attach dialog when button clicked", async () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("attach-proposal-btn"));
    expect(screen.getByTestId("proposal-attach-dialog")).not.toBeNull();
  });

  it("assign owner button disabled when owner input empty", () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    const btn = screen.getByTestId("drawer-assign-owner-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("assign owner button enabled when input filled", async () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId("drawer-owner-input"), "user-uuid-123");
    const btn = screen.getByTestId("drawer-assign-owner-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("status dialog closed after cancel", async () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("update-status-btn"));
    expect(screen.getByTestId("status-update-dialog")).not.toBeNull();
    await userEvent.click(screen.getByTestId("status-cancel"));
    expect(screen.queryByTestId("status-update-dialog")).toBeNull();
  });

  it("proposal dialog closed after cancel", async () => {
    render(<RenewalDrawer record={makeRenewal()} workspaceId={WS} onClose={vi.fn()} />);
    await userEvent.click(screen.getByTestId("attach-proposal-btn"));
    await userEvent.click(screen.getByTestId("proposal-cancel"));
    expect(screen.queryByTestId("proposal-attach-dialog")).toBeNull();
  });
});

// ── RenewalDialog ─────────────────────────────────────────────────────────────

describe("RenewalDialog", () => {
  it("renders dialog", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    expect(screen.getByTestId("renewal-dialog")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    const onClose = vi.fn();
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={onClose}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    await userEvent.click(screen.getByTestId("renewal-cancel"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("submit disabled when customer_id empty", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    const btn = screen.getByTestId("renewal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("submit enabled when customer_id filled", async () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    await userEvent.type(screen.getByTestId("renewal-customer-id"), "cust-abc");
    const btn = screen.getByTestId("renewal-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("pre-fills customer_id when provided", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        customerId="cust-123"
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    const input = screen.getByTestId("renewal-customer-id") as HTMLInputElement;
    expect(input.value).toBe("cust-123");
  });

  it("calls onCreate with form data on submit", async () => {
    const onCreate = vi.fn();
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={onCreate}
        isPending={false}
      />
    );
    await userEvent.type(screen.getByTestId("renewal-customer-id"), "cust-xyz");
    await userEvent.type(screen.getByTestId("renewal-contract-name"), "My Deal");
    await userEvent.click(screen.getByTestId("renewal-submit"));
    expect(onCreate).toHaveBeenCalledOnce();
    const arg = onCreate.mock.calls[0][0];
    expect(arg.customer_id).toBe("cust-xyz");
    expect(arg.contract_name).toBe("My Deal");
    expect(arg.workspace_id).toBe(WS);
  });

  it("shows Creating when pending", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={true}
      />
    );
    expect(screen.getByTestId("renewal-submit").textContent).toContain("Creating");
  });

  it("shows Create when not pending", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    expect(screen.getByTestId("renewal-submit").textContent).toContain("Create");
  });

  it("renewal type defaults to annual", () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    const sel = screen.getByTestId("renewal-type-select") as HTMLSelectElement;
    expect(sel.value).toBe("annual");
  });

  it("can change renewal type", async () => {
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        isPending={false}
      />
    );
    await userEvent.selectOptions(screen.getByTestId("renewal-type-select"), "quarterly");
    const sel = screen.getByTestId("renewal-type-select") as HTMLSelectElement;
    expect(sel.value).toBe("quarterly");
  });

  it("sets probability in create payload", async () => {
    const onCreate = vi.fn();
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={onCreate}
        isPending={false}
      />
    );
    await userEvent.type(screen.getByTestId("renewal-customer-id"), "cust-1");
    await userEvent.type(screen.getByTestId("renewal-probability-input"), "85");
    await userEvent.click(screen.getByTestId("renewal-submit"));
    expect(onCreate.mock.calls[0][0].probability).toBe(85);
  });

  it("sets notes in create payload", async () => {
    const onCreate = vi.fn();
    render(
      <RenewalDialog
        workspaceId={WS}
        onClose={vi.fn()}
        onCreate={onCreate}
        isPending={false}
      />
    );
    await userEvent.type(screen.getByTestId("renewal-customer-id"), "cust-1");
    await userEvent.type(screen.getByTestId("renewal-notes"), "test notes");
    await userEvent.click(screen.getByTestId("renewal-submit"));
    expect(onCreate.mock.calls[0][0].notes).toBe("test notes");
  });
});

// ── RenewalCenter ─────────────────────────────────────────────────────────────

describe("RenewalCenter", () => {
  beforeEach(() => {
    setupMutations();
  });

  it("renders center", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut() },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-center")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockList.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockList.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-error")).not.toBeNull();
  });

  it("shows total count in header", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeRenewal(), makeRenewal({ id: "ren-2" })], { total: 2 }) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-total").textContent).toContain("2");
  });

  it("shows table with records", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeRenewal()]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getAllByTestId("renewal-row")).toHaveLength(1);
  });

  it("shows empty state when no records", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-empty-state")).not.toBeNull();
  });

  it("shows load more button when has_more", () => {
    const items = Array.from({ length: 3 }, (_, i) => makeRenewal({ id: `ren-${i}` }));
    mockList.mockReturnValue({
      data: { data: makeListOut(items, { has_more: true, next_cursor: "cursor-abc" }) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-load-more")).not.toBeNull();
  });

  it("hides load more button when has_more false", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeRenewal()]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.queryByTestId("renewal-load-more")).toBeNull();
  });

  it("opens create dialog when New renewal btn clicked", async () => {
    mockList.mockReturnValue({
      data: { data: makeListOut() },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("add-renewal-btn"));
    expect(screen.getByTestId("renewal-dialog")).not.toBeNull();
  });

  it("opens drawer when row clicked", async () => {
    const record = makeRenewal();
    mockList.mockReturnValue({
      data: { data: makeListOut([record]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("renewal-row"));
    expect(screen.getByTestId("renewal-drawer")).not.toBeNull();
  });

  it("closes drawer when close clicked", async () => {
    const record = makeRenewal();
    mockList.mockReturnValue({
      data: { data: makeListOut([record]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("renewal-row"));
    await userEvent.click(screen.getByTestId("renewal-drawer-close"));
    expect(screen.queryByTestId("renewal-drawer")).toBeNull();
  });

  it("renders kpi bar", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut() },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-kpi-bar")).not.toBeNull();
  });

  it("renders filter bar", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut() },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-filter-bar")).not.toBeNull();
  });

  it("singular label when total is 1", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeRenewal()], { total: 1 }) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-total").textContent).toBe("1 renewal");
  });

  it("plural label when total is 0", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([], { total: 0 }) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCustomerRenewalList>);
    render(<RenewalCenter workspaceId={WS} />);
    expect(screen.getByTestId("renewal-total").textContent).toBe("0 renewals");
  });
});

// ── NextRenewalCard ───────────────────────────────────────────────────────────

describe("NextRenewalCard", () => {
  beforeEach(() => {
    setupMutations();
  });

  it("renders card container", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut() },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-card")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockByCustomer.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-loading")).not.toBeNull();
  });

  it("shows empty state when no active renewals", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_status: "won" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-empty")).not.toBeNull();
  });

  it("shows summary for active renewal", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_status: "planned" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-summary")).not.toBeNull();
  });

  it("shows in_progress renewal as next", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_status: "in_progress" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-summary")).not.toBeNull();
  });

  it("shows negotiation renewal as next", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_status: "negotiation" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-summary")).not.toBeNull();
  });

  it("skips won/lost/cancelled for next renewal", () => {
    mockByCustomer.mockReturnValue({
      data: {
        data: makeListOut([
          makeRenewal({ renewal_status: "won" }),
          makeRenewal({ id: "ren-2", renewal_status: "lost" }),
          makeRenewal({ id: "ren-3", renewal_status: "cancelled" }),
        ]),
      },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-empty")).not.toBeNull();
  });

  it("shows contract name in summary", () => {
    mockByCustomer.mockReturnValue({
      data: {
        data: makeListOut([makeRenewal({ contract_name: "Enterprise 2027", renewal_status: "planned" })]),
      },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-contract").textContent).toContain("Enterprise 2027");
  });

  it("shows renewal date in summary", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_date: "2027-03-15", renewal_status: "planned" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-date").textContent).toBe("2027-03-15");
  });

  it("shows probability in summary", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ probability: 72, renewal_status: "planned" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-probability").textContent).toContain("72");
  });

  it("shows expected value in summary", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ expected_value: "90000.00", renewal_status: "planned" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-expected-value").textContent).toContain("90");
  });

  it("shows renewal type in summary", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_type: "quarterly", renewal_status: "in_progress" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-type").textContent).toBe("quarterly");
  });

  it("shows status badge in summary", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeRenewal({ renewal_status: "negotiation" })]) },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("status-badge-negotiation")).not.toBeNull();
  });

  it("picks first active renewal when multiple exist", () => {
    mockByCustomer.mockReturnValue({
      data: {
        data: makeListOut([
          makeRenewal({ id: "ren-1", renewal_status: "won", contract_name: "Old" }),
          makeRenewal({ id: "ren-2", renewal_status: "planned", contract_name: "Next" }),
        ]),
      },
      isLoading: false,
    } as ReturnType<typeof useRenewalsByCustomer>);
    render(<NextRenewalCard customerId="cust-1" workspaceId={WS} />);
    expect(screen.getByTestId("next-renewal-contract").textContent).toContain("Next");
  });
});
