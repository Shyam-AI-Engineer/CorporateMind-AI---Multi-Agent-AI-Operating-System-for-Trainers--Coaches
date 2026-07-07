import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  InvoicePayment,
  InvoicePaymentListOut,
  RevenueSummaryOut,
} from "@/features/billing/types-billing";
import { PAYMENT_METHODS, PAYMENT_STATUSES } from "@/features/billing/types-billing";

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/features/billing/api/use-billing", () => ({
  useRevenueSummary: vi.fn(),
  usePaymentList: vi.fn(),
  usePaymentDetail: vi.fn(),
  usePaymentsByInvoice: vi.fn(),
  useRecordPayment: vi.fn(),
  useUpdatePayment: vi.fn(),
  useConfirmPayment: vi.fn(),
  useCancelPayment: vi.fn(),
}));

import {
  useRevenueSummary,
  usePaymentList,
  usePaymentDetail,
  usePaymentsByInvoice,
  useRecordPayment,
  useUpdatePayment,
  useConfirmPayment,
  useCancelPayment,
} from "@/features/billing/api/use-billing";

const mockRevenueSummary = vi.mocked(useRevenueSummary);
const mockPaymentList = vi.mocked(usePaymentList);
const mockPaymentDetail = vi.mocked(usePaymentDetail);
const mockPaymentsByInvoice = vi.mocked(usePaymentsByInvoice);
const mockRecordPayment = vi.mocked(useRecordPayment);
const mockUpdatePayment = vi.mocked(useUpdatePayment);
const mockConfirmPayment = vi.mocked(useConfirmPayment);
const mockCancelPayment = vi.mocked(useCancelPayment);

const {
  PaymentStatusBadge,
  RevenueSummaryCards,
  PaymentDialog,
  PaymentHistory,
  PaymentFilters,
  PaymentCenter,
  InvoicePaymentSection,
  PaymentDetailPanel,
} = await import("./payment-center");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const WS = "ws-52";
const INV = "inv-52";
const CUST = "cust-52";
const PAY_ID = "pay-52";

function makePayment(overrides: Partial<InvoicePayment> = {}): InvoicePayment {
  return {
    id: PAY_ID,
    workspace_id: WS,
    invoice_id: INV,
    customer_id: CUST,
    payment_date: "2026-07-07",
    amount: "5000.00",
    payment_method: "upi",
    reference_number: "REF-001",
    status: "pending",
    notes: null,
    created_by: null,
    created_at: "2026-07-07T10:00:00Z",
    updated_at: "2026-07-07T10:00:00Z",
    ...overrides,
  };
}

function makePaymentListOut(
  items: InvoicePayment[] = [],
  overrides: Partial<InvoicePaymentListOut> = {}
): InvoicePaymentListOut {
  return {
    items,
    next_cursor: null,
    has_more: false,
    total: items.length,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<RevenueSummaryOut> = {}): RevenueSummaryOut {
  return {
    total_collected: "50000.00",
    total_outstanding: "20000.00",
    total_overdue: "5000.00",
    count_pending_payments: 3,
    count_confirmed_payments: 10,
    count_cancelled_payments: 1,
    partial_payment_invoices: 2,
    ...overrides,
  };
}

function idleMutation() {
  return { mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue({ data: makePayment() }), isPending: false };
}

function setupMutations() {
  mockRecordPayment.mockReturnValue(idleMutation() as ReturnType<typeof useRecordPayment>);
  mockUpdatePayment.mockReturnValue(idleMutation() as ReturnType<typeof useUpdatePayment>);
  mockConfirmPayment.mockReturnValue(idleMutation() as ReturnType<typeof useConfirmPayment>);
  mockCancelPayment.mockReturnValue(idleMutation() as ReturnType<typeof useCancelPayment>);
}

function setupIdleQueries() {
  mockRevenueSummary.mockReturnValue({
    data: { data: makeSummary() },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useRevenueSummary>);
  mockPaymentList.mockReturnValue({
    data: { data: makePaymentListOut([]) },
    isLoading: false,
    error: null,
  } as ReturnType<typeof usePaymentList>);
  mockPaymentsByInvoice.mockReturnValue({
    data: { data: [] },
    isLoading: false,
    error: null,
  } as ReturnType<typeof usePaymentsByInvoice>);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMutations();
  setupIdleQueries();
});

// ── PaymentStatusBadge ────────────────────────────────────────────────────────

describe("PaymentStatusBadge", () => {
  it("renders pending badge", () => {
    render(<PaymentStatusBadge status="pending" />);
    expect(screen.getByTestId("payment-status-badge-pending")).not.toBeNull();
  });

  it("renders confirmed badge", () => {
    render(<PaymentStatusBadge status="confirmed" />);
    expect(screen.getByTestId("payment-status-badge-confirmed")).not.toBeNull();
  });

  it("renders cancelled badge", () => {
    render(<PaymentStatusBadge status="cancelled" />);
    expect(screen.getByTestId("payment-status-badge-cancelled")).not.toBeNull();
  });

  it("shows status text inside badge", () => {
    render(<PaymentStatusBadge status="pending" />);
    expect(screen.getByText("pending")).not.toBeNull();
  });

  it("pending badge has yellow styling", () => {
    render(<PaymentStatusBadge status="pending" />);
    const el = screen.getByTestId("payment-status-badge-pending");
    expect(el.className).toContain("yellow");
  });

  it("confirmed badge has green styling", () => {
    render(<PaymentStatusBadge status="confirmed" />);
    const el = screen.getByTestId("payment-status-badge-confirmed");
    expect(el.className).toContain("green");
  });

  it("cancelled badge has red styling", () => {
    render(<PaymentStatusBadge status="cancelled" />);
    const el = screen.getByTestId("payment-status-badge-cancelled");
    expect(el.className).toContain("red");
  });

  it("renders all three statuses without error", () => {
    for (const s of PAYMENT_STATUSES) {
      const { unmount } = render(<PaymentStatusBadge status={s} />);
      expect(screen.getByTestId(`payment-status-badge-${s}`)).not.toBeNull();
      unmount();
    }
  });
});

// ── RevenueSummaryCards ───────────────────────────────────────────────────────

describe("RevenueSummaryCards", () => {
  const summary = makeSummary();

  it("renders the cards container", () => {
    render(<RevenueSummaryCards summary={summary} />);
    expect(screen.getByTestId("revenue-summary-cards")).not.toBeNull();
  });

  it("shows total collected", () => {
    render(<RevenueSummaryCards summary={summary} />);
    expect(screen.getByTestId("summary-collected")).not.toBeNull();
  });

  it("shows total outstanding", () => {
    render(<RevenueSummaryCards summary={summary} />);
    expect(screen.getByTestId("summary-outstanding")).not.toBeNull();
  });

  it("shows total overdue", () => {
    render(<RevenueSummaryCards summary={summary} />);
    expect(screen.getByTestId("summary-overdue")).not.toBeNull();
  });

  it("shows partial invoice count", () => {
    render(<RevenueSummaryCards summary={summary} />);
    expect(screen.getByTestId("summary-partial")).not.toBeNull();
  });

  it("formats collected with rupee symbol", () => {
    render(<RevenueSummaryCards summary={summary} />);
    const el = screen.getByTestId("summary-collected");
    expect(el.textContent).toContain("₹");
  });

  it("formats outstanding with rupee symbol", () => {
    render(<RevenueSummaryCards summary={summary} />);
    const el = screen.getByTestId("summary-outstanding");
    expect(el.textContent).toContain("₹");
  });

  it("formats overdue with rupee symbol", () => {
    render(<RevenueSummaryCards summary={summary} />);
    const el = screen.getByTestId("summary-overdue");
    expect(el.textContent).toContain("₹");
  });

  it("shows partial invoice count as number", () => {
    render(<RevenueSummaryCards summary={makeSummary({ partial_payment_invoices: 4 })} />);
    expect(screen.getByText("4")).not.toBeNull();
  });

  it("handles zero amounts gracefully", () => {
    render(<RevenueSummaryCards summary={makeSummary({ total_collected: "0.00" })} />);
    const el = screen.getByTestId("summary-collected");
    expect(el.textContent).toContain("₹");
  });
});

// ── PaymentDialog — create mode ───────────────────────────────────────────────

describe("PaymentDialog (create mode)", () => {
  const onClose = vi.fn();

  it("renders dialog with title", () => {
    render(
      <PaymentDialog
        mode="create"
        workspaceId={WS}
        invoiceId={INV}
        customerId={CUST}
        onClose={onClose}
      />
    );
    expect(screen.getByTestId("dialog-title")).not.toBeNull();
    expect(screen.getByText("Record Payment")).not.toBeNull();
  });

  it("renders amount input", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-amount-input")).not.toBeNull();
  });

  it("renders date input", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-date-input")).not.toBeNull();
  });

  it("renders method select with all options", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    const select = screen.getByTestId("payment-method-select");
    for (const m of PAYMENT_METHODS) {
      expect(select.innerHTML).toContain(m);
    }
  });

  it("renders reference number input", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("reference-number-input")).not.toBeNull();
  });

  it("renders notes input", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-notes-input")).not.toBeNull();
  });

  it("renders submit and cancel buttons", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-submit-btn")).not.toBeNull();
    expect(screen.getByTestId("payment-cancel-btn")).not.toBeNull();
  });

  it("calls onClose when cancel clicked", async () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    await userEvent.click(screen.getByTestId("payment-cancel-btn"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("submit button says Record in create mode", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-submit-btn").textContent).toBe("Record");
  });

  it("shows Saving while pending", () => {
    mockRecordPayment.mockReturnValue({
      ...idleMutation(),
      isPending: true,
    } as ReturnType<typeof useRecordPayment>);
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.getByTestId("payment-submit-btn").textContent).toContain("Saving");
  });

  it("disables submit while pending", () => {
    mockRecordPayment.mockReturnValue({
      ...idleMutation(),
      isPending: true,
    } as ReturnType<typeof useRecordPayment>);
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect((screen.getByTestId("payment-submit-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls mutateAsync on submit with amount typed", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ data: makePayment() });
    mockRecordPayment.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync,
      isPending: false,
    } as ReturnType<typeof useRecordPayment>);
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    await userEvent.type(screen.getByTestId("payment-amount-input"), "5000");
    await userEvent.click(screen.getByTestId("payment-submit-btn"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("shows error on submit failure", async () => {
    mockRecordPayment.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockRejectedValue(new Error("Network error")),
      isPending: false,
    } as ReturnType<typeof useRecordPayment>);
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    await userEvent.type(screen.getByTestId("payment-amount-input"), "500");
    await userEvent.click(screen.getByTestId("payment-submit-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("payment-dialog-error")).not.toBeNull()
    );
  });

  it("closes on successful submit", async () => {
    const onCloseMock = vi.fn();
    render(
      <PaymentDialog
        mode="create"
        workspaceId={WS}
        invoiceId={INV}
        customerId={CUST}
        onClose={onCloseMock}
      />
    );
    await userEvent.type(screen.getByTestId("payment-amount-input"), "1000");
    await userEvent.click(screen.getByTestId("payment-submit-btn"));
    await waitFor(() => expect(onCloseMock).toHaveBeenCalledTimes(1));
  });

  it("no error shown initially", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={onClose} />
    );
    expect(screen.queryByTestId("payment-dialog-error")).toBeNull();
  });
});

// ── PaymentDialog — edit mode ─────────────────────────────────────────────────

describe("PaymentDialog (edit mode)", () => {
  const onClose = vi.fn();
  const payment = makePayment({ amount: "2500.00", payment_method: "cash" });

  it("renders with Edit Payment title", () => {
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onClose} />);
    expect(screen.getByText("Edit Payment")).not.toBeNull();
  });

  it("pre-fills amount from payment", () => {
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onClose} />);
    const input = screen.getByTestId("payment-amount-input") as HTMLInputElement;
    expect(input.value).toBe("2500.00");
  });

  it("pre-fills payment method", () => {
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onClose} />);
    const select = screen.getByTestId("payment-method-select") as HTMLSelectElement;
    expect(select.value).toBe("cash");
  });

  it("submit button says Update in edit mode", () => {
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onClose} />);
    expect(screen.getByTestId("payment-submit-btn").textContent).toBe("Update");
  });

  it("calls updateMutation on submit", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ data: payment });
    mockUpdatePayment.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync,
      isPending: false,
    } as ReturnType<typeof useUpdatePayment>);
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onClose} />);
    await userEvent.click(screen.getByTestId("payment-submit-btn"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("calls onClose after successful edit", async () => {
    const onCloseMock = vi.fn();
    render(<PaymentDialog mode="edit" workspaceId={WS} payment={payment} onClose={onCloseMock} />);
    await userEvent.click(screen.getByTestId("payment-submit-btn"));
    await waitFor(() => expect(onCloseMock).toHaveBeenCalledTimes(1));
  });
});

// ── PaymentHistory ────────────────────────────────────────────────────────────

describe("PaymentHistory", () => {
  it("shows loading state", () => {
    mockPaymentsByInvoice.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-history-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockPaymentsByInvoice.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-history-error")).not.toBeNull();
  });

  it("shows empty state when no payments", () => {
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-history-empty")).not.toBeNull();
  });

  it("renders table when payments exist", () => {
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [makePayment()] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-history-table")).not.toBeNull();
  });

  it("renders payment row", () => {
    const p = makePayment();
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId(`payment-row-${p.id}`)).not.toBeNull();
  });

  it("shows amount in row", () => {
    const p = makePayment({ amount: "7500.00" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-amount-${p.id}`);
    expect(el.textContent).toContain("₹");
  });

  it("shows confirm button for pending payment", () => {
    const p = makePayment({ status: "pending" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId(`confirm-payment-${p.id}`)).not.toBeNull();
  });

  it("shows cancel button for pending payment", () => {
    const p = makePayment({ status: "pending" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId(`cancel-payment-${p.id}`)).not.toBeNull();
  });

  it("shows cancel button for confirmed payment", () => {
    const p = makePayment({ id: "confirmed-pay", status: "confirmed" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId(`cancel-payment-${p.id}`)).not.toBeNull();
  });

  it("no confirm button for confirmed payment", () => {
    const p = makePayment({ id: "c-pay", status: "confirmed" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.queryByTestId(`confirm-payment-${p.id}`)).toBeNull();
  });

  it("no action buttons for cancelled payment", () => {
    const p = makePayment({ id: "can-pay", status: "cancelled" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.queryByTestId(`confirm-payment-${p.id}`)).toBeNull();
    expect(screen.queryByTestId(`cancel-payment-${p.id}`)).toBeNull();
  });

  it("calls confirmMutation.mutate on confirm click", async () => {
    const mutate = vi.fn();
    mockConfirmPayment.mockReturnValue({
      mutate,
      mutateAsync: vi.fn(),
      isPending: false,
    } as ReturnType<typeof useConfirmPayment>);
    const p = makePayment({ status: "pending" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId(`confirm-payment-${p.id}`));
    expect(mutate).toHaveBeenCalledWith({ id: p.id, invoiceId: p.invoice_id });
  });

  it("calls cancelMutation.mutate on cancel click", async () => {
    const mutate = vi.fn();
    mockCancelPayment.mockReturnValue({
      mutate,
      mutateAsync: vi.fn(),
      isPending: false,
    } as ReturnType<typeof useCancelPayment>);
    const p = makePayment({ status: "pending" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId(`cancel-payment-${p.id}`));
    expect(mutate).toHaveBeenCalledWith({ id: p.id, invoiceId: p.invoice_id });
  });

  it("shows payment method in row", () => {
    const p = makePayment({ payment_method: "bank_transfer" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-method-${p.id}`);
    expect(el.textContent).toBe("bank_transfer");
  });

  it("shows reference number in row", () => {
    const p = makePayment({ reference_number: "TXN-ABC" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-reference-${p.id}`);
    expect(el.textContent).toBe("TXN-ABC");
  });

  it("shows status badge in row", () => {
    const p = makePayment({ id: "pb-pay", status: "confirmed" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-status-badge-confirmed")).not.toBeNull();
  });
});

// ── PaymentFilters ────────────────────────────────────────────────────────────

describe("PaymentFilters", () => {
  it("renders filter container", () => {
    const onChange = vi.fn();
    render(
      <PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />
    );
    expect(screen.getByTestId("payment-filters")).not.toBeNull();
  });

  it("renders status select", () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    expect(screen.getByTestId("filter-status")).not.toBeNull();
  });

  it("renders method select", () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    expect(screen.getByTestId("filter-method")).not.toBeNull();
  });

  it("renders search input", () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    expect(screen.getByTestId("filter-search")).not.toBeNull();
  });

  it("status select has all status options", () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    const select = screen.getByTestId("filter-status");
    for (const s of PAYMENT_STATUSES) {
      expect(select.innerHTML).toContain(s);
    }
  });

  it("method select has all method options", () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    const select = screen.getByTestId("filter-method");
    for (const m of PAYMENT_METHODS) {
      expect(select.innerHTML).toContain(m);
    }
  });

  it("calls onChange when status changes", async () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByTestId("filter-status"), "confirmed");
    expect(onChange).toHaveBeenCalled();
  });

  it("calls onChange when method changes", async () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByTestId("filter-method"), "cash");
    expect(onChange).toHaveBeenCalled();
  });

  it("calls onChange when search typed", async () => {
    const onChange = vi.fn();
    render(<PaymentFilters filters={{ workspace_id: WS }} onChange={onChange} />);
    await userEvent.type(screen.getByTestId("filter-search"), "REF");
    expect(onChange).toHaveBeenCalled();
  });

  it("reflects current status filter value", () => {
    const onChange = vi.fn();
    render(
      <PaymentFilters filters={{ workspace_id: WS, status: "pending" }} onChange={onChange} />
    );
    const select = screen.getByTestId("filter-status") as HTMLSelectElement;
    expect(select.value).toBe("pending");
  });
});

// ── PaymentCenter ─────────────────────────────────────────────────────────────

describe("PaymentCenter", () => {
  it("renders the container", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-center")).not.toBeNull();
  });

  it("renders the title", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-center-title")).not.toBeNull();
  });

  it("shows summary cards when loaded", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("revenue-summary-cards")).not.toBeNull();
  });

  it("shows summary loading state", () => {
    mockRevenueSummary.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useRevenueSummary>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("summary-loading")).not.toBeNull();
  });

  it("shows summary error state", () => {
    mockRevenueSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as ReturnType<typeof useRevenueSummary>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("summary-error")).not.toBeNull();
  });

  it("shows empty list when no payments", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-list-empty")).not.toBeNull();
  });

  it("shows payment table when payments exist", () => {
    mockPaymentList.mockReturnValue({
      data: { data: makePaymentListOut([makePayment()]) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-table")).not.toBeNull();
  });

  it("shows list loading state", () => {
    mockPaymentList.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-list-loading")).not.toBeNull();
  });

  it("shows list error state", () => {
    mockPaymentList.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fail"),
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-list-error")).not.toBeNull();
  });

  it("shows total count", () => {
    mockPaymentList.mockReturnValue({
      data: { data: makePaymentListOut([makePayment()], { total: 42 }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-total-count").textContent).toContain("42");
  });

  it("shows load-more button when has_more is true", () => {
    mockPaymentList.mockReturnValue({
      data: {
        data: makePaymentListOut([makePayment()], {
          has_more: true,
          next_cursor: "cursor-abc",
        }),
      },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("load-more-btn")).not.toBeNull();
  });

  it("no load-more when has_more is false", () => {
    mockPaymentList.mockReturnValue({
      data: { data: makePaymentListOut([makePayment()], { has_more: false }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.queryByTestId("load-more-btn")).toBeNull();
  });

  it("opens record-payment dialog when button clicked", async () => {
    render(<PaymentCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("open-record-payment-btn"));
    expect(screen.getByTestId("payment-dialog")).not.toBeNull();
  });

  it("closes dialog when cancel clicked inside it", async () => {
    render(<PaymentCenter workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("open-record-payment-btn"));
    expect(screen.getByTestId("payment-dialog")).not.toBeNull();
    await userEvent.click(screen.getByTestId("payment-cancel-btn"));
    expect(screen.queryByTestId("payment-dialog")).toBeNull();
  });

  it("shows payment filters section", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-filters")).not.toBeNull();
  });
});

// ── InvoicePaymentSection ─────────────────────────────────────────────────────

describe("InvoicePaymentSection", () => {
  it("renders the section container", () => {
    render(
      <InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />
    );
    expect(screen.getByTestId("invoice-payment-section")).not.toBeNull();
  });

  it("renders add payment button", () => {
    render(
      <InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />
    );
    expect(screen.getByTestId("add-payment-to-invoice-btn")).not.toBeNull();
  });

  it("opens payment dialog on add click", async () => {
    render(
      <InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />
    );
    await userEvent.click(screen.getByTestId("add-payment-to-invoice-btn"));
    expect(screen.getByTestId("payment-dialog")).not.toBeNull();
  });

  it("closes dialog on cancel", async () => {
    render(
      <InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />
    );
    await userEvent.click(screen.getByTestId("add-payment-to-invoice-btn"));
    await userEvent.click(screen.getByTestId("payment-cancel-btn"));
    expect(screen.queryByTestId("payment-dialog")).toBeNull();
  });

  it("shows payment history", () => {
    render(
      <InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />
    );
    expect(screen.getByTestId("payment-history")).not.toBeNull();
  });
});

// ── PaymentDetailPanel ────────────────────────────────────────────────────────

describe("PaymentDetailPanel", () => {
  it("shows loading state", () => {
    mockPaymentDetail.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("payment-detail-loading")).not.toBeNull();
  });

  it("shows error state", () => {
    mockPaymentDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Not found"),
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("payment-detail-error")).not.toBeNull();
  });

  it("shows detail panel when loaded", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment() },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("payment-detail-panel")).not.toBeNull();
  });

  it("shows amount in detail", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ amount: "9999.00" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    const el = screen.getByTestId("detail-amount");
    expect(el.textContent).toContain("₹");
  });

  it("shows payment date", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ payment_date: "2026-07-15" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-date").textContent).toBe("2026-07-15");
  });

  it("shows payment method", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ payment_method: "cheque" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-method").textContent).toBe("cheque");
  });

  it("shows reference number", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ reference_number: "CHQ-007" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-reference").textContent).toBe("CHQ-007");
  });

  it("shows status badge", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "confirmed" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("payment-status-badge-confirmed")).not.toBeNull();
  });

  it("shows confirm button for pending payment", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "pending" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-confirm-btn")).not.toBeNull();
  });

  it("shows cancel button for confirmed payment", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "confirmed" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-cancel-btn")).not.toBeNull();
  });

  it("no confirm button for confirmed payment", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "confirmed" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.queryByTestId("detail-confirm-btn")).toBeNull();
  });

  it("no buttons for cancelled payment", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "cancelled" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.queryByTestId("detail-confirm-btn")).toBeNull();
    expect(screen.queryByTestId("detail-cancel-btn")).toBeNull();
  });

  it("calls confirmMutation.mutate on confirm click", async () => {
    const mutate = vi.fn();
    mockConfirmPayment.mockReturnValue({
      mutate,
      mutateAsync: vi.fn(),
      isPending: false,
    } as ReturnType<typeof useConfirmPayment>);
    const p = makePayment({ status: "pending" });
    mockPaymentDetail.mockReturnValue({
      data: { data: p },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("detail-confirm-btn"));
    expect(mutate).toHaveBeenCalledWith({ id: p.id, invoiceId: p.invoice_id });
  });

  it("calls cancelMutation.mutate on cancel click", async () => {
    const mutate = vi.fn();
    mockCancelPayment.mockReturnValue({
      mutate,
      mutateAsync: vi.fn(),
      isPending: false,
    } as ReturnType<typeof useCancelPayment>);
    const p = makePayment({ status: "confirmed" });
    mockPaymentDetail.mockReturnValue({
      data: { data: p },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    await userEvent.click(screen.getByTestId("detail-cancel-btn"));
    expect(mutate).toHaveBeenCalledWith({ id: p.id, invoiceId: p.invoice_id });
  });

  it("disables confirm button while pending", () => {
    mockConfirmPayment.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: true,
    } as ReturnType<typeof useConfirmPayment>);
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ status: "pending" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect((screen.getByTestId("detail-confirm-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows notes when present", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ notes: "test note" }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-notes").textContent).toBe("test note");
  });

  it("shows dash for null notes", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ notes: null }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-notes").textContent).toBe("—");
  });
});

// ── Types & constants ─────────────────────────────────────────────────────────

describe("PAYMENT_METHODS constant", () => {
  it("has 6 methods", () => {
    expect(PAYMENT_METHODS).toHaveLength(6);
  });

  it("includes cash", () => {
    expect(PAYMENT_METHODS).toContain("cash");
  });

  it("includes bank_transfer", () => {
    expect(PAYMENT_METHODS).toContain("bank_transfer");
  });

  it("includes upi", () => {
    expect(PAYMENT_METHODS).toContain("upi");
  });

  it("includes credit_card", () => {
    expect(PAYMENT_METHODS).toContain("credit_card");
  });

  it("includes cheque", () => {
    expect(PAYMENT_METHODS).toContain("cheque");
  });

  it("includes other", () => {
    expect(PAYMENT_METHODS).toContain("other");
  });
});

describe("PAYMENT_STATUSES constant", () => {
  it("has 3 statuses", () => {
    expect(PAYMENT_STATUSES).toHaveLength(3);
  });

  it("includes pending", () => {
    expect(PAYMENT_STATUSES).toContain("pending");
  });

  it("includes confirmed", () => {
    expect(PAYMENT_STATUSES).toContain("confirmed");
  });

  it("includes cancelled", () => {
    expect(PAYMENT_STATUSES).toContain("cancelled");
  });
});

// ── Multi-payment display ─────────────────────────────────────────────────────

describe("Multiple payments rendering", () => {
  it("renders multiple payment rows", () => {
    const p1 = makePayment({ id: "pay-a", status: "pending" });
    const p2 = makePayment({ id: "pay-b", status: "confirmed" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p1, p2] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-row-pay-a")).not.toBeNull();
    expect(screen.getByTestId("payment-row-pay-b")).not.toBeNull();
  });

  it("renders distinct statuses for each row", () => {
    const p1 = makePayment({ id: "sp1", status: "pending" });
    const p2 = makePayment({ id: "sp2", status: "cancelled" });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p1, p2] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByTestId("payment-status-badge-pending")).not.toBeNull();
    expect(screen.getByTestId("payment-status-badge-cancelled")).not.toBeNull();
  });

  it("payment table in PaymentCenter shows all rows", () => {
    const items = [
      makePayment({ id: "pc-a" }),
      makePayment({ id: "pc-b" }),
      makePayment({ id: "pc-c" }),
    ];
    mockPaymentList.mockReturnValue({
      data: { data: makePaymentListOut(items, { total: 3 }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentList>);
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-row-pc-a")).not.toBeNull();
    expect(screen.getByTestId("payment-row-pc-b")).not.toBeNull();
    expect(screen.getByTestId("payment-row-pc-c")).not.toBeNull();
  });
});

// ── Edge cases ────────────────────────────────────────────────────────────────

describe("Edge cases", () => {
  it("PaymentStatusBadge shows text for all statuses", () => {
    for (const s of PAYMENT_STATUSES) {
      const { unmount } = render(<PaymentStatusBadge status={s} />);
      const el = screen.getByTestId(`payment-status-badge-${s}`);
      expect(el.textContent).toBe(s);
      unmount();
    }
  });

  it("RevenueSummaryCards handles non-numeric string gracefully", () => {
    const summary = makeSummary({ total_collected: "N/A" });
    render(<RevenueSummaryCards summary={summary} />);
    const el = screen.getByTestId("summary-collected");
    expect(el.textContent).toContain("—");
  });

  it("PaymentHistory renders heading", () => {
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    expect(screen.getByText("Payment History")).not.toBeNull();
  });

  it("InvoicePaymentSection has Payments heading", () => {
    render(<InvoicePaymentSection invoiceId={INV} customerId={CUST} workspaceId={WS} />);
    expect(screen.getByText("Payments")).not.toBeNull();
  });

  it("PaymentCenter title text", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByText("Payment Management")).not.toBeNull();
  });

  it("PaymentCenter total count shows 0 when empty", () => {
    render(<PaymentCenter workspaceId={WS} />);
    expect(screen.getByTestId("payment-total-count").textContent).toContain("0");
  });

  it("PaymentDialog has dialog role", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={vi.fn()} />
    );
    expect(screen.getByRole("dialog")).not.toBeNull();
  });

  it("PaymentDialog form has data-testid", () => {
    render(
      <PaymentDialog mode="create" workspaceId={WS} invoiceId={INV} customerId={CUST} onClose={vi.fn()} />
    );
    expect(screen.getByTestId("payment-form")).not.toBeNull();
  });

  it("null amount in PaymentHistory shows dash", () => {
    const p = makePayment({ amount: null });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-amount-${p.id}`);
    expect(el.textContent).toBe("—");
  });

  it("null payment_date in row shows dash", () => {
    const p = makePayment({ payment_date: null });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-date-${p.id}`);
    expect(el.textContent).toBe("—");
  });

  it("null payment_method in row shows dash", () => {
    const p = makePayment({ payment_method: null });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-method-${p.id}`);
    expect(el.textContent).toBe("—");
  });

  it("null reference_number in row shows dash", () => {
    const p = makePayment({ reference_number: null });
    mockPaymentsByInvoice.mockReturnValue({
      data: { data: [p] },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentsByInvoice>);
    render(<PaymentHistory invoiceId={INV} workspaceId={WS} />);
    const el = screen.getByTestId(`payment-reference-${p.id}`);
    expect(el.textContent).toBe("—");
  });

  it("null amount in detail panel shows dash", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ amount: null }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-amount").textContent).toBe("—");
  });

  it("null payment_method in detail shows dash", () => {
    mockPaymentDetail.mockReturnValue({
      data: { data: makePayment({ payment_method: null }) },
      isLoading: false,
      error: null,
    } as ReturnType<typeof usePaymentDetail>);
    render(<PaymentDetailPanel paymentId={PAY_ID} workspaceId={WS} />);
    expect(screen.getByTestId("detail-method").textContent).toBe("—");
  });
});

// ── RevenueSummaryCards extended ──────────────────────────────────────────────

describe("RevenueSummaryCards — extended", () => {
  it("renders 4 cards total", () => {
    const { container } = render(<RevenueSummaryCards summary={makeSummary()} />);
    const cards = container.querySelectorAll('[class*="rounded border"]');
    expect(cards.length).toBe(4);
  });

  it("outstanding label text", () => {
    render(<RevenueSummaryCards summary={makeSummary()} />);
    expect(screen.getByText("Outstanding")).not.toBeNull();
  });

  it("overdue label text", () => {
    render(<RevenueSummaryCards summary={makeSummary()} />);
    expect(screen.getByText("Overdue")).not.toBeNull();
  });

  it("partial label text", () => {
    render(<RevenueSummaryCards summary={makeSummary()} />);
    expect(screen.getByText("Partial Invoices")).not.toBeNull();
  });

  it("collected label text", () => {
    render(<RevenueSummaryCards summary={makeSummary()} />);
    expect(screen.getByText("Total Collected")).not.toBeNull();
  });

  it("partial count of zero renders correctly", () => {
    render(<RevenueSummaryCards summary={makeSummary({ partial_payment_invoices: 0 })} />);
    const el = screen.getByTestId("summary-partial");
    expect(el.textContent).toContain("0");
  });

  it("large collected amount formats with commas", () => {
    render(<RevenueSummaryCards summary={makeSummary({ total_collected: "1000000.00" })} />);
    const el = screen.getByTestId("summary-collected");
    expect(el.textContent).toContain("₹");
    expect(el.textContent).toContain(",");
  });

  it("overdue of zero renders ₹0", () => {
    render(<RevenueSummaryCards summary={makeSummary({ total_overdue: "0.00" })} />);
    const el = screen.getByTestId("summary-overdue");
    expect(el.textContent).toContain("₹");
  });

  it("outstanding renders ₹ symbol", () => {
    render(<RevenueSummaryCards summary={makeSummary({ total_outstanding: "1500.00" })} />);
    const el = screen.getByTestId("summary-outstanding");
    expect(el.textContent).toContain("₹");
  });

  it("summary cards container has data-testid", () => {
    render(<RevenueSummaryCards summary={makeSummary()} />);
    expect(screen.getByTestId("revenue-summary-cards")).not.toBeNull();
  });
});
