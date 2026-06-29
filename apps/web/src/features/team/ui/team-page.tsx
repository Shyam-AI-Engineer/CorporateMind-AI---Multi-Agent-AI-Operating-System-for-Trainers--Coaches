"use client";

import { useState } from "react";
import { AlertCircle, UserPlus, Trash2, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useTeamMembers,
  useActivityFeed,
  useInviteMember,
  useRemoveMember,
  useChangeMemberRole,
} from "@/features/team/api/use-team";
import type { WorkspaceMemberOut, WorkspaceRole } from "@/features/team/types";

// ── Role badge ────────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: WorkspaceRole }) {
  const colors: Record<WorkspaceRole, string> = {
    owner: "bg-purple-100 text-purple-700 border-purple-200",
    admin: "bg-blue-100 text-blue-700 border-blue-200",
    member: "bg-green-100 text-green-700 border-green-200",
    viewer: "bg-slate-100 text-slate-600 border-slate-200",
  };
  return (
    <span
      data-testid={`role-badge-${role}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[role]}`}
    >
      {role}
    </span>
  );
}

// ── Invite dialog ─────────────────────────────────────────────────────────────

function InviteDialog({
  workspaceId,
  onClose,
}: {
  workspaceId: string;
  onClose: () => void;
}) {
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<WorkspaceRole>("member");
  const [error, setError] = useState<string | null>(null);
  const invite = useInviteMember(workspaceId);

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setUserId("");
      setRole("member");
      setError(null);
      onClose();
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId.trim()) return;
    setError(null);
    invite.mutate(
      { workspace_id: workspaceId, user_id: userId.trim(), role },
      {
        onSuccess: onClose,
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Failed to invite member";
          setError(msg);
        },
      },
    );
  };

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent data-testid="invite-dialog">
        <DialogHeader>
          <DialogTitle>Invite Team Member</DialogTitle>
        </DialogHeader>
        <form data-testid="invite-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="invite-user-id">User ID</Label>
            <Input
              id="invite-user-id"
              data-testid="invite-user-id-input"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="UUID of the user to invite"
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="invite-role">Role</Label>
            <select
              id="invite-role"
              data-testid="invite-role-select"
              value={role}
              onChange={(e) => setRole(e.target.value as WorkspaceRole)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="viewer">Viewer</option>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
              <option value="owner">Owner</option>
            </select>
          </div>
          {error && (
            <p data-testid="invite-error" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              data-testid="invite-submit"
              disabled={invite.isPending || !userId.trim()}
            >
              {invite.isPending ? "Inviting…" : "Send Invitation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Remove confirmation dialog ────────────────────────────────────────────────

function RemoveDialog({
  member,
  workspaceId,
  onClose,
}: {
  member: WorkspaceMemberOut;
  workspaceId: string;
  onClose: () => void;
}) {
  const remove = useRemoveMember(workspaceId);

  const handleConfirm = () => {
    remove.mutate(member.id, { onSuccess: onClose });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="remove-dialog">
        <DialogHeader>
          <DialogTitle>Remove Member</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Remove user{" "}
          <span data-testid="remove-dialog-user-id" className="font-medium">
            {member.user_id}
          </span>{" "}
          from this workspace? This action can be reversed by re-inviting them.
        </p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            data-testid="remove-confirm-btn"
            variant="destructive"
            onClick={handleConfirm}
            disabled={remove.isPending}
          >
            {remove.isPending ? "Removing…" : "Remove Member"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Change role inline ────────────────────────────────────────────────────────

function RoleSelector({
  member,
  workspaceId,
}: {
  member: WorkspaceMemberOut;
  workspaceId: string;
}) {
  const changeRole = useChangeMemberRole(workspaceId);

  return (
    <select
      data-testid={`role-select-${member.id}`}
      value={member.role}
      onChange={(e) =>
        changeRole.mutate({
          memberId: member.id,
          data: { role: e.target.value as WorkspaceRole },
        })
      }
      disabled={changeRole.isPending}
      className="rounded border border-input bg-transparent px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
    >
      <option value="viewer">Viewer</option>
      <option value="member">Member</option>
      <option value="admin">Admin</option>
      <option value="owner">Owner</option>
    </select>
  );
}

// ── Members table ─────────────────────────────────────────────────────────────

function MembersTab({ workspaceId }: { workspaceId: string }) {
  const { data, isLoading, isError } = useTeamMembers(workspaceId);
  const [showInvite, setShowInvite] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<WorkspaceMemberOut | null>(null);

  if (isLoading) {
    return (
      <div data-testid="members-skeleton" className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="members-error" className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load team members.
      </div>
    );
  }

  const members = data?.items ?? [];

  return (
    <div data-testid="members-tab" className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{members.length} member(s)</p>
        <Button
          size="sm"
          data-testid="invite-btn"
          onClick={() => setShowInvite(true)}
        >
          <UserPlus className="mr-1 h-4 w-4" />
          Invite
        </Button>
      </div>

      {members.length === 0 ? (
        <p data-testid="members-empty" className="text-sm text-muted-foreground">
          No members yet. Invite someone to get started.
        </p>
      ) : (
        <div data-testid="members-table-container" className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">User ID</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Invited</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {members.map((m) => (
                <tr
                  key={m.id}
                  data-testid={`member-row-${m.id}`}
                  className="hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs">{m.user_id}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <RoleBadge role={m.role} />
                      <RoleSelector member={m} workspaceId={workspaceId} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {m.accepted_at ? (
                      <span data-testid={`member-status-active-${m.id}`} className="text-green-600 text-xs font-medium">
                        Active
                      </span>
                    ) : (
                      <span data-testid={`member-status-pending-${m.id}`} className="text-amber-600 text-xs font-medium">
                        Pending
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {new Date(m.invited_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      size="sm"
                      variant="ghost"
                      data-testid={`remove-btn-${m.id}`}
                      onClick={() => setMemberToRemove(m)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showInvite && (
        <InviteDialog workspaceId={workspaceId} onClose={() => setShowInvite(false)} />
      )}
      {memberToRemove && (
        <RemoveDialog
          member={memberToRemove}
          workspaceId={workspaceId}
          onClose={() => setMemberToRemove(null)}
        />
      )}
    </div>
  );
}

// ── Activity feed ─────────────────────────────────────────────────────────────

function activityLabel(action: string): string {
  const labels: Record<string, string> = {
    "task.created": "created a task",
    "task.assigned": "assigned a task",
    "task.completed": "completed a task",
    "task.commented": "commented on a task",
    "member.invited": "invited a member",
    "member.accepted": "accepted invitation",
    "member.removed": "removed a member",
    "member.role_changed": "changed a member's role",
    "recommendation.accepted": "accepted a recommendation",
    "proposal.accepted": "accepted a proposal",
    "campaign.launched": "launched a campaign",
  };
  return labels[action] ?? action;
}

function ActivityTab({ workspaceId }: { workspaceId: string }) {
  const [cursor, setCursor] = useState<string | undefined>();
  const { data, isLoading, isError } = useActivityFeed(workspaceId, cursor);

  if (isLoading) {
    return (
      <div data-testid="activity-skeleton" className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid="activity-error" className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load activity feed.
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div data-testid="activity-tab" className="space-y-4">
      {items.length === 0 ? (
        <p data-testid="activity-empty" className="text-sm text-muted-foreground">
          No activity yet.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((entry, i) => (
            <div
              key={entry.id}
              data-testid={`activity-item-${i}`}
              className="flex items-start gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <div className="flex-1">
                <span className="font-mono text-xs text-muted-foreground">
                  {entry.actor_user_id.slice(0, 8)}
                </span>
                <span className="mx-1 text-muted-foreground">·</span>
                <span>{activityLabel(entry.action)}</span>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                {new Date(entry.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Cursor pagination controls */}
      <div className="flex items-center justify-between">
        {cursor && (
          <Button
            size="sm"
            variant="outline"
            data-testid="activity-prev-btn"
            onClick={() => setCursor(undefined)}
          >
            <RefreshCw className="mr-1 h-3 w-3" />
            Back to latest
          </Button>
        )}
        {data?.has_more && (
          <Button
            size="sm"
            variant="outline"
            data-testid="activity-next-btn"
            onClick={() => setCursor(data.next_cursor ?? undefined)}
            className="ml-auto"
          >
            Load older
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Main Team Page ────────────────────────────────────────────────────────────

export function TeamPage() {
  const { workspaceId } = useWorkspace();

  if (!workspaceId) {
    return (
      <div data-testid="team-no-workspace" className="text-sm text-muted-foreground">
        Select a workspace to view the team.
      </div>
    );
  }

  return (
    <div data-testid="team-page" className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Team Collaboration</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="members">
            <TabsList data-testid="team-tabs">
              <TabsTrigger value="members" data-testid="tab-members">
                Members
              </TabsTrigger>
              <TabsTrigger value="activity" data-testid="tab-activity">
                Activity
              </TabsTrigger>
            </TabsList>
            <TabsContent value="members" className="mt-4">
              <MembersTab workspaceId={workspaceId} />
            </TabsContent>
            <TabsContent value="activity" className="mt-4">
              <ActivityTab workspaceId={workspaceId} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
