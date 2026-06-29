"""Workflow Templates & Playbooks + Execution Engine service — Sprint 33/34.

Design constraints:
- No AI. No LLM. No Celery. No background jobs.
- Templates only define work; they NEVER auto-execute.
- Permissions: owner/admin can create/update/delete; member/viewer read-only.
- Redis: list TTL 300s, detail TTL 300s; invalidate after every mutation.
- Cursor pagination (newest-first) on list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.workflows.models import (
    WorkflowRun,
    WorkflowRunStep,
    WorkflowStep,
    WorkflowTemplate,
)
from corpmind.modules.workflows.repo import (
    WorkflowRunRepo,
    WorkflowRunStepRepo,
    WorkflowStepRepo,
    WorkflowTemplateRepo,
)
from corpmind.modules.workflows.schemas import (
    BlockStepIn,
    CompleteStepIn,
    ReorderStepsIn,
    SkipStepIn,
    WorkflowRunIn,
    WorkflowRunListPage,
    WorkflowRunOut,
    WorkflowRunStepOut,
    WorkflowStepIn,
    WorkflowStepOut,
    WorkflowStepUpdate,
    WorkflowTemplateIn,
    WorkflowTemplateListPage,
    WorkflowTemplateOut,
    WorkflowTemplateUpdate,
)

log = structlog.get_logger(__name__)

_TTL = 300  # 5 minutes

_WRITE_ROLES = frozenset({"owner", "admin"})


class PermissionDeniedError(Exception):
    """Raised when role doesn't permit the requested mutation."""


class StepOrderConflictError(Exception):
    """Raised when reorder list doesn't match the template's steps."""


# ── Cache key helpers ─────────────────────────────────────────────────────────

def _list_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_templates:list"


def _detail_key(org_id: uuid.UUID, template_id: uuid.UUID) -> str:
    return f"t:{org_id}:workflow_templates:detail:{template_id}"


# ── WorkflowService ───────────────────────────────────────────────────────────

class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._template_repo = WorkflowTemplateRepo(session)
        self._step_repo = WorkflowStepRepo(session)

    def _assert_write(self, ctx: object) -> None:
        role = getattr(ctx, "role", "member")
        if role not in _WRITE_ROLES:
            raise PermissionDeniedError(
                f"Role '{role}' cannot create or modify workflow templates"
            )

    async def _invalidate(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        template_id: uuid.UUID | None = None,
    ) -> None:
        keys: list[str] = [_list_key(org_id, workspace_id)]
        if template_id is not None:
            keys.append(_detail_key(org_id, template_id))
        try:
            await get_redis().delete(*keys)
        except Exception:
            pass

    # ── Template CRUD ─────────────────────────────────────────────────────────

    async def create_template(self, data: WorkflowTemplateIn) -> WorkflowTemplateOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        now = datetime.now(UTC)
        template = WorkflowTemplate(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            name=data.name,
            description=data.description,
            category=data.category,
            is_active=data.is_active,
            created_by=ctx.user_id,
            created_at=now,
        )
        await self._template_repo.create(template)
        await self._invalidate(ctx.org_id, data.workspace_id)
        log.info(
            "workflow_template.created",
            template_id=str(template.id),
            name=data.name,
            category=data.category,
        )
        return WorkflowTemplateOut.model_validate(template)

    async def get_template(self, template_id: uuid.UUID) -> WorkflowTemplateOut:
        ctx = get_tenant_context()
        key = _detail_key(ctx.org_id, template_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return WorkflowTemplateOut.model_validate_json(cached)
        except Exception:
            pass

        template = await self._template_repo.find_by_id(template_id)
        if template is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        result = WorkflowTemplateOut.model_validate(template)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_TTL)
        except Exception:
            pass
        return result

    async def update_template(
        self, template_id: uuid.UUID, data: WorkflowTemplateUpdate
    ) -> WorkflowTemplateOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        template = await self._template_repo.find_by_id(template_id)
        if template is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        updates: dict[str, object] = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.description is not None:
            updates["description"] = data.description
        if data.category is not None:
            updates["category"] = data.category
        if data.is_active is not None:
            updates["is_active"] = data.is_active

        if updates:
            await self._template_repo.update_fields(template_id, **updates)
            for k, v in updates.items():
                setattr(template, k, v)

        await self._invalidate(ctx.org_id, template.workspace_id, template_id)
        log.info(
            "workflow_template.updated",
            template_id=str(template_id),
            changed=list(updates.keys()),
        )
        return WorkflowTemplateOut.model_validate(template)

    async def delete_template(self, template_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        template = await self._template_repo.find_by_id(template_id)
        if template is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        workspace_id = template.workspace_id
        await self._template_repo.delete_by_id(template_id)
        await self._invalidate(ctx.org_id, workspace_id, template_id)
        log.info("workflow_template.deleted", template_id=str(template_id))

    async def duplicate_template(
        self, template_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> WorkflowTemplateOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        source = await self._template_repo.find_by_id(template_id)
        if source is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        now = datetime.now(UTC)
        new_template = WorkflowTemplate(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=workspace_id,
            name=f"Copy of {source.name}",
            description=source.description,
            category=source.category,
            is_active=True,
            created_by=ctx.user_id,
            created_at=now,
        )
        await self._template_repo.create(new_template)

        # Copy all steps preserving step_order
        source_steps = await self._step_repo.find_by_template(template_id)
        for src_step in source_steps:
            new_step = WorkflowStep(
                id=uuid.uuid4(),
                tenant_id=ctx.org_id,
                workspace_id=workspace_id,
                workflow_template_id=new_template.id,
                step_order=src_step.step_order,
                title=src_step.title,
                description=src_step.description,
                owner_role=src_step.owner_role,
                estimated_hours=src_step.estimated_hours,
                required=src_step.required,
                created_at=now,
            )
            await self._step_repo.create(new_step)

        await self._invalidate(ctx.org_id, workspace_id)
        log.info(
            "workflow_template.duplicated",
            source_id=str(template_id),
            new_id=str(new_template.id),
        )
        # Re-fetch to include all steps via selectin
        return await self.get_template(new_template.id)

    async def list_templates(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> WorkflowTemplateListPage:
        ctx = get_tenant_context()
        is_first_page = cursor is None and category is None and is_active is None

        if is_first_page:
            key = _list_key(ctx.org_id, workspace_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return WorkflowTemplateListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._template_repo.list_page(
            workspace_id, limit, cursor, category, is_active
        )
        result = WorkflowTemplateListPage(
            items=[WorkflowTemplateOut.model_validate(t) for t in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )

        if is_first_page:
            try:
                await get_redis().set(
                    _list_key(ctx.org_id, workspace_id),
                    result.model_dump_json(),
                    ex=_TTL,
                )
            except Exception:
                pass

        return result

    # ── Step CRUD ─────────────────────────────────────────────────────────────

    async def add_step(
        self, template_id: uuid.UUID, data: WorkflowStepIn
    ) -> WorkflowStepOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        template = await self._template_repo.find_by_id(template_id)
        if template is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        max_order = await self._step_repo.max_step_order(template_id)
        now = datetime.now(UTC)
        step = WorkflowStep(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=template.workspace_id,
            workflow_template_id=template_id,
            step_order=max_order + 1,
            title=data.title,
            description=data.description,
            owner_role=data.owner_role,
            estimated_hours=data.estimated_hours,
            required=data.required,
            created_at=now,
        )
        await self._step_repo.create(step)
        await self._invalidate(ctx.org_id, template.workspace_id, template_id)
        log.info(
            "workflow_step.added",
            step_id=str(step.id),
            template_id=str(template_id),
            step_order=step.step_order,
        )
        return WorkflowStepOut.model_validate(step)

    async def update_step(
        self, step_id: uuid.UUID, data: WorkflowStepUpdate
    ) -> WorkflowStepOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        step = await self._step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowStep {step_id} not found")

        updates: dict[str, object] = {}
        if data.title is not None:
            updates["title"] = data.title
        if data.description is not None:
            updates["description"] = data.description
        if data.owner_role is not None:
            updates["owner_role"] = data.owner_role
        if data.estimated_hours is not None:
            updates["estimated_hours"] = data.estimated_hours
        if data.required is not None:
            updates["required"] = data.required

        if updates:
            await self._step_repo.update_fields(step_id, **updates)
            for k, v in updates.items():
                setattr(step, k, v)

        await self._invalidate(ctx.org_id, step.workspace_id, step.workflow_template_id)
        log.info("workflow_step.updated", step_id=str(step_id), changed=list(updates.keys()))
        return WorkflowStepOut.model_validate(step)

    async def delete_step(self, step_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        step = await self._step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowStep {step_id} not found")

        workspace_id = step.workspace_id
        template_id = step.workflow_template_id
        await self._step_repo.delete_by_id(step_id)
        await self._invalidate(ctx.org_id, workspace_id, template_id)
        log.info("workflow_step.deleted", step_id=str(step_id))

    async def reorder_steps(
        self, template_id: uuid.UUID, data: ReorderStepsIn
    ) -> WorkflowTemplateOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)
        template = await self._template_repo.find_by_id(template_id)
        if template is None:
            raise NotFoundError(f"WorkflowTemplate {template_id} not found")

        existing_steps = await self._step_repo.find_by_template(template_id)
        existing_ids = {s.id for s in existing_steps}
        requested_ids = set(data.step_ids)

        if existing_ids != requested_ids:
            raise StepOrderConflictError(
                "step_ids must contain exactly the template's current step IDs"
            )

        # Assign new order: position in the list → step_order (1-based)
        updates = [(step_id, i + 1) for i, step_id in enumerate(data.step_ids)]
        await self._step_repo.bulk_update_order(updates)
        await self._invalidate(ctx.org_id, template.workspace_id, template_id)
        log.info(
            "workflow_steps.reordered",
            template_id=str(template_id),
            step_count=len(updates),
        )
        # Clear detail cache and re-fetch with fresh step order
        try:
            await get_redis().delete(_detail_key(ctx.org_id, template_id))
        except Exception:
            pass
        return await self.get_template(template_id)


# ── Execution Engine — Sprint 34 ──────────────────────────────────────────────

class WorkflowRunImmutableError(Exception):
    """Raised when trying to mutate a completed or cancelled run."""


class SkipRequiredStepError(Exception):
    """Raised when trying to skip a required step."""


class StepStateError(Exception):
    """Raised when a step state transition is invalid."""


# Permission sets for execution operations
_START_CANCEL_ROLES = frozenset({"owner", "admin"})
_STEP_ACTION_ROLES = frozenset({"owner", "admin", "member"})


def _run_list_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_runs:list"


def _run_detail_key(org_id: uuid.UUID, run_id: uuid.UUID) -> str:
    return f"t:{org_id}:workflow_runs:detail:{run_id}"


class WorkflowExecutionService:
    """Human-driven workflow execution: start → step actions → complete.

    No AI. No Celery. No automatic progression. Every state change is explicit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = WorkflowRunRepo(session)
        self._run_step_repo = WorkflowRunStepRepo(session)
        self._template_repo = WorkflowTemplateRepo(session)
        self._step_repo = WorkflowStepRepo(session)

    def _assert_write(self, ctx: object) -> None:
        role = getattr(ctx, "role", "member")
        if role not in _START_CANCEL_ROLES:
            raise PermissionDeniedError(
                f"Role '{role}' cannot start or cancel workflow runs"
            )

    def _assert_step_role(self, ctx: object) -> None:
        role = getattr(ctx, "role", "viewer")
        if role not in _STEP_ACTION_ROLES:
            raise PermissionDeniedError(
                f"Role '{role}' cannot perform step actions"
            )

    async def _invalidate_run(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID | None = None,
    ) -> None:
        keys: list[str] = [_run_list_key(org_id, workspace_id)]
        if run_id is not None:
            keys.append(_run_detail_key(org_id, run_id))
        try:
            await get_redis().delete(*keys)
        except Exception:
            pass

    async def _notify(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: str,
        title: str,
        message: str,
        entity_id: uuid.UUID,
    ) -> None:
        """Fire-and-forget notification — failures are swallowed."""
        try:
            from corpmind.modules.notifications.schemas import NotificationIn
            from corpmind.modules.notifications.service import NotificationService

            await NotificationService(self._session).create(
                NotificationIn(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    entity_type="workflow_run",
                    entity_id=entity_id,
                    priority="medium",
                )
            )
        except Exception:
            pass

    async def _check_and_maybe_complete(
        self, run_id: uuid.UUID, run: WorkflowRun
    ) -> bool:
        """Auto-complete run if all required steps are done. Returns True if completed."""
        ctx = get_tenant_context()
        steps = await self._run_step_repo.find_by_run(run_id)
        if not steps:
            return False
        required = [s for s in steps if s.required]
        if not required:
            return False
        if all(s.status == "completed" for s in required):
            now = datetime.now(UTC)
            await self._run_repo.update_fields(
                run_id, status="completed", completed_at=now
            )
            await self._invalidate_run(ctx.org_id, run.workspace_id, run_id)
            log.info("workflow_run.auto_completed", run_id=str(run_id))
            # Notify started_by
            await self._notify(
                workspace_id=run.workspace_id,
                user_id=run.started_by,
                notification_type="workflow_completed",
                title="Workflow completed",
                message=f'"{run.title}" has been completed.',
                entity_id=run_id,
            )
            return True
        return False

    # ── Run CRUD ──────────────────────────────────────────────────────────────

    async def start_run(self, data: WorkflowRunIn) -> WorkflowRunOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)

        template = await self._template_repo.find_by_id(data.workflow_template_id)
        if template is None:
            raise NotFoundError(
                f"WorkflowTemplate {data.workflow_template_id} not found"
            )

        now = datetime.now(UTC)
        run = WorkflowRun(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=data.workspace_id,
            workflow_template_id=data.workflow_template_id,
            title=data.title,
            status="active",
            started_by=ctx.user_id,
            assigned_to=data.assigned_to,
            started_at=now,
        )
        await self._run_repo.create(run)

        # Snapshot all template steps as independent run steps
        template_steps = await self._step_repo.find_by_template(
            data.workflow_template_id
        )
        for src in template_steps:
            run_step = WorkflowRunStep(
                id=uuid.uuid4(),
                tenant_id=ctx.org_id,
                workspace_id=data.workspace_id,
                workflow_run_id=run.id,
                template_step_id=src.id,
                title=src.title,
                description=src.description,
                owner_role=src.owner_role,
                required=src.required,
                step_order=src.step_order,
                status="pending",
            )
            await self._run_step_repo.create(run_step)

        await self._invalidate_run(ctx.org_id, data.workspace_id)
        log.info(
            "workflow_run.started",
            run_id=str(run.id),
            template_id=str(data.workflow_template_id),
            step_count=len(template_steps),
        )

        # Notify assigned user if set
        if data.assigned_to:
            await self._notify(
                workspace_id=data.workspace_id,
                user_id=data.assigned_to,
                notification_type="workflow_started",
                title="Workflow assigned to you",
                message=f'"{data.title}" has been started and assigned to you.',
                entity_id=run.id,
            )

        return await self.get_run(run.id)

    async def cancel_run(self, run_id: uuid.UUID) -> WorkflowRunOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)

        run = await self._run_repo.find_by_id(run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {run_id} not found")
        if run.status in ("completed", "cancelled"):
            raise WorkflowRunImmutableError(
                f"Run {run_id} is {run.status} and cannot be modified"
            )

        now = datetime.now(UTC)
        await self._run_repo.update_fields(
            run_id, status="cancelled", cancelled_at=now
        )
        run.status = "cancelled"
        run.cancelled_at = now

        await self._invalidate_run(ctx.org_id, run.workspace_id, run_id)
        log.info("workflow_run.cancelled", run_id=str(run_id))

        await self._notify(
            workspace_id=run.workspace_id,
            user_id=run.started_by,
            notification_type="workflow_cancelled",
            title="Workflow cancelled",
            message=f'"{run.title}" has been cancelled.',
            entity_id=run_id,
        )
        return WorkflowRunOut.model_validate(run)

    async def get_run(self, run_id: uuid.UUID) -> WorkflowRunOut:
        ctx = get_tenant_context()
        key = _run_detail_key(ctx.org_id, run_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return WorkflowRunOut.model_validate_json(cached)
        except Exception:
            pass

        run = await self._run_repo.find_by_id(run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {run_id} not found")

        result = WorkflowRunOut.model_validate(run)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_TTL)
        except Exception:
            pass
        return result

    async def list_runs(
        self,
        workspace_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
        status_filter: str | None = None,
    ) -> WorkflowRunListPage:
        ctx = get_tenant_context()
        is_first_page = cursor is None and status_filter is None

        if is_first_page:
            key = _run_list_key(ctx.org_id, workspace_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return WorkflowRunListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._run_repo.list_page(
            workspace_id, limit, cursor, status_filter
        )
        result = WorkflowRunListPage(
            items=[WorkflowRunOut.model_validate(r) for r in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )

        if is_first_page:
            try:
                await get_redis().set(
                    _run_list_key(ctx.org_id, workspace_id),
                    result.model_dump_json(),
                    ex=_TTL,
                )
            except Exception:
                pass

        return result

    # ── Step actions ──────────────────────────────────────────────────────────

    async def complete_step(
        self, step_id: uuid.UUID, data: CompleteStepIn
    ) -> WorkflowRunStepOut:
        ctx = get_tenant_context()
        self._assert_step_role(ctx)

        step = await self._run_step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowRunStep {step_id} not found")

        run = await self._run_repo.find_by_id(step.workflow_run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {step.workflow_run_id} not found")
        if run.status in ("completed", "cancelled"):
            raise WorkflowRunImmutableError(
                f"Run {run.id} is {run.status} and cannot be modified"
            )

        now = datetime.now(UTC)
        await self._run_step_repo.update_fields(
            step_id,
            status="completed",
            completed_by=ctx.user_id,
            completed_at=now,
            notes=data.notes,
        )
        step.status = "completed"
        step.completed_by = ctx.user_id
        step.completed_at = now
        step.notes = data.notes

        await self._invalidate_run(ctx.org_id, run.workspace_id, run.id)
        log.info(
            "workflow_run_step.completed",
            step_id=str(step_id),
            run_id=str(run.id),
        )

        await self._notify(
            workspace_id=run.workspace_id,
            user_id=run.started_by,
            notification_type="workflow_step_completed",
            title="Step completed",
            message=f'Step "{step.title}" in "{run.title}" was completed.',
            entity_id=run.id,
        )

        await self._check_and_maybe_complete(run.id, run)
        return WorkflowRunStepOut.model_validate(step)

    async def reopen_step(self, step_id: uuid.UUID) -> WorkflowRunStepOut:
        ctx = get_tenant_context()
        self._assert_step_role(ctx)

        step = await self._run_step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowRunStep {step_id} not found")

        run = await self._run_repo.find_by_id(step.workflow_run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {step.workflow_run_id} not found")
        if run.status == "cancelled":
            raise WorkflowRunImmutableError(
                f"Run {run.id} is cancelled and cannot be modified"
            )

        await self._run_step_repo.update_fields(
            step_id,
            status="pending",
            completed_by=None,
            completed_at=None,
            notes=None,
        )
        step.status = "pending"
        step.completed_by = None
        step.completed_at = None
        step.notes = None

        # If run was completed, revert it to active
        if run.status == "completed":
            await self._run_repo.update_fields(
                run.id, status="active", completed_at=None
            )
            run.status = "active"

        await self._invalidate_run(ctx.org_id, run.workspace_id, run.id)
        log.info(
            "workflow_run_step.reopened",
            step_id=str(step_id),
            run_id=str(run.id),
        )
        return WorkflowRunStepOut.model_validate(step)

    async def skip_step(
        self, step_id: uuid.UUID, data: SkipStepIn
    ) -> WorkflowRunStepOut:
        ctx = get_tenant_context()
        self._assert_step_role(ctx)

        step = await self._run_step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowRunStep {step_id} not found")
        if step.required:
            raise SkipRequiredStepError(
                f"Step {step_id} is required and cannot be skipped"
            )

        run = await self._run_repo.find_by_id(step.workflow_run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {step.workflow_run_id} not found")
        if run.status in ("completed", "cancelled"):
            raise WorkflowRunImmutableError(
                f"Run {run.id} is {run.status} and cannot be modified"
            )

        await self._run_step_repo.update_fields(
            step_id, status="skipped", notes=data.notes
        )
        step.status = "skipped"
        step.notes = data.notes

        await self._invalidate_run(ctx.org_id, run.workspace_id, run.id)
        log.info(
            "workflow_run_step.skipped",
            step_id=str(step_id),
            run_id=str(run.id),
        )
        return WorkflowRunStepOut.model_validate(step)

    async def block_step(
        self, step_id: uuid.UUID, data: BlockStepIn
    ) -> WorkflowRunStepOut:
        ctx = get_tenant_context()
        self._assert_step_role(ctx)

        step = await self._run_step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowRunStep {step_id} not found")

        run = await self._run_repo.find_by_id(step.workflow_run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {step.workflow_run_id} not found")
        if run.status in ("completed", "cancelled"):
            raise WorkflowRunImmutableError(
                f"Run {run.id} is {run.status} and cannot be modified"
            )

        await self._run_step_repo.update_fields(
            step_id, status="blocked", notes=data.notes
        )
        step.status = "blocked"
        step.notes = data.notes

        await self._invalidate_run(ctx.org_id, run.workspace_id, run.id)
        log.info(
            "workflow_run_step.blocked",
            step_id=str(step_id),
            run_id=str(run.id),
        )
        return WorkflowRunStepOut.model_validate(step)

    async def resume_step(self, step_id: uuid.UUID) -> WorkflowRunStepOut:
        ctx = get_tenant_context()
        self._assert_step_role(ctx)

        step = await self._run_step_repo.find_by_id(step_id)
        if step is None:
            raise NotFoundError(f"WorkflowRunStep {step_id} not found")
        if step.status != "blocked":
            raise StepStateError(
                f"Step {step_id} is not blocked (current status: {step.status})"
            )

        run = await self._run_repo.find_by_id(step.workflow_run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {step.workflow_run_id} not found")
        if run.status in ("completed", "cancelled"):
            raise WorkflowRunImmutableError(
                f"Run {run.id} is {run.status} and cannot be modified"
            )

        await self._run_step_repo.update_fields(step_id, status="in_progress")
        step.status = "in_progress"

        await self._invalidate_run(ctx.org_id, run.workspace_id, run.id)
        log.info(
            "workflow_run_step.resumed",
            step_id=str(step_id),
            run_id=str(run.id),
        )
        return WorkflowRunStepOut.model_validate(step)
