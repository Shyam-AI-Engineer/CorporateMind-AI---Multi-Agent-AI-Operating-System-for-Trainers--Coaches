export interface Proposal {
  id: string;
  workspace_id: string;
  contact_id: string;
  title: string;
  status: string; // draft | sent
  content: Record<string, unknown>; // at minimum: { title, body }
  cloudinary_url: string | null;
  sent_at: string | null;
  created_at: string;
  // Sprint 12A — approval workflow
  approval_status: string; // pending_approval | approved | rejected
  approved_by: string | null;
  approved_at: string | null;
  rejected_reason: string | null;
  // Sprint 12B — delivery tracking
  outbound_message_id: string | null;
  delivery_status: string | null; // queued | sent | blocked | failed
  // Sprint 18A — revenue attribution + client response
  lead_id: string | null;
  expected_value_inr: number | null;
  actual_value_inr: number | null;
  client_status: string | null; // null | accepted | declined
  client_accepted_at: string | null;
  client_declined_at: string | null;
}

export interface ProposalListOut {
  items: Proposal[];
  total: number;
  limit: number;
  offset: number;
}

export interface GenerateProposalRequest {
  lead_id: string;
  workspace_id: string;
}

export interface RejectProposalRequest {
  proposalId: string;
  reason: string;
}

export interface AcceptProposalRequest {
  proposalId: string;
  actual_value_inr: number;
  expected_value_inr?: number;
}

export interface DeclineProposalRequest {
  proposalId: string;
  reason?: string;
}

export const PROPOSAL_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  draft: { label: "Draft", variant: "secondary" },
  sent:  { label: "Sent",  variant: "success"   },
};

export const APPROVAL_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  pending_approval: { label: "Pending Review", variant: "warning"     },
  approved:         { label: "Approved",        variant: "success"     },
  rejected:         { label: "Rejected",        variant: "destructive" },
};

export const DELIVERY_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  queued:  { label: "Queued",  variant: "warning"     },
  sent:    { label: "Sent",    variant: "success"     },
  blocked: { label: "Blocked", variant: "destructive" },
  failed:  { label: "Failed",  variant: "destructive" },
};

export const CLIENT_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  accepted: { label: "Accepted", variant: "success"     },
  declined: { label: "Declined", variant: "destructive" },
};
