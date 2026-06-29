"use client";

import { useState } from "react";
import { AlertCircle, Calendar, CheckCircle2, Clock, Plus, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useOperationsTasks,
  useOperationsWorkload,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
} from "@/features/operations/api/use-operations";
import {
  useTeamMembers,
  useTaskComments,
  useCreateComment,
  useDeleteComment,
  useAssignTask,
} from "@/features/team/api/use-team";
import type {
  BusinessTaskOut,
  TaskPriority,
  TaskStatus,
  WorkloadOut,
} from "@/features/operations/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function priorityColor(priority: TaskPriority): string {
  if (priority === "high") return "bg-red-100 text-red-700 border-red-200";
  if (priority === "medium") return "bg-amber-100 text-amber-700 border-amber-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function isOverdue(task: BusinessTaskOut): boolean {
  if (!task.due_date) return false;
  return new Date(task.due_date) < new Date(new Date().toDateString());
}

// ── KPI Row ───────────────────────────────────────────────────────────────────

function KPIRow({ workload }: { workload: WorkloadOut }) {
  return (
    <div data-testid="kpi-row" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card data-testid="kpi-open">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs font-medium text-muted-foreground">Open</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold tabular-nums">{workload.total_open}</p>
        </CardContent>
      </Card>
      <Card data-testid="kpi-overdue">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs font-medium text-muted-foreground">Overdue</CardTitle>
        </CardHeader>
        <CardContent>
          <p className={`text-2xl font-bold tabular-nums ${workload.overdue > 0 ? "text-red-600" : ""}`}>
            {workload.overdue}
          </p>
        </CardContent>
      </Card>
      <Card data-testid="kpi-completed-today">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs font-medium text-muted-foreground">Completed Today</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold tabular-nums text-green-600">{workload.completed_today}</p>
        </CardContent>
      </Card>
      <Card data-testid="kpi-blocked">
        <CardHeader className="pb-1">
          <CardTitle className="text-xs font-medium text-muted-foreground">Blocked</CardTitle>
        </CardHeader>
        <CardContent>
          <p className={`text-2xl font-bold tabular-nums ${workload.blocked > 0 ? "text-orange-600" : ""}`}>
            {workload.blocked}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Task Card ─────────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onSelect,
}: {
  task: BusinessTaskOut;
  onSelect: (t: BusinessTaskOut) => void;
}) {
  const overdue = isOverdue(task);
  return (
    <div
      data-testid={`task-card-${task.id}`}
      className="cursor-pointer rounded-md border bg-background p-3 text-sm shadow-sm hover:border-primary/40 transition-colors"
      onClick={() => onSelect(task)}
    >
      <p className="font-medium line-clamp-2">{task.title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          data-testid={`task-priority-${task.id}`}
          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${priorityColor(task.priority)}`}
        >
          {task.priority}
        </span>
        {task.due_date && (
          <span
            data-testid={`task-due-${task.id}`}
            className={`flex items-center gap-1 text-[11px] ${overdue ? "text-red-600 font-semibold" : "text-muted-foreground"}`}
          >
            <Clock className="h-3 w-3" />
            {task.due_date}
            {overdue && " (overdue)"}
          </span>
        )}
        {task.assignee && (
          <span
            data-testid={`task-assignee-${task.id}`}
            className="flex items-center gap-1 text-[11px] text-muted-foreground"
          >
            <Users className="h-3 w-3" />
            {task.assignee}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Kanban Column ─────────────────────────────────────────────────────────────

function KanbanColumn({
  testId,
  label,
  tasks,
  onSelect,
}: {
  testId: string;
  label: string;
  tasks: BusinessTaskOut[];
  onSelect: (t: BusinessTaskOut) => void;
}) {
  return (
    <div data-testid={testId} className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </h4>
        <Badge variant="secondary" className="text-[10px]">{tasks.length}</Badge>
      </div>
      {tasks.length === 0 ? (
        <p
          data-testid={`${testId}-empty`}
          className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground"
        >
          No tasks
        </p>
      ) : (
        tasks.map((t) => <TaskCard key={t.id} task={t} onSelect={onSelect} />)
      )}
    </div>
  );
}

// ── Kanban Board ──────────────────────────────────────────────────────────────

function KanbanBoard({
  backlog,
  in_progress,
  blocked,
  completed,
  onSelect,
}: {
  backlog: BusinessTaskOut[];
  in_progress: BusinessTaskOut[];
  blocked: BusinessTaskOut[];
  completed: BusinessTaskOut[];
  onSelect: (t: BusinessTaskOut) => void;
}) {
  return (
    <section data-testid="kanban-board">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Task Board
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KanbanColumn testId="kanban-backlog" label="Backlog" tasks={backlog} onSelect={onSelect} />
        <KanbanColumn testId="kanban-in-progress" label="In Progress" tasks={in_progress} onSelect={onSelect} />
        <KanbanColumn testId="kanban-blocked" label="Blocked" tasks={blocked} onSelect={onSelect} />
        <KanbanColumn testId="kanban-completed" label="Completed" tasks={completed} onSelect={onSelect} />
      </div>
    </section>
  );
}

// ── Calendar Section ──────────────────────────────────────────────────────────

function DueCalendar({ tasks }: { tasks: BusinessTaskOut[] }) {
  const upcoming = tasks
    .filter((t) => t.due_date && t.status !== "completed")
    .sort((a, b) => (a.due_date! > b.due_date! ? 1 : -1))
    .slice(0, 10);

  return (
    <section data-testid="due-calendar">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Upcoming Due Dates
      </h3>
      {upcoming.length === 0 ? (
        <p data-testid="calendar-empty" className="text-sm text-muted-foreground">
          No upcoming due dates.
        </p>
      ) : (
        <div className="space-y-2">
          {upcoming.map((t, i) => (
            <div
              key={t.id}
              data-testid={`calendar-item-${i}`}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
            >
              <span className="font-medium line-clamp-1">{t.title}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{t.due_date}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Workload Section ──────────────────────────────────────────────────────────

function WorkloadSection({ workload }: { workload: WorkloadOut }) {
  const assignees = Object.entries(workload.by_assignee);
  const priorities = Object.entries(workload.by_priority).filter(([, count]) => count > 0);

  return (
    <section data-testid="workload-section">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Workload
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">By Priority</CardTitle>
          </CardHeader>
          <CardContent>
            {priorities.length === 0 ? (
              <p data-testid="workload-priority-empty" className="text-xs text-muted-foreground">No open tasks</p>
            ) : (
              <div data-testid="workload-priority" className="space-y-1">
                {priorities.map(([priority, count]) => (
                  <div key={priority} className="flex items-center justify-between text-sm">
                    <span className="capitalize">{priority}</span>
                    <span className="font-semibold tabular-nums">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">By Assignee</CardTitle>
          </CardHeader>
          <CardContent>
            {assignees.length === 0 ? (
              <p data-testid="workload-assignee-empty" className="text-xs text-muted-foreground">No assigned tasks</p>
            ) : (
              <div data-testid="workload-assignee" className="space-y-1">
                {assignees.map(([assignee, count]) => (
                  <div key={assignee} className="flex items-center justify-between text-sm">
                    <span>{assignee}</span>
                    <span className="font-semibold tabular-nums">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

// ── Task Detail Drawer ────────────────────────────────────────────────────────

function TaskDetailDialog({
  task,
  workspaceId,
  onClose,
}: {
  task: BusinessTaskOut | null;
  workspaceId: string;
  onClose: () => void;
}) {
  const update = useUpdateTask(workspaceId);
  const del = useDeleteTask(workspaceId);
  const assign = useAssignTask(workspaceId);
  const members = useTeamMembers(workspaceId);
  const comments = useTaskComments(workspaceId, task?.id ?? null);
  const createComment = useCreateComment(workspaceId, task?.id ?? "");
  const deleteComment = useDeleteComment(workspaceId, task?.id ?? "");
  const [commentBody, setCommentBody] = useState("");

  if (!task) return null;

  const handleStatusChange = (status: string) => {
    update.mutate({ taskId: task.id, data: { status: status as TaskStatus } });
    onClose();
  };

  const handleDelete = () => {
    del.mutate(task.id);
    onClose();
  };

  const handleAssign = (userId: string) => {
    assign.mutate({
      taskId: task.id,
      data: {
        workspace_id: workspaceId,
        assigned_user_id: userId === "" ? null : userId,
      },
    });
  };

  const handleAddComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentBody.trim()) return;
    createComment.mutate(
      { body: commentBody.trim() },
      { onSuccess: () => setCommentBody("") },
    );
  };

  return (
    <Dialog open={!!task} onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="task-detail-dialog" className="max-w-lg">
        <DialogHeader>
          <DialogTitle data-testid="task-detail-title">{task.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {task.description && (
            <p data-testid="task-detail-description" className="text-sm text-muted-foreground">
              {task.description}
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">Priority</span>
              <p data-testid="task-detail-priority" className="font-medium capitalize">{task.priority}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Status</span>
              <p data-testid="task-detail-status" className="font-medium capitalize">{task.status.replace("_", " ")}</p>
            </div>
            {task.assignee && (
              <div>
                <span className="text-muted-foreground">Assignee</span>
                <p data-testid="task-detail-assignee" className="font-medium">{task.assignee}</p>
              </div>
            )}
            {task.due_date && (
              <div>
                <span className="text-muted-foreground">Due Date</span>
                <p data-testid="task-detail-due-date" className="font-medium">{task.due_date}</p>
              </div>
            )}
          </div>

          {/* Assignment dropdown */}
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Assign to member</Label>
            <select
              data-testid="task-assign-select"
              value={task.assigned_user_id ?? ""}
              onChange={(e) => handleAssign(e.target.value)}
              disabled={assign.isPending}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">Unassigned</option>
              {(members.data?.items ?? []).map((m) => (
                <option key={m.id} value={m.user_id}>
                  {m.user_id}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2">
            {task.status !== "completed" && (
              <Button
                data-testid="task-complete-btn"
                size="sm"
                onClick={() => handleStatusChange("completed")}
                disabled={update.isPending}
              >
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Mark Complete
              </Button>
            )}
            {task.status === "backlog" && (
              <Button
                data-testid="task-start-btn"
                size="sm"
                variant="outline"
                onClick={() => handleStatusChange("in_progress")}
                disabled={update.isPending}
              >
                Start
              </Button>
            )}
            <Button
              data-testid="task-delete-btn"
              size="sm"
              variant="destructive"
              onClick={handleDelete}
              disabled={del.isPending}
            >
              Delete
            </Button>
          </div>

          {/* Comments panel */}
          <div data-testid="task-comments-panel" className="space-y-2 border-t pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Comments
            </p>
            {comments.isLoading && <Skeleton className="h-16 w-full" />}
            {!comments.isLoading && (comments.data ?? []).length === 0 && (
              <p data-testid="comments-empty" className="text-xs text-muted-foreground">
                No comments yet.
              </p>
            )}
            <div className="space-y-2">
              {(comments.data ?? []).map((c) => (
                <div
                  key={c.id}
                  data-testid={`comment-${c.id}`}
                  className="flex items-start justify-between gap-2 rounded-md bg-muted/40 px-3 py-2 text-sm"
                >
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">
                      {c.author_user_id.slice(0, 8)}
                    </span>
                    <p>{c.body}</p>
                  </div>
                  <button
                    data-testid={`delete-comment-${c.id}`}
                    onClick={() => deleteComment.mutate(c.id)}
                    className="shrink-0 text-xs text-muted-foreground hover:text-destructive"
                    aria-label="Delete comment"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <form
              data-testid="add-comment-form"
              onSubmit={handleAddComment}
              className="flex gap-2"
            >
              <input
                data-testid="comment-body-input"
                value={commentBody}
                onChange={(e) => setCommentBody(e.target.value)}
                placeholder="Add a comment…"
                className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <Button
                type="submit"
                size="sm"
                data-testid="add-comment-submit"
                disabled={createComment.isPending || !commentBody.trim()}
              >
                Post
              </Button>
            </form>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Create Task Form ──────────────────────────────────────────────────────────

function CreateTaskDialog({
  workspaceId,
  onClose,
}: {
  workspaceId: string;
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");
  const create = useCreateTask(workspaceId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    create.mutate(
      {
        workspace_id: workspaceId,
        title: title.trim(),
        priority,
        assignee: assignee || null,
        due_date: dueDate || null,
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Task</DialogTitle>
        </DialogHeader>
        <form data-testid="create-task-form" onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="task-title">Title</Label>
            <Input
              id="task-title"
              data-testid="task-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Task title"
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="task-priority">Priority</Label>
            <select
              id="task-priority"
              data-testid="task-priority-select"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TaskPriority)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="task-assignee">Assignee</Label>
            <Input
              id="task-assignee"
              data-testid="task-assignee-input"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="task-due-date">Due Date</Label>
            <Input
              id="task-due-date"
              data-testid="task-due-date-input"
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              data-testid="create-task-submit"
              disabled={create.isPending || !title.trim()}
            >
              Create Task
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function OperationsCenter() {
  const { workspaceId } = useWorkspace();
  const tasks = useOperationsTasks(workspaceId);
  const workload = useOperationsWorkload(workspaceId);

  const [selectedTask, setSelectedTask] = useState<BusinessTaskOut | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  if (tasks.isLoading || workload.isLoading) {
    return (
      <div data-testid="operations-skeleton" className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (tasks.isError || workload.isError) {
    return (
      <div
        data-testid="operations-error"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load operations data. Try refreshing.
      </div>
    );
  }

  const t = tasks.data!;
  const w = workload.data!;
  const allTasks = [...t.backlog, ...t.in_progress, ...t.blocked, ...t.completed];

  return (
    <div data-testid="operations-center" className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div />
        <Button
          data-testid="new-task-btn"
          size="sm"
          onClick={() => setShowCreate(true)}
        >
          <Plus className="mr-1 h-4 w-4" />
          New Task
        </Button>
      </div>

      {/* KPI row */}
      <KPIRow workload={w} />

      {/* Kanban */}
      <KanbanBoard
        backlog={t.backlog}
        in_progress={t.in_progress}
        blocked={t.blocked}
        completed={t.completed}
        onSelect={setSelectedTask}
      />

      {/* Calendar */}
      <DueCalendar tasks={allTasks} />

      {/* Workload */}
      <WorkloadSection workload={w} />

      {/* Dialogs */}
      {showCreate && workspaceId && (
        <CreateTaskDialog
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
        />
      )}
      {selectedTask && workspaceId && (
        <TaskDetailDialog
          task={selectedTask}
          workspaceId={workspaceId}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </div>
  );
}
