export type InvoiceStatus =
  | "draft"
  | "issued"
  | "paid"
  | "cancelled"
  | "overdue";

export interface CustomerInvoice {
  id: string;
  workspace_id: string;
  customer_id: string;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  amount: string | null;
  tax_amount: string | null;
  total_amount: string | null;
  currency: string | null;
  status: InvoiceStatus;
  payment_date: string | null;
  renewal_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerInvoiceListOut {
  items: CustomerInvoice[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface CustomerInvoiceCreate {
  workspace_id: string;
  customer_id: string;
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  amount?: string | null;
  tax_amount?: string | null;
  total_amount?: string | null;
  currency?: string;
  notes?: string | null;
  renewal_id?: string | null;
}

export interface CustomerInvoiceUpdate {
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  amount?: string | null;
  tax_amount?: string | null;
  total_amount?: string | null;
  currency?: string | null;
  notes?: string | null;
}

export interface MarkInvoicePaid {
  payment_date: string;
}

export interface CustomerInvoiceFilters {
  workspace_id: string;
  customer_id?: string;
  status?: InvoiceStatus;
  invoice_date_from?: string;
  invoice_date_to?: string;
  due_date_from?: string;
  due_date_to?: string;
  renewal_id?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}

export interface InvoiceKPIsOut {
  total_outstanding: string;
  total_paid: string;
  total_overdue: string;
  count_draft: number;
  count_issued: number;
  count_paid: number;
  count_overdue: number;
  count_cancelled: number;
}

export const INVOICE_STATUSES: InvoiceStatus[] = [
  "draft",
  "issued",
  "paid",
  "cancelled",
  "overdue",
];
