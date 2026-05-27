import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getServerSession(authOptions);
  if (!session) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen bg-muted/20">
      <Sidebar userEmail={session.user?.email ?? ""} />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
