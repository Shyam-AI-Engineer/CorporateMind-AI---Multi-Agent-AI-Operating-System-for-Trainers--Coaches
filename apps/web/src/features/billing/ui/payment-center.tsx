"use client";

import { useState } from "react";
import {
  useRevenueSummary,
  usePaymentList,
  usePaymentsByInvoice,
  usePaymentDetail,
  useRecordPayment,
  useUpdatePayment,
  useConfirmPayment,
  useCancelPayment,
} from "@/features/billing/api/use-billing";
import type {
  InvoicePayment,
  InvoicePaymentCreate,
  InvoicePaymentFilters,
  InvoicePaymentUpdate,
  PaymentMethod,
  PaymentStatus,
  RevenueSummaryOut,
} from "@/features/billing/types-billing";
import { PAYMENT_METHODS, PAYMENT_STATUSES } from "@/features/billing/types-billing";

// ── PaymentStatusBadge ────────────────────────────────────────────────────────

function paymentStatusColor(s: PaymentStatus): string {
  switch (s) {
    case "pending":   return "bg-yellow-100 text-yellow-800";
    case "confirmed": return "bg-green-100 text-green-800";
    case "cancelled": return "bg-red-100 text-red-700";
  }
}

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return (
    <span
      data-testid={`payment-status-badge-${status}`}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${paymentStatusColor(status)}`}
    >
      {status}
    </span>
  );
}

// ── RevenueSummaryCards ───────────────────────────────────────────────────────

export function RevenueSummaryCards({ summary }: { summary: RevenueSummaryOut }) {
  const fmt = (v: string) => {
    const n = parseFloat(v);
    return isNaN(n) ? "—" : `₹${n.toLocaleString("en-IN")}`;
  };
  return (
    <div data-testid="revenue-summary-cards" className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div data-testid="summary-collected" className="rounded border p-4">
        <p className="text-xs text-gray-500">Total Collected</p>
        <p className="text-lg font-semibold">{fmt(summary.total_collected)}</p>
      </div>
      <div data-testid="summary-outstanding" className="rounded border p-4">
        <p className="text-xs text-gray-500">Outstanding</p>
        <p className="text-lg font-semibold">{fmt(summary.total_outstanding)}</p>
      </div>
      <div data-testid="summary-overdue" className="rounded border p-4">
        <p className="text-xs text-gray-500">Overdue</p>
        <p className="text-lg font-semibold">{fmt(summary.total_overdue)}</p>
      </div>
      <div data-testid="summary-partial" className="rounded border p-4">
        <p className="text-xs text-gray-500">Partial Invoices</p>
        <p className="text-lg font-semibold">{summary.partial_payment_invoices}</p>
      </div>
    </div>
  );
}

// ── PaymentDialog ─────────────────────────────────────────────────────────────

interface PaymentDialogProps {
  mode: "create" | "edit";
  workspaceId: string;
  invoiceId?: string;
  customerId?: string;
  payment?: InvoicePayment;
  onClose: () => void;
}

export function PaymentDialog({
  mode,
  workspaceId,
  invoiceId,
  customerId,
  payment,
  onClose,
}: PaymentDialogProps) {
  const [amount, setAmount] = useState(payment?.amount ?? "");
  const [paymentDate, setPaymentDate] = useState(payment?.payment_date ?? "");
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | "">(
    payment?.payment_method ?? ""
  );
  const [referenceNumber, setReferenceNumber] = useState(
    payment?.reference_number ?? ""
  );
  const [notes, setNotes] = useState(payment?.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  const recordMutation = useRecordPayment(workspaceId);
  const updateMutation = useUpdatePayment(workspaceId);

  const isPending =
    recordMutation.isPending || updateMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (mode === "create") {
      if (!invoiceId || !customerId) {
        setError("Invoice and customer are required");
        return;
      }
      const body: InvoicePaymentCreate = {
        workspace_id: workspaceId,
        invoice_id: invoiceId,
        customer_id: customerId,
        amount,
        payment_date: paymentDate || null,
        payment_method: (paymentMethod || null) as PaymentMethod | null,
        reference_number: referenceNumber || null,
        notes: notes || null,
      };
      try {
        await recordMutation.mutateAsync(body);
        onClose();
      } catch (err: unknown) {
        setError((err as Error)?.message ?? "Failed to record payment");
      }
    } else if (payment) {
      const body: InvoicePaymentUpdate = {
        amount: amount || null,
        payment_date: paymentDate || null,
        payment_method: (paymentMethod || null) as PaymentMethod | null,
        reference_number: referenceNumber || null,
        notes: notes || null,
      };
      try {
        await updateMutation.mutateAsync({
          id: payment.id,
          body,
          invoiceId: payment.invoice_id,
        });
        onClose();
      } catch (err: unknown) {
        setError((err as Error)?.message ?? "Failed to update payment");
      }
    }
  };

  return (
    <div data-testid="payment-dialog" role="dialog" aria-modal="true">
      <h2 data-testid="dialog-title">
        {mode === "create" ? "Record Payment" : "Edit Payment"}
      </h2>
      <form data-testid="payment-form" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="payment-amount">Amount</label>
          <input
            id="payment-amount"
            data-testid="payment-amount-input"
            type="text"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="payment-date">Payment Date</label>
          <input
            id="payment-date"
            data-testid="payment-date-input"
            type="date"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="payment-method">Method</label>
          <select
            id="payment-method"
            data-testid="payment-method-select"
            value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod)}
          >
            <option value="">Select method</option>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="reference-number">Reference #</label>
          <input
            id="reference-number"
            data-testid="reference-number-input"
            type="text"
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="payment-notes">Notes</label>
          <textarea
            id="payment-notes"
            data-testid="payment-notes-input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        {error && (
          <p data-testid="payment-dialog-error" role="alert">
            {error}
          </p>
        )}
        <div>
          <button
            data-testid="payment-submit-btn"
            type="submit"
            disabled={isPending}
          >
            {isPending ? "Saving…" : mode === "create" ? "Record" : "Update"}
          </button>
          <button data-testid="payment-cancel-btn" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

// ── PaymentRow ────────────────────────────────────────────────────────────────

interface PaymentRowProps {
  payment: InvoicePayment;
  workspaceId: string;
  onEdit: (p: InvoicePayment) => void;
}

function PaymentRow({ payment, workspaceId, onEdit }: PaymentRowProps) {
  const confirmMutation = useConfirmPayment(workspaceId);
  const cancelMutation = useCancelPayment(workspaceId);

  const handleConfirm = () => {
    confirmMutation.mutate({ id: payment.id, invoiceId: payment.invoice_id });
  };

  const handleCancel = () => {
    cancelMutation.mutate({ id: payment.id, invoiceId: payment.invoice_id });
  };

  return (
    <tr data-testid={`payment-row-${payment.id}`}>
      <td data-testid={`payment-amount-${payment.id}`}>
        {payment.amount ? `₹${parseFloat(payment.amount).toLocaleString("en-IN")}` : "—"}
      </td>
      <td data-testid={`payment-date-${payment.id}`}>{payment.payment_date ?? "—"}</td>
      <td data-testid={`payment-method-${payment.id}`}>{payment.payment_method ?? "—"}</td>
      <td data-testid={`payment-reference-${payment.id}`}>
        {payment.reference_number ?? "—"}
      </td>
      <td data-testid={`payment-status-cell-${payment.id}`}>
        <PaymentStatusBadge status={payment.status} />
      </td>
      <td>
        {payment.status === "pending" && (
          <>
            <button
              data-testid={`edit-payment-${payment.id}`}
              onClick={() => onEdit(payment)}
            >
              Edit
            </button>
            <button
              data-testid={`confirm-payment-${payment.id}`}
              onClick={handleConfirm}
              disabled={confirmMutation.isPending}
            >
              Confirm
            </button>
          </>
        )}
        {(payment.status === "pending" || payment.status === "confirmed") && (
          <button
            data-testid={`cancel-payment-${payment.id}`}
            onClick={handleCancel}
            disabled={cancelMutation.isPending}
          >
            Cancel
          </button>
        )}
      </td>
    </tr>
  );
}

// ── PaymentHistory ────────────────────────────────────────────────────────────

interface PaymentHistoryProps {
  invoiceId: string;
  workspaceId: string;
}

export function PaymentHistory({ invoiceId, workspaceId }: PaymentHistoryProps) {
  const [editPayment, setEditPayment] = useState<InvoicePayment | null>(null);
  const { data, isLoading, error } = usePaymentsByInvoice(invoiceId);
  const payments = data?.data ?? [];

  if (isLoading) return <p data-testid="payment-history-loading">Loading payments…</p>;
  if (error) return <p data-testid="payment-history-error">Failed to load payments</p>;

  return (
    <div data-testid="payment-history">
      <h3>Payment History</h3>
      {payments.length === 0 ? (
        <p data-testid="payment-history-empty">No payments recorded</p>
      ) : (
        <table data-testid="payment-history-table">
          <thead>
            <tr>
              <th>Amount</th>
              <th>Date</th>
              <th>Method</th>
              <th>Reference</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <PaymentRow
                key={p.id}
                payment={p}
                workspaceId={workspaceId}
                onEdit={setEditPayment}
              />
            ))}
          </tbody>
        </table>
      )}
      {editPayment && (
        <PaymentDialog
          mode="edit"
          workspaceId={workspaceId}
          payment={editPayment}
          onClose={() => setEditPayment(null)}
        />
      )}
    </div>
  );
}

// ── PaymentFilters ────────────────────────────────────────────────────────────

interface PaymentFiltersProps {
  filters: InvoicePaymentFilters;
  onChange: (f: InvoicePaymentFilters) => void;
}

export function PaymentFilters({ filters, onChange }: PaymentFiltersProps) {
  return (
    <div data-testid="payment-filters" className="flex flex-wrap gap-2">
      <select
        data-testid="filter-status"
        value={filters.status ?? ""}
        onChange={(e) =>
          onChange({ ...filters, status: (e.target.value as PaymentStatus) || undefined })
        }
      >
        <option value="">All statuses</option>
        {PAYMENT_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <select
        data-testid="filter-method"
        value={filters.payment_method ?? ""}
        onChange={(e) =>
          onChange({
            ...filters,
            payment_method: (e.target.value as PaymentMethod) || undefined,
          })
        }
      >
        <option value="">All methods</option>
        {PAYMENT_METHODS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <input
        data-testid="filter-search"
        type="text"
        placeholder="Search reference…"
        value={filters.search ?? ""}
        onChange={(e) => onChange({ ...filters, search: e.target.value || undefined })}
      />
    </div>
  );
}

// ── PaymentCenter ─────────────────────────────────────────────────────────────

interface PaymentCenterProps {
  workspaceId: string;
}

export function PaymentCenter({ workspaceId }: PaymentCenterProps) {
  const [filters, setFilters] = useState<InvoicePaymentFilters>({
    workspace_id: workspaceId,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [invoiceIdForNew, setInvoiceIdForNew] = useState("");
  const [customerIdForNew, setCustomerIdForNew] = useState("");

  const summaryQuery = useRevenueSummary(workspaceId);
  const listQuery = usePaymentList(filters);

  const summary = summaryQuery.data?.data;
  const listData = listQuery.data?.data;
  const payments = listData?.items ?? [];

  return (
    <div data-testid="payment-center">
      <h2 data-testid="payment-center-title">Payment Management</h2>

      {summaryQuery.isLoading && (
        <p data-testid="summary-loading">Loading summary…</p>
      )}
      {summaryQuery.error && (
        <p data-testid="summary-error">Failed to load revenue summary</p>
      )}
      {summary && <RevenueSummaryCards summary={summary} />}

      <div className="flex items-center justify-between">
        <PaymentFilters filters={filters} onChange={setFilters} />
        <button
          data-testid="open-record-payment-btn"
          onClick={() => setShowCreate(true)}
        >
          + Record Payment
        </button>
      </div>

      {listQuery.isLoading && (
        <p data-testid="payment-list-loading">Loading payments…</p>
      )}
      {listQuery.error && (
        <p data-testid="payment-list-error">Failed to load payments</p>
      )}

      {!listQuery.isLoading && !listQuery.error && (
        <>
          {payments.length === 0 ? (
            <p data-testid="payment-list-empty">No payments found</p>
          ) : (
            <table data-testid="payment-table">
              <thead>
                <tr>
                  <th>Amount</th>
                  <th>Date</th>
                  <th>Method</th>
                  <th>Reference</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <PaymentRow
                    key={p.id}
                    payment={p}
                    workspaceId={workspaceId}
                    onEdit={() => {}}
                  />
                ))}
              </tbody>
            </table>
          )}
          {listData?.has_more && (
            <button
              data-testid="load-more-btn"
              onClick={() =>
                setFilters((f) => ({ ...f, cursor: listData.next_cursor ?? undefined }))
              }
            >
              Load more
            </button>
          )}
          <p data-testid="payment-total-count">Total: {listData?.total ?? 0}</p>
        </>
      )}

      {showCreate && (
        <PaymentDialog
          mode="create"
          workspaceId={workspaceId}
          invoiceId={invoiceIdForNew || undefined}
          customerId={customerIdForNew || undefined}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}

// ── InvoicePaymentSection ─────────────────────────────────────────────────────

interface InvoicePaymentSectionProps {
  invoiceId: string;
  customerId: string;
  workspaceId: string;
}

export function InvoicePaymentSection({
  invoiceId,
  customerId,
  workspaceId,
}: InvoicePaymentSectionProps) {
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div data-testid="invoice-payment-section">
      <div className="flex items-center justify-between">
        <h3>Payments</h3>
        <button
          data-testid="add-payment-to-invoice-btn"
          onClick={() => setShowAdd(true)}
        >
          + Add Payment
        </button>
      </div>

      <PaymentHistory invoiceId={invoiceId} workspaceId={workspaceId} />

      {showAdd && (
        <PaymentDialog
          mode="create"
          workspaceId={workspaceId}
          invoiceId={invoiceId}
          customerId={customerId}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  );
}

// ── PaymentDetailPanel ────────────────────────────────────────────────────────

interface PaymentDetailPanelProps {
  paymentId: string;
  workspaceId: string;
}

export function PaymentDetailPanel({ paymentId, workspaceId }: PaymentDetailPanelProps) {
  const { data, isLoading, error } = usePaymentDetail(paymentId);
  const payment = data?.data;
  const confirmMutation = useConfirmPayment(workspaceId);
  const cancelMutation = useCancelPayment(workspaceId);

  if (isLoading) return <p data-testid="payment-detail-loading">Loading…</p>;
  if (error || !payment)
    return <p data-testid="payment-detail-error">Payment not found</p>;

  return (
    <div data-testid="payment-detail-panel">
      <dl>
        <dt>Amount</dt>
        <dd data-testid="detail-amount">
          {payment.amount ? `₹${parseFloat(payment.amount).toLocaleString("en-IN")}` : "—"}
        </dd>
        <dt>Date</dt>
        <dd data-testid="detail-date">{payment.payment_date ?? "—"}</dd>
        <dt>Method</dt>
        <dd data-testid="detail-method">{payment.payment_method ?? "—"}</dd>
        <dt>Reference</dt>
        <dd data-testid="detail-reference">{payment.reference_number ?? "—"}</dd>
        <dt>Status</dt>
        <dd data-testid="detail-status">
          <PaymentStatusBadge status={payment.status} />
        </dd>
        <dt>Notes</dt>
        <dd data-testid="detail-notes">{payment.notes ?? "—"}</dd>
      </dl>
      {payment.status === "pending" && (
        <button
          data-testid="detail-confirm-btn"
          onClick={() =>
            confirmMutation.mutate({ id: payment.id, invoiceId: payment.invoice_id })
          }
          disabled={confirmMutation.isPending}
        >
          Confirm Payment
        </button>
      )}
      {(payment.status === "pending" || payment.status === "confirmed") && (
        <button
          data-testid="detail-cancel-btn"
          onClick={() =>
            cancelMutation.mutate({ id: payment.id, invoiceId: payment.invoice_id })
          }
          disabled={cancelMutation.isPending}
        >
          Cancel Payment
        </button>
      )}
    </div>
  );
}
