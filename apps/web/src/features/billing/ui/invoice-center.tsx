"use client";

import { useState } from "react";
import {
  useInvoiceList,
  useInvoiceKPIs,
  useInvoiceDetail,
  useInvoicesByCustomer,
  useCreateInvoice,
  useUpdateInvoice,
  useIssueInvoice,
  useMarkInvoicePaid,
  useCancelInvoice,
} from "@/features/billing/api/use-billing";
import type {
  CustomerInvoice,
  CustomerInvoiceCreate,
  CustomerInvoiceFilters,
  InvoiceKPIsOut,
  InvoiceStatus,
  MarkInvoicePaid,
} from "@/features/billing/types-billing";
import { INVOICE_STATUSES } from "@/features/billing/types-billing";

// ── StatusBadge ───────────────────────────────────────────────────────────────

function invoiceStatusColor(s: InvoiceStatus): string {
  switch (s) {
    case "draft":     return "bg-gray-100 text-gray-700";
    case "issued":    return "bg-blue-100 text-blue-800";
    case "paid":      return "bg-green-100 text-green-800";
    case "cancelled": return "bg-red-100 text-red-700";
    case "overdue":   return "bg-orange-100 text-orange-800";
  }
}

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      data-testid={`invoice-status-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${invoiceStatusColor(status)}`}
    >
      {status}
    </span>
  );
}

// ── InvoiceKPISection ─────────────────────────────────────────────────────────

export function InvoiceKPISection({ kpis }: { kpis: InvoiceKPIsOut }) {
  const fmt = (v: string) => {
    const n = parseFloat(v);
    return isNaN(n) ? "—" : `₹${n.toLocaleString("en-IN")}`;
  };
  return (
    <div data-testid="invoice-kpi-section" className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div data-testid="kpi-outstanding" className="rounded border p-4">
        <p className="text-xs text-gray-500">Outstanding</p>
        <p className="text-lg font-semibold">{fmt(kpis.total_outstanding)}</p>
      </div>
      <div data-testid="kpi-paid" className="rounded border p-4">
        <p className="text-xs text-gray-500">Paid</p>
        <p className="text-lg font-semibold">{fmt(kpis.total_paid)}</p>
      </div>
      <div data-testid="kpi-overdue" className="rounded border p-4">
        <p className="text-xs text-gray-500">Overdue</p>
        <p className="text-lg font-semibold">{fmt(kpis.total_overdue)}</p>
      </div>
      <div data-testid="kpi-counts" className="rounded border p-4">
        <p className="text-xs text-gray-500">Draft / Issued</p>
        <p className="text-lg font-semibold">
          {kpis.count_draft} / {kpis.count_issued}
        </p>
      </div>
    </div>
  );
}

// ── InvoiceTable ──────────────────────────────────────────────────────────────

export function InvoiceTable({
  items,
  onSelect,
}: {
  items: CustomerInvoice[];
  onSelect: (inv: CustomerInvoice) => void;
}) {
  if (items.length === 0) {
    return <p data-testid="invoice-table-empty">No invoices found.</p>;
  }
  return (
    <table data-testid="invoice-table" className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-xs text-gray-500">
          <th className="py-2 pr-4">Number</th>
          <th className="py-2 pr-4">Status</th>
          <th className="py-2 pr-4">Date</th>
          <th className="py-2 pr-4">Due</th>
          <th className="py-2 pr-4">Total</th>
          <th className="py-2" />
        </tr>
      </thead>
      <tbody>
        {items.map((inv) => (
          <tr
            key={inv.id}
            data-testid={`invoice-row-${inv.id}`}
            className="border-b hover:bg-gray-50 cursor-pointer"
          >
            <td className="py-2 pr-4 font-mono text-xs">
              {inv.invoice_number ?? "—"}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={inv.status} />
            </td>
            <td className="py-2 pr-4">{inv.invoice_date ?? "—"}</td>
            <td className="py-2 pr-4">{inv.due_date ?? "—"}</td>
            <td className="py-2 pr-4">
              {inv.total_amount ? `₹${parseFloat(inv.total_amount).toLocaleString("en-IN")}` : "—"}
            </td>
            <td className="py-2">
              <button
                data-testid={`invoice-view-${inv.id}`}
                className="text-xs text-blue-600 hover:underline"
                onClick={() => onSelect(inv)}
              >
                View
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── InvoiceDialog (create) ────────────────────────────────────────────────────

export function InvoiceDialog({
  workspaceId,
  customerId,
  open,
  onClose,
}: {
  workspaceId: string;
  customerId: string;
  open: boolean;
  onClose: () => void;
}) {
  const createMut = useCreateInvoice(workspaceId);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [totalAmount, setTotalAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const body: CustomerInvoiceCreate = {
      workspace_id: workspaceId,
      customer_id: customerId,
      invoice_number: invoiceNumber || null,
      invoice_date: invoiceDate || null,
      due_date: dueDate || null,
      total_amount: totalAmount || null,
      notes: notes || null,
    };
    try {
      await createMut.mutateAsync(body);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create invoice");
    }
  };

  return (
    <div data-testid="invoice-dialog" role="dialog" aria-modal="true">
      <h2 className="text-base font-semibold mb-4">New Invoice</h2>
      <form onSubmit={handleSubmit} data-testid="invoice-form">
        <div className="space-y-3">
          <input
            data-testid="field-invoice-number"
            placeholder="Invoice number (optional)"
            value={invoiceNumber}
            onChange={(e) => setInvoiceNumber(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
          <input
            data-testid="field-invoice-date"
            type="date"
            placeholder="Invoice date"
            value={invoiceDate}
            onChange={(e) => setInvoiceDate(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
          <input
            data-testid="field-due-date"
            type="date"
            placeholder="Due date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
          <input
            data-testid="field-total-amount"
            placeholder="Total amount"
            value={totalAmount}
            onChange={(e) => setTotalAmount(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
          <textarea
            data-testid="field-notes"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
            rows={3}
          />
        </div>
        {error && <p data-testid="invoice-dialog-error" className="text-red-600 text-sm mt-2">{error}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button
            type="button"
            data-testid="invoice-dialog-cancel"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            data-testid="invoice-dialog-submit"
            disabled={createMut.isPending}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {createMut.isPending ? "Creating…" : "Create Invoice"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── PaymentDialog ─────────────────────────────────────────────────────────────

export function PaymentDialog({
  invoiceId,
  workspaceId,
  open,
  onClose,
}: {
  invoiceId: string;
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}) {
  const markPaidMut = useMarkInvoicePaid(workspaceId);
  const [paymentDate, setPaymentDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!paymentDate) {
      setError("Payment date is required");
      return;
    }
    const body: MarkInvoicePaid = { payment_date: paymentDate };
    try {
      await markPaidMut.mutateAsync({ id: invoiceId, body });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to mark paid");
    }
  };

  return (
    <div data-testid="payment-dialog" role="dialog" aria-modal="true">
      <h2 className="text-base font-semibold mb-4">Mark as Paid</h2>
      <form onSubmit={handleSubmit} data-testid="payment-form">
        <input
          data-testid="field-payment-date"
          type="date"
          value={paymentDate}
          onChange={(e) => setPaymentDate(e.target.value)}
          className="w-full border rounded px-3 py-2 text-sm"
          required
        />
        {error && <p data-testid="payment-dialog-error" className="text-red-600 text-sm mt-2">{error}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button
            type="button"
            data-testid="payment-dialog-cancel"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            data-testid="payment-dialog-submit"
            disabled={markPaidMut.isPending}
            className="rounded bg-green-600 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {markPaidMut.isPending ? "Saving…" : "Mark Paid"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── InvoiceDrawer ─────────────────────────────────────────────────────────────

export function InvoiceDrawer({
  invoiceId,
  workspaceId,
  open,
  onClose,
}: {
  invoiceId: string | null;
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading } = useInvoiceDetail(open ? invoiceId : null);
  const issueMut = useIssueInvoice(workspaceId);
  const cancelMut = useCancelInvoice(workspaceId);
  const [showPayment, setShowPayment] = useState(false);

  if (!open || !invoiceId) return null;

  const inv = data?.data;

  return (
    <aside data-testid="invoice-drawer" className="fixed right-0 top-0 h-full w-96 bg-white shadow-xl p-6">
      <button
        data-testid="invoice-drawer-close"
        onClick={onClose}
        className="absolute right-4 top-4 text-gray-500"
        aria-label="Close drawer"
      >
        ✕
      </button>
      <h2 className="text-base font-semibold mb-4">Invoice Detail</h2>

      {isLoading && <p data-testid="drawer-loading">Loading…</p>}
      {!isLoading && !inv && <p data-testid="drawer-not-found">Invoice not found.</p>}

      {inv && (
        <div data-testid="drawer-content">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-gray-500">Number</dt>
              <dd data-testid="drawer-invoice-number">{inv.invoice_number ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Status</dt>
              <dd><StatusBadge status={inv.status} /></dd>
            </div>
            <div>
              <dt className="text-gray-500">Total</dt>
              <dd data-testid="drawer-total">
                {inv.total_amount
                  ? `₹${parseFloat(inv.total_amount).toLocaleString("en-IN")}`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Due date</dt>
              <dd data-testid="drawer-due-date">{inv.due_date ?? "—"}</dd>
            </div>
            {inv.payment_date && (
              <div>
                <dt className="text-gray-500">Paid on</dt>
                <dd data-testid="drawer-payment-date">{inv.payment_date}</dd>
              </div>
            )}
            {inv.notes && (
              <div>
                <dt className="text-gray-500">Notes</dt>
                <dd data-testid="drawer-notes">{inv.notes}</dd>
              </div>
            )}
          </dl>

          <div className="mt-6 flex flex-wrap gap-2">
            {inv.status === "draft" && (
              <button
                data-testid="drawer-action-issue"
                disabled={issueMut.isPending}
                onClick={() => issueMut.mutate(inv.id)}
                className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
              >
                Issue
              </button>
            )}
            {inv.status === "issued" && (
              <button
                data-testid="drawer-action-mark-paid"
                onClick={() => setShowPayment(true)}
                className="rounded bg-green-600 px-3 py-1.5 text-xs text-white"
              >
                Mark Paid
              </button>
            )}
            {["draft", "issued", "overdue"].includes(inv.status) && (
              <button
                data-testid="drawer-action-cancel"
                disabled={cancelMut.isPending}
                onClick={() => cancelMut.mutate(inv.id)}
                className="rounded border border-red-300 px-3 py-1.5 text-xs text-red-600 disabled:opacity-50"
              >
                Cancel
              </button>
            )}
          </div>

          {showPayment && (
            <div className="mt-4">
              <PaymentDialog
                invoiceId={inv.id}
                workspaceId={workspaceId}
                open={showPayment}
                onClose={() => setShowPayment(false)}
              />
            </div>
          )}
        </div>
      )}
    </aside>
  );
}

// ── InvoiceCenter ─────────────────────────────────────────────────────────────

export function InvoiceCenter({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | "">("");
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<CustomerInvoice | null>(null);

  const filters: CustomerInvoiceFilters = {
    workspace_id: workspaceId,
    status: statusFilter || undefined,
    search: search || undefined,
  };

  const { data: kpisData, isLoading: kpisLoading } = useInvoiceKPIs(workspaceId);
  const { data: listData, isLoading: listLoading, isError } = useInvoiceList(filters);

  const items = listData?.data.items ?? [];
  const kpis = kpisData?.data;

  return (
    <div data-testid="invoice-center">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Invoices</h1>
        <button
          data-testid="invoice-create-btn"
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white"
        >
          New Invoice
        </button>
      </div>

      {kpisLoading && <p data-testid="kpis-loading">Loading KPIs…</p>}
      {kpis && <InvoiceKPISection kpis={kpis} />}

      <div className="mt-4 flex gap-3">
        <input
          data-testid="invoice-search"
          placeholder="Search invoices…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded border px-3 py-2 text-sm"
        />
        <select
          data-testid="invoice-status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as InvoiceStatus | "")}
          className="rounded border px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          {INVOICE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        {listLoading && <p data-testid="invoice-list-loading">Loading invoices…</p>}
        {isError && <p data-testid="invoice-list-error">Failed to load invoices.</p>}
        {!listLoading && !isError && (
          <InvoiceTable items={items} onSelect={setSelectedInvoice} />
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md shadow-xl">
            <InvoiceDialog
              workspaceId={workspaceId}
              customerId=""
              open={showCreate}
              onClose={() => setShowCreate(false)}
            />
          </div>
        </div>
      )}

      {selectedInvoice && (
        <InvoiceDrawer
          invoiceId={selectedInvoice.id}
          workspaceId={workspaceId}
          open={true}
          onClose={() => setSelectedInvoice(null)}
        />
      )}
    </div>
  );
}

// ── CustomerInvoicesTab (embedded in Customer Detail) ─────────────────────────

export function CustomerInvoicesTab({
  customerId,
  workspaceId,
}: {
  customerId: string;
  workspaceId: string;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<CustomerInvoice | null>(null);
  const { data, isLoading } = useInvoicesByCustomer(customerId, workspaceId);
  const items = data?.data.items ?? [];

  return (
    <div data-testid="customer-invoices-tab">
      <div className="flex justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-700">
          Invoices ({items.length})
        </h3>
        <button
          data-testid="customer-invoices-add-btn"
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-600 px-3 py-1 text-xs text-white"
        >
          Add Invoice
        </button>
      </div>

      {isLoading && <p data-testid="customer-invoices-loading">Loading…</p>}
      {!isLoading && (
        <InvoiceTable items={items} onSelect={setSelectedInvoice} />
      )}

      {showCreate && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md shadow-xl">
            <InvoiceDialog
              workspaceId={workspaceId}
              customerId={customerId}
              open={showCreate}
              onClose={() => setShowCreate(false)}
            />
          </div>
        </div>
      )}

      {selectedInvoice && (
        <InvoiceDrawer
          invoiceId={selectedInvoice.id}
          workspaceId={workspaceId}
          open={true}
          onClose={() => setSelectedInvoice(null)}
        />
      )}
    </div>
  );
}

// ── LinkedInvoiceBadge (on Renewal Detail) ────────────────────────────────────

export function LinkedInvoiceBadge({
  invoiceId,
  workspaceId,
}: {
  invoiceId: string | null | undefined;
  workspaceId: string;
}) {
  const { data, isLoading } = useInvoiceDetail(invoiceId ?? null);
  const inv = data?.data;

  if (!invoiceId) return null;
  if (isLoading) return <span data-testid="linked-invoice-loading" className="text-xs text-gray-400">Loading…</span>;
  if (!inv) return null;

  return (
    <div data-testid="linked-invoice-badge" className="flex items-center gap-2 rounded border px-3 py-2">
      <span className="text-xs text-gray-500">Invoice</span>
      <span data-testid="linked-invoice-number" className="font-mono text-xs">
        {inv.invoice_number ?? inv.id.slice(0, 8)}
      </span>
      <StatusBadge status={inv.status} />
      {inv.total_amount && (
        <span data-testid="linked-invoice-amount" className="text-xs font-medium">
          ₹{parseFloat(inv.total_amount).toLocaleString("en-IN")}
        </span>
      )}
    </div>
  );
}
