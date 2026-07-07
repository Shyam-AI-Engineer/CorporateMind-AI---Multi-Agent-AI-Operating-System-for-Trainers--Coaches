import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  CustomerInvoice,
  CustomerInvoiceListOut,
  InvoiceKPIsOut,
} from "@/features/billing/types-billing";
import { INVOICE_STATUSES } from "@/features/billing/types-billing";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/billing/api/use-billing", () => ({
  useInvoiceKPIs: vi.fn(),
  useInvoiceList: vi.fn(),
  useInvoiceDetail: vi.fn(),
  useInvoicesByCustomer: vi.fn(),
  useCreateInvoice: vi.fn(),
  useUpdateInvoice: vi.fn(),
  useIssueInvoice: vi.fn(),
  useMarkInvoicePaid: vi.fn(),
  useCancelInvoice: vi.fn(),
}));

import {
  useInvoiceKPIs,
  useInvoiceList,
  useInvoiceDetail,
  useInvoicesByCustomer,
  useCreateInvoice,
  useIssueInvoice,
  useMarkInvoicePaid,
  useCancelInvoice,
} from "@/features/billing/api/use-billing";

const mockKPIs = vi.mocked(useInvoiceKPIs);
const mockList = vi.mocked(useInvoiceList);
const mockDetail = vi.mocked(useInvoiceDetail);
const mockByCustomer = vi.mocked(useInvoicesByCustomer);
const mockCreate = vi.mocked(useCreateInvoice);
const mockIssue = vi.mocked(useIssueInvoice);
const mockMarkPaid = vi.mocked(useMarkInvoicePaid);
const mockCancel = vi.mocked(useCancelInvoice);

const {
  StatusBadge,
  InvoiceKPISection,
  InvoiceTable,
  InvoiceDialog,
  PaymentDialog,
  InvoiceDrawer,
  InvoiceCenter,
  CustomerInvoicesTab,
  LinkedInvoiceBadge,
} = await import("./invoice-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS = "ws-51";
const CUST = "cust-51";

function makeInvoice(overrides: Partial<CustomerInvoice> = {}): CustomerInvoice {
  return {
    id: "inv-1",
    workspace_id: WS,
    customer_id: CUST,
    invoice_number: "INV-001",
    invoice_date: "2026-07-01",
    due_date: "2026-07-31",
    amount: "10000.00",
    tax_amount: "1800.00",
    total_amount: "11800.00",
    currency: "INR",
    status: "draft",
    payment_date: null,
    renewal_id: null,
    notes: null,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

function makeListOut(
  items: CustomerInvoice[] = [],
  overrides: Partial<CustomerInvoiceListOut> = {}
): CustomerInvoiceListOut {
  return { items, next_cursor: null, has_more: false, total: items.length, ...overrides };
}

function makeKPIs(overrides: Partial<InvoiceKPIsOut> = {}): InvoiceKPIsOut {
  return {
    total_outstanding: "11800.00",
    total_paid: "5000.00",
    total_overdue: "0.00",
    count_draft: 1,
    count_issued: 1,
    count_paid: 2,
    count_overdue: 0,
    count_cancelled: 0,
    ...overrides,
  };
}

function idleMutation() {
  return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
}

function setupMutations() {
  mockCreate.mockReturnValue(idleMutation() as ReturnType<typeof useCreateInvoice>);
  mockIssue.mockReturnValue(idleMutation() as ReturnType<typeof useIssueInvoice>);
  mockMarkPaid.mockReturnValue(idleMutation() as ReturnType<typeof useMarkInvoicePaid>);
  mockCancel.mockReturnValue(idleMutation() as ReturnType<typeof useCancelInvoice>);
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

describe("StatusBadge", () => {
  it("renders draft badge", () => {
    render(<StatusBadge status="draft" />);
    expect(screen.getByTestId("invoice-status-badge-draft")).not.toBeNull();
  });

  it("renders issued badge", () => {
    render(<StatusBadge status="issued" />);
    expect(screen.getByTestId("invoice-status-badge-issued")).not.toBeNull();
  });

  it("renders paid badge", () => {
    render(<StatusBadge status="paid" />);
    expect(screen.getByTestId("invoice-status-badge-paid")).not.toBeNull();
  });

  it("renders cancelled badge", () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByTestId("invoice-status-badge-cancelled")).not.toBeNull();
  });

  it("renders overdue badge", () => {
    render(<StatusBadge status="overdue" />);
    expect(screen.getByTestId("invoice-status-badge-overdue")).not.toBeNull();
  });

  it("badge text matches status", () => {
    render(<StatusBadge status="paid" />);
    expect(screen.getByTestId("invoice-status-badge-paid").textContent).toContain("paid");
  });

  it("issued badge shows blue class", () => {
    render(<StatusBadge status="issued" />);
    const el = screen.getByTestId("invoice-status-badge-issued");
    expect(el.className).toContain("blue");
  });

  it("paid badge shows green class", () => {
    render(<StatusBadge status="paid" />);
    const el = screen.getByTestId("invoice-status-badge-paid");
    expect(el.className).toContain("green");
  });

  it("cancelled badge shows red class", () => {
    render(<StatusBadge status="cancelled" />);
    const el = screen.getByTestId("invoice-status-badge-cancelled");
    expect(el.className).toContain("red");
  });

  it("overdue badge shows orange class", () => {
    render(<StatusBadge status="overdue" />);
    const el = screen.getByTestId("invoice-status-badge-overdue");
    expect(el.className).toContain("orange");
  });
});

// ── InvoiceKPISection ─────────────────────────────────────────────────────────

describe("InvoiceKPISection", () => {
  it("renders kpi section", () => {
    render(<InvoiceKPISection kpis={makeKPIs()} />);
    expect(screen.getByTestId("invoice-kpi-section")).not.toBeNull();
  });

  it("shows outstanding amount", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ total_outstanding: "11800.00" })} />);
    const el = screen.getByTestId("kpi-outstanding");
    expect(el.textContent).toContain("11");
  });

  it("shows paid amount", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ total_paid: "5000.00" })} />);
    const el = screen.getByTestId("kpi-paid");
    expect(el.textContent).toContain("5");
  });

  it("shows overdue amount", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ total_overdue: "0.00" })} />);
    expect(screen.getByTestId("kpi-overdue")).not.toBeNull();
  });

  it("shows draft/issued counts", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ count_draft: 3, count_issued: 2 })} />);
    const el = screen.getByTestId("kpi-counts");
    expect(el.textContent).toContain("3");
    expect(el.textContent).toContain("2");
  });

  it("renders 4 kpi cards", () => {
    const { container } = render(<InvoiceKPISection kpis={makeKPIs()} />);
    const cards = container.querySelectorAll("[data-testid^='kpi-']");
    expect(cards.length).toBe(4);
  });

  it("zero values show dash for invalid amount", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ total_outstanding: "NaN" })} />);
    expect(screen.getByTestId("kpi-outstanding").textContent).toContain("—");
  });

  it("formats INR currency symbol", () => {
    render(<InvoiceKPISection kpis={makeKPIs({ total_paid: "50000.00" })} />);
    expect(screen.getByTestId("kpi-paid").textContent).toContain("₹");
  });
});

// ── InvoiceTable ──────────────────────────────────────────────────────────────

describe("InvoiceTable", () => {
  it("shows empty state", () => {
    render(<InvoiceTable items={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("invoice-table-empty")).not.toBeNull();
  });

  it("renders table when items exist", () => {
    render(<InvoiceTable items={[makeInvoice()]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("invoice-table")).not.toBeNull();
  });

  it("renders a row per invoice", () => {
    const items = [makeInvoice({ id: "i1" }), makeInvoice({ id: "i2" })];
    render(<InvoiceTable items={items} onSelect={vi.fn()} />);
    expect(screen.getByTestId("invoice-row-i1")).not.toBeNull();
    expect(screen.getByTestId("invoice-row-i2")).not.toBeNull();
  });

  it("shows invoice number", () => {
    render(<InvoiceTable items={[makeInvoice({ invoice_number: "INV-999" })]} onSelect={vi.fn()} />);
    expect(screen.getByText("INV-999")).not.toBeNull();
  });

  it("shows em-dash for null invoice number", () => {
    render(<InvoiceTable items={[makeInvoice({ invoice_number: null })]} onSelect={vi.fn()} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows status badge in row", () => {
    render(<InvoiceTable items={[makeInvoice({ status: "issued" })]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("invoice-status-badge-issued")).not.toBeNull();
  });

  it("view button calls onSelect with invoice", async () => {
    const inv = makeInvoice();
    const onSelect = vi.fn();
    render(<InvoiceTable items={[inv]} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId(`invoice-view-${inv.id}`));
    expect(onSelect).toHaveBeenCalledWith(inv);
  });

  it("total amount formatted with rupee symbol", () => {
    render(<InvoiceTable items={[makeInvoice({ total_amount: "11800.00" })]} onSelect={vi.fn()} />);
    const row = screen.getByTestId("invoice-row-inv-1");
    expect(row.textContent).toContain("₹");
  });

  it("null total_amount shows dash", () => {
    render(<InvoiceTable items={[makeInvoice({ total_amount: null })]} onSelect={vi.fn()} />);
    const row = screen.getByTestId("invoice-row-inv-1");
    expect(row.textContent).toContain("—");
  });

  it("invoice date shown in row", () => {
    render(<InvoiceTable items={[makeInvoice({ invoice_date: "2026-07-01" })]} onSelect={vi.fn()} />);
    expect(screen.getByText("2026-07-01")).not.toBeNull();
  });
});

// ── InvoiceDialog ─────────────────────────────────────────────────────────────

describe("InvoiceDialog", () => {
  beforeEach(() => {
    setupMutations();
  });

  it("renders nothing when closed", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={false} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("invoice-dialog")).toBeNull();
  });

  it("renders dialog when open", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("invoice-dialog")).not.toBeNull();
  });

  it("shows invoice number field", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-invoice-number")).not.toBeNull();
  });

  it("shows invoice date field", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-invoice-date")).not.toBeNull();
  });

  it("shows due date field", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-due-date")).not.toBeNull();
  });

  it("shows total amount field", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-total-amount")).not.toBeNull();
  });

  it("shows notes field", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-notes")).not.toBeNull();
  });

  it("cancel button calls onClose", async () => {
    const onClose = vi.fn();
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={onClose} />
    );
    await userEvent.click(screen.getByTestId("invoice-dialog-cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("submit button is enabled by default", () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    const btn = screen.getByTestId("invoice-dialog-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("submit button disabled when pending", () => {
    const pendingMut = { ...idleMutation(), isPending: true };
    mockCreate.mockReturnValue(pendingMut as ReturnType<typeof useCreateInvoice>);
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    const btn = screen.getByTestId("invoice-dialog-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("pending button shows loading text", () => {
    const pendingMut = { ...idleMutation(), isPending: true };
    mockCreate.mockReturnValue(pendingMut as ReturnType<typeof useCreateInvoice>);
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("invoice-dialog-submit").textContent).toContain("Creating");
  });

  it("invoice number field is editable", async () => {
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    const input = screen.getByTestId("field-invoice-number") as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "INV-123");
    expect(input.value).toBe("INV-123");
  });

  it("successful submit calls mutateAsync", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ data: makeInvoice() });
    mockCreate.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useCreateInvoice>);
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("invoice-dialog-submit"));
    expect(mutateAsync).toHaveBeenCalled();
  });

  it("error from mutateAsync shows error message", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("Already exists"));
    mockCreate.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useCreateInvoice>);
    render(
      <InvoiceDialog workspaceId={WS} customerId={CUST} open={true} onClose={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("invoice-dialog-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("invoice-dialog-error")).not.toBeNull();
    });
  });
});

// ── PaymentDialog ─────────────────────────────────────────────────────────────

describe("PaymentDialog", () => {
  beforeEach(() => setupMutations());

  it("renders nothing when closed", () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={false} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("payment-dialog")).toBeNull();
  });

  it("renders when open", () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("payment-dialog")).not.toBeNull();
  });

  it("shows payment date field", () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("field-payment-date")).not.toBeNull();
  });

  it("cancel button calls onClose", async () => {
    const onClose = vi.fn();
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={onClose} />
    );
    await userEvent.click(screen.getByTestId("payment-dialog-cancel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("submit without date shows error", async () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    fireEvent.submit(screen.getByTestId("payment-form"));
    await waitFor(() => {
      expect(screen.getByTestId("payment-dialog-error")).not.toBeNull();
    });
  });

  it("submit with date calls mutateAsync", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ data: makeInvoice({ status: "paid" }) });
    mockMarkPaid.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    const input = screen.getByTestId("field-payment-date") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2026-07-15" } });
    fireEvent.submit(screen.getByTestId("payment-form"));
    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({ id: "inv-1", body: { payment_date: "2026-07-15" } });
    });
  });

  it("submit disabled when pending", () => {
    const pendingMut = { ...idleMutation(), isPending: true };
    mockMarkPaid.mockReturnValue(pendingMut as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    const btn = screen.getByTestId("payment-dialog-submit") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("pending shows saving text", () => {
    const pendingMut = { ...idleMutation(), isPending: true };
    mockMarkPaid.mockReturnValue(pendingMut as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("payment-dialog-submit").textContent).toContain("Saving");
  });

  it("error from mutateAsync shows error message", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("Server error"));
    mockMarkPaid.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    const input = screen.getByTestId("field-payment-date") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2026-07-15" } });
    fireEvent.submit(screen.getByTestId("payment-form"));
    await waitFor(() => {
      expect(screen.getByTestId("payment-dialog-error")).not.toBeNull();
    });
  });

  it("successful submit calls onClose", async () => {
    const onClose = vi.fn();
    const mutateAsync = vi.fn().mockResolvedValue({ data: makeInvoice({ status: "paid" }) });
    mockMarkPaid.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={onClose} />
    );
    const input = screen.getByTestId("field-payment-date") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2026-07-15" } });
    fireEvent.submit(screen.getByTestId("payment-form"));
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("title says Mark as Paid", () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByText("Mark as Paid")).not.toBeNull();
  });

  it("payment date field is type date", () => {
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    const input = screen.getByTestId("field-payment-date") as HTMLInputElement;
    expect(input.type).toBe("date");
  });

  it("non-Error rejection shows generic message", async () => {
    const mutateAsync = vi.fn().mockRejectedValue("unknown");
    mockMarkPaid.mockReturnValue({ ...idleMutation(), mutateAsync } as ReturnType<typeof useMarkInvoicePaid>);
    render(
      <PaymentDialog invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    const input = screen.getByTestId("field-payment-date") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2026-07-15" } });
    fireEvent.submit(screen.getByTestId("payment-form"));
    await waitFor(() => {
      const err = screen.getByTestId("payment-dialog-error");
      expect(err.textContent).toContain("Failed to mark paid");
    });
  });
});

// ── InvoiceDrawer ─────────────────────────────────────────────────────────────

describe("InvoiceDrawer", () => {
  beforeEach(() => {
    setupMutations();
    // React hooks run before the early-return guard, so always provide a valid query result
    mockDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
  });

  it("renders nothing when closed", () => {
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={false} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("renders nothing when invoiceId is null", () => {
    mockDetail.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId={null} workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("shows loading state", () => {
    mockDetail.mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-loading")).not.toBeNull();
  });

  it("shows not found when no data", () => {
    mockDetail.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-not-found")).not.toBeNull();
  });

  it("shows drawer content when loaded", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-content")).not.toBeNull();
  });

  it("shows invoice number", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ invoice_number: "INV-999" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-invoice-number").textContent).toBe("INV-999");
  });

  it("shows status badge in drawer", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "issued" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("invoice-status-badge-issued")).not.toBeNull();
  });

  it("shows Issue button for draft invoice", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "draft" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-action-issue")).not.toBeNull();
  });

  it("shows Mark Paid button for issued invoice", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "issued" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-action-mark-paid")).not.toBeNull();
  });

  it("shows Cancel button for draft invoice", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "draft" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-action-cancel")).not.toBeNull();
  });

  it("no Issue button for paid invoice", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "paid" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("drawer-action-issue")).toBeNull();
  });

  it("no Cancel button for paid invoice", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "paid" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.queryByTestId("drawer-action-cancel")).toBeNull();
  });

  it("close button calls onClose", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    const onClose = vi.fn();
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={onClose} />
    );
    await userEvent.click(screen.getByTestId("invoice-drawer-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("Issue button calls issueMut.mutate", async () => {
    const mutate = vi.fn();
    mockIssue.mockReturnValue({ ...idleMutation(), mutate } as ReturnType<typeof useIssueInvoice>);
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "draft" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("drawer-action-issue"));
    expect(mutate).toHaveBeenCalledWith("inv-1");
  });

  it("Cancel button calls cancelMut.mutate", async () => {
    const mutate = vi.fn();
    mockCancel.mockReturnValue({ ...idleMutation(), mutate } as ReturnType<typeof useCancelInvoice>);
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "issued" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("drawer-action-cancel"));
    expect(mutate).toHaveBeenCalledWith("inv-1");
  });

  it("shows due date", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ due_date: "2026-07-31" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-due-date").textContent).toBe("2026-07-31");
  });

  it("shows payment date when paid", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "paid", payment_date: "2026-07-15" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-payment-date").textContent).toBe("2026-07-15");
  });

  it("shows notes when present", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ notes: "Please pay by month end" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("drawer-notes").textContent).toContain("Please pay");
  });

  it("mark paid button opens payment dialog", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "issued" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(
      <InvoiceDrawer invoiceId="inv-1" workspaceId={WS} open={true} onClose={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("drawer-action-mark-paid"));
    expect(screen.getByTestId("payment-dialog")).not.toBeNull();
  });
});

// ── InvoiceCenter ─────────────────────────────────────────────────────────────

describe("InvoiceCenter", () => {
  beforeEach(() => {
    setupMutations();
    mockKPIs.mockReturnValue({ data: { data: makeKPIs() }, isLoading: false } as ReturnType<typeof useInvoiceKPIs>);
    mockList.mockReturnValue({
      data: { data: makeListOut([makeInvoice()]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useInvoiceList>);
  });

  it("renders invoice center", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-center")).not.toBeNull();
  });

  it("shows page heading", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByText("Invoices")).not.toBeNull();
  });

  it("shows New Invoice button", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-create-btn")).not.toBeNull();
  });

  it("shows kpi section", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-kpi-section")).not.toBeNull();
  });

  it("shows kpis loading state", () => {
    mockKPIs.mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useInvoiceKPIs>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("kpis-loading")).not.toBeNull();
  });

  it("shows search input", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-search")).not.toBeNull();
  });

  it("shows status filter select", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-status-filter")).not.toBeNull();
  });

  it("status filter has all-statuses option", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    const select = screen.getByTestId("invoice-status-filter") as HTMLSelectElement;
    expect(select.options[0].value).toBe("");
  });

  it("status filter has all 5 status options", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    const select = screen.getByTestId("invoice-status-filter") as HTMLSelectElement;
    expect(select.options.length).toBe(INVOICE_STATUSES.length + 1);
  });

  it("shows invoice table", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-table")).not.toBeNull();
  });

  it("shows loading state", () => {
    mockList.mockReturnValue({ data: undefined, isLoading: true, isError: false } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-list-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockList.mockReturnValue({ data: undefined, isLoading: false, isError: true } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-list-error")).not.toBeNull();
  });

  it("empty list shows empty message", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-table-empty")).not.toBeNull();
  });

  it("clicking New Invoice opens dialog", async () => {
    render(<InvoiceCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-create-btn"));
    expect(screen.getByTestId("invoice-dialog")).not.toBeNull();
  });

  it("dialog cancel closes dialog", async () => {
    render(<InvoiceCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-create-btn"));
    await userEvent.click(screen.getByTestId("invoice-dialog-cancel"));
    expect(screen.queryByTestId("invoice-dialog")).toBeNull();
  });

  it("invoice dialog not shown by default", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-dialog")).toBeNull();
  });

  it("clicking view row opens drawer", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<InvoiceCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-view-inv-1"));
    expect(screen.getByTestId("invoice-drawer")).not.toBeNull();
  });

  it("drawer close button hides drawer", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<InvoiceCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-view-inv-1"));
    await userEvent.click(screen.getByTestId("invoice-drawer-close"));
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("search input updates value", async () => {
    render(<InvoiceCenter workspaceId={WS} />);
    const input = screen.getByTestId("invoice-search") as HTMLInputElement;
    await userEvent.type(input, "INV-");
    expect(input.value).toContain("INV-");
  });

  it("status filter change updates value", async () => {
    render(<InvoiceCenter workspaceId={WS} />);
    const select = screen.getByTestId("invoice-status-filter") as HTMLSelectElement;
    await userEvent.selectOptions(select, "draft");
    expect(select.value).toBe("draft");
  });

  it("status filter can be reset to all", async () => {
    render(<InvoiceCenter workspaceId={WS} />);
    const select = screen.getByTestId("invoice-status-filter") as HTMLSelectElement;
    await userEvent.selectOptions(select, "paid");
    await userEvent.selectOptions(select, "");
    expect(select.value).toBe("");
  });

  it("multiple invoices shown in table", () => {
    mockList.mockReturnValue({
      data: {
        data: makeListOut([
          makeInvoice({ id: "i1" }),
          makeInvoice({ id: "i2" }),
          makeInvoice({ id: "i3" }),
        ]),
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-row-i1")).not.toBeNull();
    expect(screen.getByTestId("invoice-row-i2")).not.toBeNull();
    expect(screen.getByTestId("invoice-row-i3")).not.toBeNull();
  });

  it("drawer is not shown initially", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("kpi shows outstanding formatted", () => {
    mockKPIs.mockReturnValue({
      data: { data: makeKPIs({ total_outstanding: "25000.00" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceKPIs>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("kpi-outstanding").textContent).toContain("25");
  });

  it("invoice number shown in table row", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeInvoice({ invoice_number: "INV-TEST" })]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByText("INV-TEST")).not.toBeNull();
  });

  it("status badge shown in table row", () => {
    mockList.mockReturnValue({
      data: { data: makeListOut([makeInvoice({ status: "paid" })]) },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useInvoiceList>);
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.getByTestId("invoice-status-badge-paid")).not.toBeNull();
  });

  it("no error state when data loads", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-list-error")).toBeNull();
  });

  it("does not show list-loading when data available", () => {
    render(<InvoiceCenter workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-list-loading")).toBeNull();
  });
});

// ── CustomerInvoicesTab ───────────────────────────────────────────────────────

describe("CustomerInvoicesTab", () => {
  beforeEach(() => {
    setupMutations();
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeInvoice()]) },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
  });

  it("renders the tab", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("customer-invoices-tab")).not.toBeNull();
  });

  it("shows Add Invoice button", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("customer-invoices-add-btn")).not.toBeNull();
  });

  it("shows invoice count in heading", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByText(/Invoices \(1\)/)).not.toBeNull();
  });

  it("shows loading state", () => {
    mockByCustomer.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("customer-invoices-loading")).not.toBeNull();
  });

  it("shows invoice table", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("invoice-table")).not.toBeNull();
  });

  it("empty invoices shows empty state", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([]) },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("invoice-table-empty")).not.toBeNull();
  });

  it("clicking Add Invoice opens dialog", async () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("customer-invoices-add-btn"));
    expect(screen.getByTestId("invoice-dialog")).not.toBeNull();
  });

  it("dialog cancel closes it", async () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("customer-invoices-add-btn"));
    await userEvent.click(screen.getByTestId("invoice-dialog-cancel"));
    expect(screen.queryByTestId("invoice-dialog")).toBeNull();
  });

  it("clicking view opens drawer", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-view-inv-1"));
    expect(screen.getByTestId("invoice-drawer")).not.toBeNull();
  });

  it("drawer close hides it", async () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("invoice-view-inv-1"));
    await userEvent.click(screen.getByTestId("invoice-drawer-close"));
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("count shows 0 when no invoices", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([]) },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByText(/Invoices \(0\)/)).not.toBeNull();
  });

  it("multiple invoices all shown", () => {
    mockByCustomer.mockReturnValue({
      data: {
        data: makeListOut([
          makeInvoice({ id: "a1" }),
          makeInvoice({ id: "a2" }),
        ]),
      },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("invoice-row-a1")).not.toBeNull();
    expect(screen.getByTestId("invoice-row-a2")).not.toBeNull();
  });

  it("no drawer shown by default", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-drawer")).toBeNull();
  });

  it("invoice status badge shown for each row", () => {
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut([makeInvoice({ status: "issued" })]) },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByTestId("invoice-status-badge-issued")).not.toBeNull();
  });

  it("dialog is not open by default", () => {
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.queryByTestId("invoice-dialog")).toBeNull();
  });

  it("passes correct customerId to dialog", async () => {
    render(<CustomerInvoicesTab customerId="cust-xyz" workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("customer-invoices-add-btn"));
    expect(screen.getByTestId("invoice-dialog")).not.toBeNull();
  });

  it("count matches items length", () => {
    const items = [
      makeInvoice({ id: "b1" }),
      makeInvoice({ id: "b2" }),
      makeInvoice({ id: "b3" }),
    ];
    mockByCustomer.mockReturnValue({
      data: { data: makeListOut(items) },
      isLoading: false,
    } as ReturnType<typeof useInvoicesByCustomer>);
    render(<CustomerInvoicesTab customerId={CUST} workspaceId={WS} />);
    expect(screen.getByText(/Invoices \(3\)/)).not.toBeNull();
  });
});

// ── LinkedInvoiceBadge ────────────────────────────────────────────────────────

describe("LinkedInvoiceBadge", () => {
  it("renders nothing when invoiceId is null", () => {
    const { container } = render(
      <LinkedInvoiceBadge invoiceId={null} workspaceId={WS} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when invoiceId is undefined", () => {
    const { container } = render(
      <LinkedInvoiceBadge invoiceId={undefined} workspaceId={WS} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows loading when fetching", () => {
    mockDetail.mockReturnValue({ data: undefined, isLoading: true } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("linked-invoice-loading")).not.toBeNull();
  });

  it("renders nothing when data not found", () => {
    mockDetail.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<typeof useInvoiceDetail>);
    const { container } = render(
      <LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows badge when loaded", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice() },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("linked-invoice-badge")).not.toBeNull();
  });

  it("shows invoice number", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ invoice_number: "INV-42" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("linked-invoice-number").textContent).toBe("INV-42");
  });

  it("shows truncated id when no invoice number", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ invoice_number: null, id: "12345678-aaaa-bbbb-cccc-ddddeeeefffff" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("linked-invoice-number").textContent).toBe("12345678");
  });

  it("shows amount when present", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ total_amount: "11800.00" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("linked-invoice-amount")).not.toBeNull();
    expect(screen.getByTestId("linked-invoice-amount").textContent).toContain("₹");
  });

  it("no amount shown when total_amount is null", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ total_amount: null }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.queryByTestId("linked-invoice-amount")).toBeNull();
  });

  it("shows status badge in linked badge", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ status: "paid" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    expect(screen.getByTestId("invoice-status-badge-paid")).not.toBeNull();
  });

  it("amount formatted with rupee symbol", () => {
    mockDetail.mockReturnValue({
      data: { data: makeInvoice({ total_amount: "50000.00" }) },
      isLoading: false,
    } as ReturnType<typeof useInvoiceDetail>);
    render(<LinkedInvoiceBadge invoiceId="inv-1" workspaceId={WS} />);
    const amountEl = screen.getByTestId("linked-invoice-amount");
    expect(amountEl.textContent).toContain("₹");
  });
});
