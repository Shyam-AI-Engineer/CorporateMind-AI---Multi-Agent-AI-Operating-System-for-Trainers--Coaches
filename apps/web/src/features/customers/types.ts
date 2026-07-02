export interface Customer {
  id: string;
  tenant_id: string;
  workspace_id: string;
  company_name: string;
  display_name: string;
  industry: string | null;
  website: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  postal_code: string | null;
  company_size: string | null;
  annual_revenue_inr: string | null;
  status: CustomerStatus;
  health_status: CustomerHealthStatus;
  relationship_owner_id: string | null;
  primary_contact_name: string | null;
  primary_contact_email: string | null;
  primary_contact_phone: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type CustomerStatus = "active" | "inactive" | "prospect" | "former";
export type CustomerHealthStatus = "healthy" | "attention" | "at_risk" | "inactive";

export interface CustomerListOut {
  items: Customer[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}

export interface CustomerCreate {
  workspace_id: string;
  company_name: string;
  display_name: string;
  industry?: string;
  website?: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  country?: string;
  postal_code?: string;
  company_size?: string;
  annual_revenue_inr?: string;
  status?: CustomerStatus;
  health_status?: CustomerHealthStatus;
  relationship_owner_id?: string;
  primary_contact_name?: string;
  primary_contact_email?: string;
  primary_contact_phone?: string;
  notes?: string;
}

export interface CustomerUpdate {
  company_name?: string;
  display_name?: string;
  industry?: string;
  website?: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  country?: string;
  postal_code?: string;
  company_size?: string;
  annual_revenue_inr?: string;
  notes?: string;
}

export interface CustomerHealthUpdate {
  health_status: CustomerHealthStatus;
}

export interface CustomerOwnerAssign {
  relationship_owner_id: string;
}

export interface CustomerFilters {
  workspace_id: string;
  status?: CustomerStatus;
  industry?: string;
  health_status?: CustomerHealthStatus;
  owner_id?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}

export const CUSTOMER_STATUSES: CustomerStatus[] = ["active", "inactive", "prospect", "former"];
export const CUSTOMER_HEALTH_STATUSES: CustomerHealthStatus[] = [
  "healthy",
  "attention",
  "at_risk",
  "inactive",
];
