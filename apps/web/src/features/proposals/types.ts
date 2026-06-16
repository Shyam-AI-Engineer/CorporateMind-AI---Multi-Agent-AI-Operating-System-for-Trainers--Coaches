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
