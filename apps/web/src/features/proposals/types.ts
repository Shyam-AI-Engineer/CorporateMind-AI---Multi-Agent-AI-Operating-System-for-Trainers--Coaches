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

export const PROPOSAL_STATUS_CONFIG: Record<
  string,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" }
> = {
  draft: { label: "Draft", variant: "secondary" },
  sent:  { label: "Sent",  variant: "success"   },
};
