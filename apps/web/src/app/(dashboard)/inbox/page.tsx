import { ConnectionsPanel } from "@/features/inbox/ui/connections-panel";

export default function InboxPage() {
  return (
    <div className="flex flex-col gap-1 p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Inbox Connections</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Manage connected Gmail accounts. Replies are synced automatically every 5 minutes.
        </p>
      </div>
      <ConnectionsPanel />
    </div>
  );
}
