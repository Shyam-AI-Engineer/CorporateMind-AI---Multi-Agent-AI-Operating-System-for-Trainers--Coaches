export type RenewalType = "annual" | "quarterly" | "monthly" | "custom";
export type RenewalStatus =
  | "planned"
  | "in_progress"
  | "negotiation"
  | "won"
  | "lost"
  | "cancelled";

export interface CustomerRenewal {
  id: string;
  tenant_id: string;
  workspace_id: string;
  customer_id: string;
  contract_name: string | null;
  contract_value: string | null;
  renewal_type: RenewalType;
  renewal_status: RenewalStatus;
  renewal_date: string | null;
  owner_user_id: string | null;
  probability: number | null;
  expected_value: string | null;
  proposal_id: string | null;
  notes: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerRenewalListOut {
  items: CustomerRenewal[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface CustomerRenewalCreate {
  workspace_id: string;
  customer_id: string;
  contract_name?: string;
  contract_value?: string;
  renewal_type?: RenewalType;
  renewal_status?: RenewalStatus;
  renewal_date?: string;
  owner_user_id?: string;
  probability?: number;
  expected_value?: string;
  proposal_id?: string;
  notes?: string;
}

export interface CustomerRenewalUpdate {
  contract_name?: string;
  contract_value?: string;
  renewal_type?: RenewalType;
  renewal_date?: string;
  owner_user_id?: string;
  probability?: number;
  expected_value?: string;
  notes?: string;
}

export interface AssignRenewalOwner {
  owner_user_id: string;
}

export interface UpdateRenewalStatus {
  renewal_status: RenewalStatus;
}

export interface AttachProposal {
  proposal_id: string;
}

export interface CustomerRenewalFilters {
  workspace_id: string;
  customer_id?: string;
  renewal_type?: RenewalType;
  renewal_status?: RenewalStatus;
  owner_user_id?: string;
  renewal_date_from?: string;
  renewal_date_to?: string;
  search?: string;
  include_archived?: boolean;
  cursor?: string;
  limit?: number;
}

export const RENEWAL_TYPES: RenewalType[] = ["annual", "quarterly", "monthly", "custom"];
export const RENEWAL_STATUSES: RenewalStatus[] = [
  "planned",
  "in_progress",
  "negotiation",
  "won",
  "lost",
  "cancelled",
];
