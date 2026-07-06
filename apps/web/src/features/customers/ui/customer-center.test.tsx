import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CustomerCenter, CustomerStatusBadge, CustomerHealthBadge } from "./customer-center";

// ── Mock hooks ────────────────────────────────────────────────────────────────

vi.mock("@/features/customers/api/use-customers", () => ({
  useCustomers: vi.fn(),
  useCustomer: vi.fn(),
  useCreateCustomer: vi.fn(),
  useUpdateCustomer: vi.fn(),
  useArchiveCustomer: vi.fn(),
  useAssignOwner: vi.fn(),
  useUpdateCustomerHealth: vi.fn(),
}));

vi.mock("@/features/training/api/use-training", () => ({
  useCustomerFeedback: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
}));

vi.mock("@/features/customers/api/use-customer-success", () => ({
  useCustomerSuccessByCustomer: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useCustomerSuccessList: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useCreateCustomerSuccess: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateCustomerSuccess: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAssignSuccessOwner: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateSuccessHealth: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useScheduleFollowup: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useArchiveCustomerSuccess: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

import {
  useCustomers,
  useCreateCustomer,
  useUpdateCustomer,
  useArchiveCustomer,
  useAssignOwner,
  useUpdateCustomerHealth,
} from "@/features/customers/api/use-customers";
import type { Customer } from "@/features/customers/types";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const C1: Customer = {
  id: "cid-1",
  tenant_id: "org-1",
  workspace_id: "ws-1",
  company_name: "Acme Corp",
  display_name: "Acme",
  industry: "SaaS",
  website: "https://acme.com",
  email: "info@acme.com",
  phone: null,
  address: null,
  city: "Mumbai",
  state: null,
  country: "India",
  postal_code: null,
  company_size: "50-200",
  annual_revenue_inr: "5000000",
  status: "active",
  health_status: "healthy",
  relationship_owner_id: null,
  primary_contact_name: "Jane Doe",
  primary_contact_email: "jane@acme.com",
  primary_contact_phone: null,
  notes: "VIP customer",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
};

const C2: Customer = {
  ...C1,
  id: "cid-2",
  company_name: "Beta Inc",
  display_name: "Beta",
  industry: "Finance",
  status: "prospect",
  health_status: "at_risk",
  primary_contact_name: null,
  notes: null,
};

const C3_INACTIVE: Customer = {
  ...C1,
  id: "cid-3",
  display_name: "Gamma",
  status: "inactive",
  health_status: "inactive",
};

const LIST_OUT = {
  items: [C1, C2],
  next_cursor: null,
  has_more: false,
  total: 2,
};

const LIST_OUT_WITH_MORE = {
  items: [C1],
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

  vi.mocked(useCustomers).mockReturnValue({
    data: listData ? { data: listData } : undefined,
    isLoading: loading,
    isError: error,
  } as ReturnType<typeof useCustomers>);

  vi.mocked(useCreateCustomer).mockReturnValue({
    mutate: NOOP_MUTATE,
    isPending: false,
  } as ReturnType<typeof useCreateCustomer>);

  vi.mocked(useUpdateCustomer).mockReturnValue({
    mutate: NOOP_MUTATE,
    isPending: false,
  } as ReturnType<typeof useUpdateCustomer>);

  vi.mocked(useArchiveCustomer).mockReturnValue({
    mutate: NOOP_MUTATE,
    isPending: false,
  } as ReturnType<typeof useArchiveCustomer>);

  vi.mocked(useAssignOwner).mockReturnValue({
    mutate: NOOP_MUTATE,
    isPending: false,
  } as ReturnType<typeof useAssignOwner>);

  vi.mocked(useUpdateCustomerHealth).mockReturnValue({
    mutate: NOOP_MUTATE,
    isPending: false,
  } as ReturnType<typeof useUpdateCustomerHealth>);
}

const WS = "ws-1";

function renderCenter() {
  return render(<CustomerCenter workspaceId={WS} />);
}

// ─────────────────────────────────────────────────────────────────────────────

describe("CustomerStatusBadge", () => {
  it("renders active badge", () => {
    render(<CustomerStatusBadge status="active" />);
    expect(screen.getByTestId("status-badge-active")).toBeTruthy();
    expect(screen.getByText("active")).toBeTruthy();
  });

  it("renders inactive badge", () => {
    render(<CustomerStatusBadge status="inactive" />);
    expect(screen.getByTestId("status-badge-inactive")).toBeTruthy();
  });

  it("renders prospect badge", () => {
    render(<CustomerStatusBadge status="prospect" />);
    expect(screen.getByTestId("status-badge-prospect")).toBeTruthy();
  });

  it("renders former badge", () => {
    render(<CustomerStatusBadge status="former" />);
    expect(screen.getByTestId("status-badge-former")).toBeTruthy();
  });
});

describe("CustomerHealthBadge", () => {
  it("renders healthy badge", () => {
    render(<CustomerHealthBadge health="healthy" />);
    expect(screen.getByTestId("health-badge-healthy")).toBeTruthy();
    expect(screen.getByText("healthy")).toBeTruthy();
  });

  it("renders attention badge", () => {
    render(<CustomerHealthBadge health="attention" />);
    expect(screen.getByTestId("health-badge-attention")).toBeTruthy();
  });

  it("renders at_risk badge with space", () => {
    render(<CustomerHealthBadge health="at_risk" />);
    expect(screen.getByTestId("health-badge-at_risk")).toBeTruthy();
    expect(screen.getByText("at risk")).toBeTruthy();
  });

  it("renders inactive health badge", () => {
    render(<CustomerHealthBadge health="inactive" />);
    expect(screen.getByTestId("health-badge-inactive")).toBeTruthy();
  });
});

describe("CustomerCenter — loading state", () => {
  beforeEach(() => mockAll({ loading: true }));

  it("renders loading indicator", () => {
    renderCenter();
    expect(screen.getByTestId("loading-state")).toBeTruthy();
  });

  it("does not render table while loading", () => {
    renderCenter();
    expect(screen.queryByTestId("customer-table")).toBeNull();
  });
});

describe("CustomerCenter — error state", () => {
  beforeEach(() => mockAll({ error: true }));

  it("renders error message", () => {
    renderCenter();
    expect(screen.getByTestId("error-state")).toBeTruthy();
  });
});

describe("CustomerCenter — empty state", () => {
  beforeEach(() => mockAll({ listOut: EMPTY_LIST }));

  it("renders empty state message", () => {
    renderCenter();
    expect(screen.getByTestId("empty-state")).toBeTruthy();
  });

  it("shows 0 customers in total", () => {
    renderCenter();
    expect(screen.getByTestId("customer-total").textContent).toContain("0");
  });

  it("KPI section shows all zeros", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-active").textContent).toBe("0");
    expect(screen.getByTestId("kpi-prospects").textContent).toBe("0");
    expect(screen.getByTestId("kpi-at-risk").textContent).toBe("0");
    expect(screen.getByTestId("kpi-healthy").textContent).toBe("0");
  });
});

describe("CustomerCenter — data state", () => {
  beforeEach(() => mockAll());

  it("renders customer center container", () => {
    renderCenter();
    expect(screen.getByTestId("customer-center")).toBeTruthy();
  });

  it("renders the customers heading", () => {
    renderCenter();
    expect(screen.getByText("Customers")).toBeTruthy();
  });

  it("shows total customer count", () => {
    renderCenter();
    expect(screen.getByTestId("customer-total").textContent).toContain("2");
  });

  it("renders customer table", () => {
    renderCenter();
    expect(screen.getByTestId("customer-table")).toBeTruthy();
  });

  it("renders first customer row", () => {
    renderCenter();
    expect(screen.getByTestId("customer-row-cid-1")).toBeTruthy();
  });

  it("renders second customer row", () => {
    renderCenter();
    expect(screen.getByTestId("customer-row-cid-2")).toBeTruthy();
  });

  it("shows display name in table", () => {
    renderCenter();
    expect(screen.getByText("Acme")).toBeTruthy();
    expect(screen.getByText("Beta")).toBeTruthy();
  });

  it("shows industry in table", () => {
    renderCenter();
    expect(screen.getByText("SaaS")).toBeTruthy();
    expect(screen.getByText("Finance")).toBeTruthy();
  });

  it("shows primary contact name", () => {
    renderCenter();
    expect(screen.getByText("Jane Doe")).toBeTruthy();
  });
});

describe("CustomerCenter — KPI counts", () => {
  beforeEach(() => mockAll({ listOut: { ...LIST_OUT, items: [C1, C2, C3_INACTIVE] } }));

  it("counts active customers correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-active").textContent).toBe("1");
  });

  it("counts prospects correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-prospects").textContent).toBe("1");
  });

  it("counts at-risk correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-at-risk").textContent).toBe("1");
  });

  it("counts healthy correctly", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-healthy").textContent).toBe("1");
  });
});

describe("CustomerCenter — add customer button", () => {
  beforeEach(() => mockAll());

  it("renders add customer button", () => {
    renderCenter();
    expect(screen.getByTestId("add-customer-btn")).toBeTruthy();
  });

  it("opens create dialog on click", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    expect(screen.getByTestId("create-dialog")).toBeTruthy();
  });

  it("create dialog has company name field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    expect(screen.getByTestId("create-company-name")).toBeTruthy();
  });

  it("create dialog has display name field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    expect(screen.getByTestId("create-display-name")).toBeTruthy();
  });

  it("create dialog has industry field", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    expect(screen.getByTestId("create-industry")).toBeTruthy();
  });

  it("cancel button closes dialog", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    fireEvent.click(screen.getByTestId("create-cancel"));
    expect(screen.queryByTestId("create-dialog")).toBeNull();
  });

  it("submit button is disabled when fields empty", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    const submit = screen.getByTestId("create-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("submit button enables when both required fields filled", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    fireEvent.change(screen.getByTestId("create-company-name"), { target: { value: "NewCo" } });
    fireEvent.change(screen.getByTestId("create-display-name"), { target: { value: "New" } });
    const submit = screen.getByTestId("create-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });

  it("submitting calls createMut.mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("add-customer-btn"));
    fireEvent.change(screen.getByTestId("create-company-name"), { target: { value: "NewCo" } });
    fireEvent.change(screen.getByTestId("create-display-name"), { target: { value: "New" } });
    fireEvent.submit(screen.getByTestId("create-submit").closest("form")!);
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });
});

describe("CustomerCenter — filters", () => {
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

  it("renders health select", () => {
    renderCenter();
    expect(screen.getByTestId("health-select")).toBeTruthy();
  });

  it("status select has all status options", () => {
    renderCenter();
    const sel = screen.getByTestId("status-select") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("active");
    expect(values).toContain("inactive");
    expect(values).toContain("prospect");
    expect(values).toContain("former");
  });

  it("health select has all health options", () => {
    renderCenter();
    const sel = screen.getByTestId("health-select") as HTMLSelectElement;
    const values = Array.from(sel.options).map((o) => o.value);
    expect(values).toContain("healthy");
    expect(values).toContain("attention");
    expect(values).toContain("at_risk");
    expect(values).toContain("inactive");
  });

  it("typing in search updates input value", () => {
    renderCenter();
    const input = screen.getByTestId("search-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "acme" } });
    expect(input.value).toBe("acme");
  });

  it("selecting status updates select", () => {
    renderCenter();
    const sel = screen.getByTestId("status-select") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "active" } });
    expect(sel.value).toBe("active");
  });

  it("selecting health updates select", () => {
    renderCenter();
    const sel = screen.getByTestId("health-select") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "at_risk" } });
    expect(sel.value).toBe("at_risk");
  });
});

describe("CustomerCenter — pagination", () => {
  it("load more button appears when has_more is true", () => {
    mockAll({ listOut: LIST_OUT_WITH_MORE });
    renderCenter();
    expect(screen.getByTestId("load-more-btn")).toBeTruthy();
  });

  it("load more button hidden when no more pages", () => {
    mockAll({ listOut: LIST_OUT });
    renderCenter();
    expect(screen.queryByTestId("load-more-btn")).toBeNull();
  });

  it("clicking load more triggers refetch (cursor set)", () => {
    mockAll({ listOut: LIST_OUT_WITH_MORE });
    renderCenter();
    fireEvent.click(screen.getByTestId("load-more-btn"));
    // After clicking, useCustomers is called with new cursor
    expect(vi.mocked(useCustomers)).toHaveBeenCalled();
  });
});

describe("CustomerCenter — detail drawer", () => {
  beforeEach(() => mockAll());

  it("drawer hidden initially", () => {
    renderCenter();
    expect(screen.queryByTestId("detail-drawer")).toBeNull();
  });

  it("clicking row opens drawer", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("detail-drawer")).toBeTruthy();
  });

  it("drawer shows company name", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("drawer-company-name").textContent).toBe("Acme");
  });

  it("drawer shows industry", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("drawer-industry").textContent).toBe("SaaS");
  });

  it("drawer shows email", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("drawer-email").textContent).toBe("info@acme.com");
  });

  it("drawer shows notes", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("drawer-notes").textContent).toBe("VIP customer");
  });

  it("close button hides drawer", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    fireEvent.click(screen.getByTestId("drawer-close"));
    expect(screen.queryByTestId("detail-drawer")).toBeNull();
  });

  it("drawer has health change buttons", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("health-btn-healthy")).toBeTruthy();
    expect(screen.getByTestId("health-btn-at_risk")).toBeTruthy();
    expect(screen.getByTestId("health-btn-attention")).toBeTruthy();
    expect(screen.getByTestId("health-btn-inactive")).toBeTruthy();
  });

  it("clicking health button calls mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    fireEvent.click(screen.getByTestId("health-btn-at_risk"));
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });

  it("archive button visible in drawer", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("archive-btn")).toBeTruthy();
  });

  it("clicking archive calls archive mutate", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    fireEvent.click(screen.getByTestId("archive-btn"));
    expect(NOOP_MUTATE).toHaveBeenCalled();
  });

  it("drawer has website when present", () => {
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-1"));
    expect(screen.getByTestId("drawer-website").textContent).toBe("https://acme.com");
  });

  it("drawer shows null-optional fields conditionally", () => {
    mockAll({ listOut: { ...LIST_OUT, items: [C2] } });
    renderCenter();
    fireEvent.click(screen.getByTestId("customer-row-cid-2"));
    expect(screen.queryByTestId("drawer-notes")).toBeNull();
  });
});

describe("CustomerCenter — KPI section", () => {
  beforeEach(() => mockAll());

  it("renders KPI section", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-section")).toBeTruthy();
  });

  it("KPI active card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-active")).toBeTruthy();
  });

  it("KPI prospects card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-prospects")).toBeTruthy();
  });

  it("KPI at-risk card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-at-risk")).toBeTruthy();
  });

  it("KPI healthy card present", () => {
    renderCenter();
    expect(screen.getByTestId("kpi-healthy")).toBeTruthy();
  });
});
