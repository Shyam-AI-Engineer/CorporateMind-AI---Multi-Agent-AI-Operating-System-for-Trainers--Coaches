"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import {
  LayoutDashboard,
  TrendingUp,
  Megaphone,
  Send,
  Users,
  FileText,
  Share2,
  LogOut,
  Zap,
  UserCircle,
  Mail,
  BarChart2,
  Activity,
  Briefcase,
  UsersRound,
  ClipboardList,
  Bell,
  GitBranch,
  PlayCircle,
  ShieldCheck,
  BarChart,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ApprovalCountBadge } from "@/features/crm/ui/approval-count-badge";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  soon?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard",  label: "Dashboard",      icon: LayoutDashboard },
  { href: "/trainer",    label: "Trainer Profile", icon: UserCircle },
  { href: "/crm",        label: "CRM Pipeline",    icon: TrendingUp },
  { href: "/inbox",      label: "Inbox",           icon: Mail },
  { href: "/campaigns",  label: "Campaigns",       icon: Megaphone },
  { href: "/outreach",   label: "Outreach",        icon: Send },
  { href: "/hr",         label: "HR Contacts",     icon: Users },
  { href: "/proposals",  label: "Proposals",       icon: FileText },
  { href: "/analytics",  label: "Analytics",       icon: BarChart2 },
  { href: "/health",      label: "Health Center",  icon: Activity },
  { href: "/operations",  label: "Operations",     icon: Briefcase },
  { href: "/approvals",      label: "Approvals",      icon: ClipboardList },
  { href: "/notifications",  label: "Notifications",  icon: Bell },
  { href: "/workflows",       label: "Workflows",      icon: GitBranch },
  { href: "/workflow-runs",       label: "Workflow Runs",       icon: PlayCircle },
  { href: "/workflow-analytics", label: "Workflow Analytics", icon: BarChart2 },
  { href: "/workflow-sla",           label: "Workflow SLA",           icon: ShieldCheck },
  { href: "/workflow-effectiveness",  label: "Workflow Effectiveness",  icon: BarChart },
  { href: "/workflow-observability",  label: "Workflow Observability",  icon: Eye },
  { href: "/team",                    label: "Team",                    icon: UsersRound },
  { href: "/social",      label: "Social",         icon: Share2, soon: true },
];

interface SidebarProps {
  userEmail: string;
}

export function Sidebar({ userEmail }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r bg-background">
      {/* Logo */}
      <div className="flex items-center gap-2 border-b px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
          <Zap className="h-4 w-4 text-primary-foreground" />
        </div>
        <span className="text-sm font-semibold leading-tight">
          CorporateMind
          <br />
          <span className="font-normal text-muted-foreground">AI</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 p-2 pt-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon, soon }) => {
          if (soon) {
            return (
              <div
                key={href}
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm cursor-not-allowed select-none opacity-50"
                title={`${label} — coming in Phase 2`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">{label}</span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider">
                  Soon
                </span>
              </div>
            );
          }
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href as Route}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 font-medium text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {href === "/crm" && <ApprovalCountBadge />}
            </Link>
          );
        })}
      </nav>

      {/* User + Logout */}
      <div className="border-t p-3">
        <div className="mb-2 truncate px-1 text-xs text-muted-foreground">
          {userEmail}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-muted-foreground"
          onClick={() => signOut({ callbackUrl: "/login" })}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
