"""BusinessOperationsService — Sprint 29.

Human-in-the-loop task management for the Business Operations Center.

Design constraints:
- No AI.  No automatic task creation.  No background jobs.
- Every task has an explicit creator (user_id from JWT via TenantContext).
- Redis cache per workspace, TTL 300 seconds.
- Cache is invalidated on every mutation (create / update / delete).
- No cross-module repo/model imports — business data flows through this module only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.operations.models import BusinessTask
from corpmind.modules.operations.repo import BusinessTaskRepo
from corpmind.modules.operations.schemas import (
    BusinessTaskIn,
    BusinessTaskOut,
    BusinessTaskUpdate,
    GroupedTasksOut,
    WorkloadOut,
)

log = structlog.get_logger(__name__)

_CACHE_TTL = 300   # 5 minutes — matches spec

_OPEN_STATUSES: frozenset[str] = frozenset({"backlog", "in_progress", "blocked"})


class BusinessOperationsService:
    """Manages the lifecycle of BusinessTasks for a workspace.

    All public methods are workspace-scoped; tenant isolation is enforced by
    the repository (via TenantContext) and by Postgres RLS.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BusinessTaskRepo(session)

    # ── Cache helpers ──────────────────────────────────────────────────────────

    def _cache_keys(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> tuple[str, str]:
        prefix = f"t:{org_id}:{workspace_id}:operations"
        return f"{prefix}:tasks", f"{prefix}:workload"

    async def _invalidate(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        tasks_key, workload_key = self._cache_keys(org_id, workspace_id)
        try:
            await get_redis().delete(tasks_key, workload_key)
        except Exception:
            pass

    # ── Grouping / compute (static, fully testable without DB) ────────────────

    @staticmethod
    def _group_tasks(tasks: list[BusinessTask]) -> GroupedTasksOut:
        backlog: list[BusinessTaskOut] = []
        in_progress: list[BusinessTaskOut] = []
        blocked: list[BusinessTaskOut] = []
        completed: list[BusinessTaskOut] = []

        for t in tasks:
            out = BusinessTaskOut.model_validate(t)
            if t.status == "backlog":
                backlog.append(out)
            elif t.status == "in_progress":
                in_progress.append(out)
            elif t.status == "blocked":
                blocked.append(out)
            elif t.status == "completed":
                completed.append(out)

        return GroupedTasksOut(
            backlog=backlog,
            in_progress=in_progress,
            blocked=blocked,
            completed=completed,
            total=len(backlog) + len(in_progress) + len(blocked) + len(completed),
        )

    @staticmethod
    def _compute_workload(
        tasks: list[BusinessTask],
        completed_today: int,
    ) -> WorkloadOut:
        today = date.today()
        open_tasks = [t for t in tasks if t.status in _OPEN_STATUSES]
        total_open = len(open_tasks)
        overdue = sum(1 for t in open_tasks if t.due_date and t.due_date < today)
        blocked = sum(1 for t in tasks if t.status == "blocked")

        by_priority: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        by_assignee: dict[str, int] = {}

        for t in open_tasks:
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            if t.assignee:
                by_assignee[t.assignee] = by_assignee.get(t.assignee, 0) + 1

        return WorkloadOut(
            total_open=total_open,
            overdue=overdue,
            completed_today=completed_today,
            blocked=blocked,
            by_priority=by_priority,
            by_assignee=by_assignee,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def list_tasks(self, workspace_id: uuid.UUID) -> GroupedTasksOut:
        ctx = get_tenant_context()
        tasks_key, _ = self._cache_keys(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(tasks_key)
            if cached:
                return GroupedTasksOut.model_validate_json(cached)
        except Exception:
            pass

        tasks = await self._repo.list_active(workspace_id)
        result = self._group_tasks(tasks)
        try:
            await get_redis().set(tasks_key, result.model_dump_json(), ex=_CACHE_TTL)
        except Exception:
            pass
        return result

    async def create_task(
        self,
        data: BusinessTaskIn,
        created_by: str,
    ) -> BusinessTaskOut:
        ctx = get_tenant_context()
        task = BusinessTask(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            source_type=data.source_type,
            source_id=data.source_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            status="backlog",
            assignee=data.assignee,
            due_date=data.due_date,
            created_by=created_by,
        )
        await self._repo.create(task)
        await self._invalidate(ctx.org_id, data.workspace_id)
        log.info(
            "operations.task.created",
            task_id=str(task.id),
            workspace_id=str(data.workspace_id),
            priority=task.priority,
            created_by=created_by,
        )
        return BusinessTaskOut.model_validate(task)

    async def update_task(
        self,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: BusinessTaskUpdate,
    ) -> BusinessTaskOut:
        ctx = get_tenant_context()
        task = await self._repo.find_by_id(task_id)
        if task is None or task.workspace_id != workspace_id or task.status == "deleted":
            raise NotFoundError(f"Task {task_id} not found")

        updates: dict[str, Any] = {}
        if data.status is not None:
            updates["status"] = data.status
            if data.status == "completed":
                updates["completed_at"] = datetime.now(UTC)
        if data.assignee is not None:
            updates["assignee"] = data.assignee
        if data.due_date is not None:
            updates["due_date"] = data.due_date

        if updates:
            updates["updated_at"] = datetime.now(UTC)
            await self._repo.update_fields(task_id, **updates)
            for key, value in updates.items():
                setattr(task, key, value)

        await self._invalidate(ctx.org_id, workspace_id)
        log.info(
            "operations.task.updated",
            task_id=str(task_id),
            updates=list(updates.keys()),
        )
        return BusinessTaskOut.model_validate(task)

    async def delete_task(
        self,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        ctx = get_tenant_context()
        task = await self._repo.find_by_id(task_id)
        if task is None or task.workspace_id != workspace_id or task.status == "deleted":
            raise NotFoundError(f"Task {task_id} not found")

        await self._repo.update_fields(
            task_id,
            status="deleted",
            updated_at=datetime.now(UTC),
        )
        await self._invalidate(ctx.org_id, workspace_id)
        log.info(
            "operations.task.deleted",
            task_id=str(task_id),
            workspace_id=str(workspace_id),
        )

    async def get_workload(self, workspace_id: uuid.UUID) -> WorkloadOut:
        ctx = get_tenant_context()
        _, workload_key = self._cache_keys(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(workload_key)
            if cached:
                return WorkloadOut.model_validate_json(cached)
        except Exception:
            pass

        tasks = await self._repo.list_active(workspace_id)
        completed_today = await self._repo.count_completed_today(workspace_id)
        result = self._compute_workload(tasks, completed_today)
        try:
            await get_redis().set(workload_key, result.model_dump_json(), ex=_CACHE_TTL)
        except Exception:
            pass
        return result

    async def assign_task(
        self,
        task_id: uuid.UUID,
        workspace_id: uuid.UUID,
        assigned_user_id: uuid.UUID | None,
    ) -> BusinessTaskOut:
        """Assign (or unassign) a task to a workspace user."""
        ctx = get_tenant_context()
        task = await self._repo.find_by_id(task_id)
        if task is None or task.workspace_id != workspace_id or task.status == "deleted":
            raise NotFoundError(f"Task {task_id} not found")

        updates: dict[str, Any] = {
            "assigned_user_id": assigned_user_id,
            "updated_at": datetime.now(UTC),
        }
        await self._repo.update_fields(task_id, **updates)
        for key, value in updates.items():
            setattr(task, key, value)

        await self._invalidate(ctx.org_id, workspace_id)
        log.info(
            "operations.task.assigned",
            task_id=str(task_id),
            assigned_user_id=str(assigned_user_id) if assigned_user_id else None,
        )
        return BusinessTaskOut.model_validate(task)
