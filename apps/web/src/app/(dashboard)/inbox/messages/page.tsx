import { MessagesPanel } from "@/features/inbox/ui/messages-panel";

export default function InboxMessagesPage() {
  return (
    <div className="flex flex-col gap-1 p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Inbox Messages</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Synced replies, classified by intent. Filter by intent type to find the right leads.
        </p>
      </div>
      <MessagesPanel />
    </div>
  );
}
