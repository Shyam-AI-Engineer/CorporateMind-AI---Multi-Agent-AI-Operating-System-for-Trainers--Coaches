export type ReportType =
  | "customers"
  | "training"
  | "invoices"
  | "payments"
  | "executive_kpis"
  | "workflow_analytics"
  | "audit_logs";

export type ReportFormat = "csv" | "xlsx";

export type ReportStatus = "pending" | "ready" | "failed";

export interface ReportExport {
  id: string;
  tenant_id: string;
  workspace_id: string;
  report_type: ReportType;
  format: ReportFormat;
  status: ReportStatus;
  generated_by: string;
  generated_at: string | null;
  download_name: string | null;
  row_count: number | null;
  file_size_bytes: number | null;
  created_at: string;
}

export interface GenerateReportRequest {
  workspace_id: string;
  report_type: ReportType;
  format: ReportFormat;
  date_from?: string;
  date_to?: string;
}

export interface ReportExportListResponse {
  items: ReportExport[];
  total: number;
}

export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  customers: "Customers",
  training: "Training Engagements",
  invoices: "Invoices",
  payments: "Payments",
  executive_kpis: "Executive KPIs",
  workflow_analytics: "Workflow Analytics",
  audit_logs: "Audit Logs",
};

export const REPORT_FORMAT_LABELS: Record<ReportFormat, string> = {
  csv: "CSV",
  xlsx: "Excel (XLSX)",
};
