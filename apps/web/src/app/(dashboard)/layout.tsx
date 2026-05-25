import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

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
    <div className="flex min-h-screen">
      {/* TODO(Phase 1): Sidebar navigation */}
      <aside className="w-64 border-r bg-muted/10">
        <nav className="p-4">
          <p className="text-sm text-muted-foreground">Navigation — Phase 1</p>
        </nav>
      </aside>
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
