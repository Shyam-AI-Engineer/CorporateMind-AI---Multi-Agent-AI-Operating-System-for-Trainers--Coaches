export interface WorkspaceBookingWebhook {
  workspace_id: string;
  webhook_url: string;
  has_secret: boolean;
  secret: string | null;
}
