import type { Metadata } from "next";
import { NotificationPage } from "@/features/notifications/ui/notification-page";

export const metadata: Metadata = {
  title: "Notifications — CorporateMind AI",
};

export default function NotificationsRoute() {
  return (
    <div className="max-w-3xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Notification Center</h1>
      <NotificationPage />
    </div>
  );
}
