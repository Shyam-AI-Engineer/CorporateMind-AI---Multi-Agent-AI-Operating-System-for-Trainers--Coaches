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
    AnalyticsSummaryOut,
    AttachEntityIn,
    BlockStepIn,
    BottleneckAnalyticsOut,
    BottleneckItem,
    CompleteStepIn,
    CompletionImpactItem,
    CompletionImpactOut,
    DurationBucketItem,
    DurationImpactOut,
    EffectivenessEntityItem,
    EffectivenessEntityOut,
    EffectivenessSummaryOut,
    EffectivenessTemplateItem,
    EffectivenessTemplateOut,
    EntityRunListPage,
    ReorderStepsIn,
    SLAOverdueItem,
    SLAOverdueOut,
    SLAOwnerItem,
    SLAOwnerOut,
    SLASummaryOut,
    SLATemplateItem,
    SLATemplateOut,
    SLATrendBucket,
    SLATrendOut,
    SkipStepIn,
    TemplateAnalyticsItem,
    TemplateAnalyticsOut,
    TrendAnalyticsOut,
    TrendBucket,
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
    WorkloadAnalyticsOut,
    WorkloadItem,
    BottleneckObsItem,
    BottleneckObsOut,
    FlowHealthOut,
    OwnerCapacityItem,
    OwnerCapacityOut,
    StepAnalysisItem,
    StepAnalysisOut,
    TemplateCapacityItem,
    TemplateCapacityOut,
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


class DuplicateActiveEntityRunError(Exception):
    """Raised when entity already has an active or pending run."""


# Permission sets for execution operations
_START_CANCEL_ROLES = frozenset({"owner", "admin"})
_STEP_ACTION_ROLES = frozenset({"owner", "admin", "member"})


def _run_list_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_runs:list"


def _run_detail_key(org_id: uuid.UUID, run_id: uuid.UUID) -> str:
    return f"t:{org_id}:workflow_runs:detail:{run_id}"


def _entity_runs_key(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_entity_runs:{entity_type}:{entity_id}"


def _active_entity_key(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_active_entity:{entity_type}:{entity_id}"


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

    # ── Entity integration — Sprint 35 ────────────────────────────────────────

    async def _invalidate_entity(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> None:
        keys = [
            _entity_runs_key(org_id, workspace_id, entity_type, entity_id),
            _active_entity_key(org_id, workspace_id, entity_type, entity_id),
        ]
        try:
            await get_redis().delete(*keys)
        except Exception:
            pass

    async def attach_entity(
        self, run_id: uuid.UUID, data: AttachEntityIn
    ) -> WorkflowRunOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)

        run = await self._run_repo.find_by_id(run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {run_id} not found")

        # Enforce: one active/pending run per entity (different run must not be active)
        existing = await self._run_repo.find_active_entity_run(
            run.workspace_id, data.entity_type, data.entity_id
        )
        if existing is not None and existing.id != run_id:
            raise DuplicateActiveEntityRunError(
                f"Entity {data.entity_type}/{data.entity_id} already has an active run "
                f"({existing.id})"
            )

        await self._run_repo.update_fields(
            run_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            entity_title=data.entity_title,
        )
        run.entity_type = data.entity_type
        run.entity_id = data.entity_id
        run.entity_title = data.entity_title

        await self._invalidate_run(ctx.org_id, run.workspace_id, run_id)
        await self._invalidate_entity(
            ctx.org_id, run.workspace_id, data.entity_type, data.entity_id
        )
        log.info(
            "workflow_run.entity_attached",
            run_id=str(run_id),
            entity_type=data.entity_type,
            entity_id=str(data.entity_id),
        )

        await self._notify(
            workspace_id=run.workspace_id,
            user_id=run.started_by,
            notification_type="workflow_entity_attached",
            title="Workflow linked to entity",
            message=(
                f'"{run.title}" has been linked to {data.entity_type} '
                f'"{data.entity_title}".'
            ),
            entity_id=run_id,
        )
        return WorkflowRunOut.model_validate(run)

    async def detach_entity(self, run_id: uuid.UUID) -> WorkflowRunOut:
        ctx = get_tenant_context()
        self._assert_write(ctx)

        run = await self._run_repo.find_by_id(run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {run_id} not found")

        old_entity_type = run.entity_type
        old_entity_id = run.entity_id

        await self._run_repo.update_fields(
            run_id,
            entity_type=None,
            entity_id=None,
            entity_title=None,
        )
        run.entity_type = None
        run.entity_id = None
        run.entity_title = None

        await self._invalidate_run(ctx.org_id, run.workspace_id, run_id)
        if old_entity_type and old_entity_id:
            await self._invalidate_entity(
                ctx.org_id, run.workspace_id, old_entity_type, old_entity_id
            )
        log.info("workflow_run.entity_detached", run_id=str(run_id))

        await self._notify(
            workspace_id=run.workspace_id,
            user_id=run.started_by,
            notification_type="workflow_entity_detached",
            title="Workflow unlinked from entity",
            message=f'"{run.title}" has been unlinked from its entity.',
            entity_id=run_id,
        )
        return WorkflowRunOut.model_validate(run)

    async def list_entity_runs(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> EntityRunListPage:
        ctx = get_tenant_context()
        is_first_page = cursor is None

        if is_first_page:
            key = _entity_runs_key(ctx.org_id, workspace_id, entity_type, entity_id)
            try:
                cached = await get_redis().get(key)
                if cached:
                    return EntityRunListPage.model_validate_json(cached)
            except Exception:
                pass

        items, next_cursor = await self._run_repo.find_by_entity(
            workspace_id, entity_type, entity_id, limit, cursor
        )
        result = EntityRunListPage(
            items=[WorkflowRunOut.model_validate(r) for r in items],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )

        if is_first_page:
            try:
                await get_redis().set(
                    _entity_runs_key(ctx.org_id, workspace_id, entity_type, entity_id),
                    result.model_dump_json(),
                    ex=_TTL,
                )
            except Exception:
                pass

        return result

    async def find_active_run(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> WorkflowRunOut | None:
        ctx = get_tenant_context()
        key = _active_entity_key(ctx.org_id, workspace_id, entity_type, entity_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return WorkflowRunOut.model_validate_json(cached)
        except Exception:
            pass

        run = await self._run_repo.find_active_entity_run(
            workspace_id, entity_type, entity_id
        )
        if run is None:
            return None

        result = WorkflowRunOut.model_validate(run)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_TTL)
        except Exception:
            pass
        return result


# ── Analytics cache key helpers ───────────────────────────────────────────────

_ANALYTICS_TTL = 900  # 15 minutes


def _analytics_summary_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_analytics_summary"


def _analytics_templates_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_analytics_templates"


def _analytics_bottlenecks_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_analytics_bottlenecks"


def _analytics_trends_key(org_id: uuid.UUID, workspace_id: uuid.UUID, period: int) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_analytics_trends:{period}"


def _analytics_workload_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_analytics_workload"


# ── WorkflowAnalyticsService — Sprint 36 ─────────────────────────────────────


class WorkflowAnalyticsService:
    """Read-only analytics service.

    All methods are pure aggregations over existing workflow_runs /
    workflow_run_steps data. No writes. No mutations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = WorkflowRunRepo(session)
        self._template_repo = WorkflowTemplateRepo(session)

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_summary(self, workspace_id: uuid.UUID) -> AnalyticsSummaryOut:
        ctx = get_tenant_context()
        key = _analytics_summary_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return AnalyticsSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_summary(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_ANALYTICS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_summary(runs: list) -> AnalyticsSummaryOut:
        from datetime import timezone

        total = len(runs)
        active = sum(1 for r in runs if r.status in ("active", "pending"))
        completed = sum(1 for r in runs if r.status == "completed")
        cancelled = sum(1 for r in runs if r.status == "cancelled")

        finished = completed + cancelled
        completion_rate = round(completed / finished, 4) if finished > 0 else 0.0

        # Duration averages — completed runs only
        completion_durations: list[float] = []
        for r in runs:
            if r.status == "completed" and r.completed_at and r.started_at:
                delta = (r.completed_at - r.started_at).total_seconds() / 86400
                completion_durations.append(max(delta, 0.0))
        avg_completion = (
            round(sum(completion_durations) / len(completion_durations), 4)
            if completion_durations
            else 0.0
        )

        # Step completion time — (step.completed_at - run.started_at) for completed steps
        step_durations: list[float] = []
        required_counts: list[int] = []
        optional_counts: list[int] = []
        data_integrity_warning = False

        for r in runs:
            steps = r.run_steps
            req = sum(1 for s in steps if s.required)
            opt = sum(1 for s in steps if not s.required)
            required_counts.append(req)
            optional_counts.append(opt)

            for s in steps:
                if s.status == "completed" and s.completed_at and r.started_at:
                    delta = (s.completed_at - r.started_at).total_seconds() / 86400
                    step_durations.append(max(delta, 0.0))
                if s.required and s.status == "skipped":
                    data_integrity_warning = True

        avg_step = (
            round(sum(step_durations) / len(step_durations), 4)
            if step_durations
            else 0.0
        )
        avg_req = (
            round(sum(required_counts) / len(required_counts), 4)
            if required_counts
            else 0.0
        )
        avg_opt = (
            round(sum(optional_counts) / len(optional_counts), 4)
            if optional_counts
            else 0.0
        )

        return AnalyticsSummaryOut(
            total_runs=total,
            active_runs=active,
            completed_runs=completed,
            cancelled_runs=cancelled,
            completion_rate=completion_rate,
            average_completion_days=avg_completion,
            average_step_completion_days=avg_step,
            average_required_steps=avg_req,
            average_optional_steps=avg_opt,
            data_integrity_warning=data_integrity_warning,
        )

    # ── Template analytics ────────────────────────────────────────────────────

    async def get_template_analytics(
        self, workspace_id: uuid.UUID
    ) -> TemplateAnalyticsOut:
        ctx = get_tenant_context()
        key = _analytics_templates_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return TemplateAnalyticsOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {
            str(t.id): t.name for t in templates
        }
        result = self._compute_template_analytics(runs, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_ANALYTICS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_template_analytics(
        runs: list, template_names: dict[str, str]
    ) -> TemplateAnalyticsOut:
        from collections import defaultdict

        groups: dict[str | None, list] = defaultdict(list)
        for r in runs:
            key = str(r.workflow_template_id) if r.workflow_template_id else None
            groups[key].append(r)

        items: list[TemplateAnalyticsItem] = []
        for tmpl_id, grp in groups.items():
            tmpl_name = template_names.get(tmpl_id or "", "Standalone (no template)")
            comp = [r for r in grp if r.status == "completed"]
            canc = [r for r in grp if r.status == "cancelled"]
            finished = len(comp) + len(canc)
            comp_rate = round(len(comp) / finished, 4) if finished > 0 else 0.0

            dur: list[float] = []
            for r in comp:
                if r.completed_at and r.started_at:
                    delta = (r.completed_at - r.started_at).total_seconds() / 86400
                    dur.append(max(delta, 0.0))
            avg_dur = round(sum(dur) / len(dur), 4) if dur else 0.0

            step_totals: list[int] = []
            req_totals: list[int] = []
            opt_totals: list[int] = []
            for r in grp:
                steps = r.run_steps
                step_totals.append(len(steps))
                req_totals.append(sum(1 for s in steps if s.required))
                opt_totals.append(sum(1 for s in steps if not s.required))

            n = len(grp)
            items.append(
                TemplateAnalyticsItem(
                    template_id=tmpl_id,
                    template_name=tmpl_name,
                    runs=n,
                    completed=len(comp),
                    cancelled=len(canc),
                    completion_rate=comp_rate,
                    average_completion_days=avg_dur,
                    average_steps=round(sum(step_totals) / n, 4) if n > 0 else 0.0,
                    average_required_steps=round(sum(req_totals) / n, 4) if n > 0 else 0.0,
                    average_optional_steps=round(sum(opt_totals) / n, 4) if n > 0 else 0.0,
                )
            )

        items.sort(key=lambda x: x.completed, reverse=True)
        return TemplateAnalyticsOut(items=items)

    # ── Bottleneck analytics ──────────────────────────────────────────────────

    async def get_bottlenecks(self, workspace_id: uuid.UUID) -> BottleneckAnalyticsOut:
        ctx = get_tenant_context()
        key = _analytics_bottlenecks_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return BottleneckAnalyticsOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {
            str(t.id): t.name for t in templates
        }
        result = self._compute_bottlenecks(runs, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_ANALYTICS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_bottlenecks(
        runs: list, template_names: dict[str, str]
    ) -> BottleneckAnalyticsOut:
        from collections import defaultdict

        # Group step instances by (template_step_id or fallback key, title, template_name)
        groups: dict[tuple, list] = defaultdict(list)

        for r in runs:
            tmpl_name = template_names.get(
                str(r.workflow_template_id) if r.workflow_template_id else "", ""
            ) or "Standalone"
            for s in r.run_steps:
                key = (
                    str(s.template_step_id) if s.template_step_id else None,
                    s.title,
                    tmpl_name,
                )
                groups[key].append((s, r))

        items: list[BottleneckItem] = []
        for (step_id, step_name, tmpl_name), instances in groups.items():
            times_executed = len(instances)
            completed_count = sum(1 for s, _ in instances if s.status == "completed")
            blocked_count = sum(1 for s, _ in instances if s.status == "blocked")
            skip_count = sum(1 for s, _ in instances if s.status == "skipped")
            comp_rate = (
                round(completed_count / times_executed, 4) if times_executed > 0 else 0.0
            )

            durations: list[float] = []
            for s, r in instances:
                if s.status == "completed" and s.completed_at and r.started_at:
                    delta = (s.completed_at - r.started_at).total_seconds() / 86400
                    durations.append(max(delta, 0.0))
            avg_days = round(sum(durations) / len(durations), 4) if durations else 0.0

            items.append(
                BottleneckItem(
                    step_name=step_name,
                    template_name=tmpl_name,
                    times_executed=times_executed,
                    average_days=avg_days,
                    completion_rate=comp_rate,
                    blocked_count=blocked_count,
                    skip_count=skip_count,
                )
            )

        items.sort(key=lambda x: x.average_days, reverse=True)
        return BottleneckAnalyticsOut(items=items)

    # ── Trend analytics ───────────────────────────────────────────────────────

    async def get_trends(
        self, workspace_id: uuid.UUID, period: int
    ) -> TrendAnalyticsOut:
        ctx = get_tenant_context()
        key = _analytics_trends_key(ctx.org_id, workspace_id, period)
        try:
            cached = await get_redis().get(key)
            if cached:
                return TrendAnalyticsOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_trends(runs, period)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_ANALYTICS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_trends(runs: list, period: int) -> TrendAnalyticsOut:
        from datetime import date, timedelta

        today = datetime.now(UTC).date()
        start_date = today - timedelta(days=period - 1)

        # Build day buckets
        buckets: dict[date, dict[str, int]] = {}
        for i in range(period):
            d = start_date + timedelta(days=i)
            buckets[d] = {"started": 0, "completed": 0, "cancelled": 0}

        for r in runs:
            if r.started_at:
                d = r.started_at.date()
                if d in buckets:
                    buckets[d]["started"] += 1
            if r.status == "completed" and r.completed_at:
                d = r.completed_at.date()
                if d in buckets:
                    buckets[d]["completed"] += 1
            if r.status == "cancelled" and r.cancelled_at:
                d = r.cancelled_at.date()
                if d in buckets:
                    buckets[d]["cancelled"] += 1

        result_buckets: list[TrendBucket] = []
        for d in sorted(buckets.keys()):
            b = buckets[d]
            finished = b["completed"] + b["cancelled"]
            comp_rate = round(b["completed"] / finished, 4) if finished > 0 else 0.0
            result_buckets.append(
                TrendBucket(
                    date=d.isoformat(),
                    runs_started=b["started"],
                    runs_completed=b["completed"],
                    runs_cancelled=b["cancelled"],
                    completion_rate=comp_rate,
                )
            )

        return TrendAnalyticsOut(period=period, buckets=result_buckets)

    # ── Workload analytics ────────────────────────────────────────────────────

    async def get_workload(self, workspace_id: uuid.UUID) -> WorkloadAnalyticsOut:
        ctx = get_tenant_context()
        key = _analytics_workload_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return WorkloadAnalyticsOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_workload(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_ANALYTICS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_workload(runs: list) -> WorkloadAnalyticsOut:
        from collections import defaultdict

        pending_map: dict[str, int] = defaultdict(int)
        completed_map: dict[str, int] = defaultdict(int)
        blocked_map: dict[str, int] = defaultdict(int)
        duration_map: dict[str, list[float]] = defaultdict(list)

        for r in runs:
            for s in r.run_steps:
                role = s.owner_role
                if s.status in ("pending", "in_progress"):
                    pending_map[role] += 1
                elif s.status == "completed":
                    completed_map[role] += 1
                    if s.completed_at and r.started_at:
                        delta = (s.completed_at - r.started_at).total_seconds() / 86400
                        duration_map[role].append(max(delta, 0.0))
                elif s.status == "blocked":
                    blocked_map[role] += 1

        all_roles = set(pending_map) | set(completed_map) | set(blocked_map)
        items: list[WorkloadItem] = []
        for role in sorted(all_roles):
            p = pending_map[role]
            c = completed_map[role]
            bl = blocked_map[role]
            total_steps = p + c + bl
            comp_rate = round(c / total_steps, 4) if total_steps > 0 else 0.0
            durs = duration_map[role]
            avg_days = round(sum(durs) / len(durs), 4) if durs else 0.0
            items.append(
                WorkloadItem(
                    owner=role,
                    pending_steps=p,
                    completed_steps=c,
                    blocked_steps=bl,
                    completion_rate=comp_rate,
                    average_completion_days=avg_days,
                )
            )

        return WorkloadAnalyticsOut(items=items)


# ── SLA cache key helpers — Sprint 37 ─────────────────────────────────────────

_SLA_TTL = 900  # 15 minutes

_SLA_WARNING_MULTIPLIER = 2  # days > SLA * 2 → critical


def _sla_summary_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_sla_summary"


def _sla_overdue_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_sla_overdue"


def _sla_templates_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_sla_templates"


def _sla_owner_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_sla_owner"


def _sla_trend_key(org_id: uuid.UUID, workspace_id: uuid.UUID, period: int) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_sla_trend:{period}"


# ── WorkflowSLAService — Sprint 37 ───────────────────────────────────────────


class WorkflowSLAService:
    """Read-only SLA compliance dashboard.

    Measures SLA compliance against default thresholds (30-day workflow,
    7-day step). Never escalates. Never modifies workflow state.
    """

    _WORKFLOW_SLA = 30   # days
    _STEP_SLA = 7        # days
    _CRITICAL_THRESHOLD = 60  # days > 60 → critical (2× SLA)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = WorkflowRunRepo(session)
        self._template_repo = WorkflowTemplateRepo(session)

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_summary(self, workspace_id: uuid.UUID) -> SLASummaryOut:
        ctx = get_tenant_context()
        key = _sla_summary_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SLASummaryOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        now = datetime.now(UTC)
        result = self._compute_summary(runs, now)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_SLA_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_summary(runs: list, now: datetime) -> SLASummaryOut:
        _SLA = WorkflowSLAService._WORKFLOW_SLA
        _CRITICAL = WorkflowSLAService._CRITICAL_THRESHOLD

        active = [r for r in runs if r.status in ("active", "pending")]
        healthy = 0
        warning_overdue = 0
        critical_overdue = 0
        days_open_list: list[float] = []
        days_overdue_list: list[float] = []
        data_integrity_warning = False

        for r in runs:
            if r.completed_at and r.started_at:
                if (r.completed_at - r.started_at).total_seconds() < 0:
                    data_integrity_warning = True

        for r in active:
            days_open = (now - r.started_at).total_seconds() / 86400
            days_open_list.append(days_open)
            if days_open <= _SLA:
                healthy += 1
            elif days_open <= _CRITICAL:
                warning_overdue += 1
                days_overdue_list.append(days_open - _SLA)
            else:
                critical_overdue += 1
                days_overdue_list.append(days_open - _SLA)

        total_active = len(active)
        overdue_count = warning_overdue + critical_overdue
        compliance_rate = (
            round(healthy / total_active, 4) if total_active > 0 else 1.0
        )
        avg_days_open = (
            round(sum(days_open_list) / len(days_open_list), 4)
            if days_open_list
            else 0.0
        )
        avg_days_overdue = (
            round(sum(days_overdue_list) / len(days_overdue_list), 4)
            if days_overdue_list
            else 0.0
        )

        return SLASummaryOut(
            active_runs=total_active,
            overdue_runs=overdue_count,
            sla_compliance_rate=compliance_rate,
            average_days_open=avg_days_open,
            average_days_overdue=avg_days_overdue,
            critical_overdue=critical_overdue,
            warning_overdue=warning_overdue,
            healthy_runs=healthy,
            data_integrity_warning=data_integrity_warning,
        )

    # ── Overdue list ──────────────────────────────────────────────────────────

    async def get_overdue(self, workspace_id: uuid.UUID) -> SLAOverdueOut:
        ctx = get_tenant_context()
        key = _sla_overdue_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SLAOverdueOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {str(t.id): t.name for t in templates}
        now = datetime.now(UTC)
        result = self._compute_overdue(runs, now, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_SLA_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_overdue(
        runs: list, now: datetime, template_names: dict[str, str]
    ) -> SLAOverdueOut:
        _SLA = WorkflowSLAService._WORKFLOW_SLA
        items: list[SLAOverdueItem] = []

        for r in runs:
            if r.status not in ("active", "pending"):
                continue
            days_open = (now - r.started_at).total_seconds() / 86400
            if days_open <= _SLA:
                continue

            # First non-completed, non-skipped step (by step_order)
            current_step: str | None = None
            owner_role: str | None = None
            for s in sorted(r.run_steps, key=lambda x: x.step_order):
                if s.status not in ("completed", "skipped"):
                    current_step = s.title
                    owner_role = s.owner_role
                    break

            tmpl_name: str | None = template_names.get(
                str(r.workflow_template_id) if r.workflow_template_id else "", None
            ) if r.workflow_template_id else None

            items.append(
                SLAOverdueItem(
                    run_id=str(r.id),
                    title=r.title,
                    template_name=tmpl_name,
                    entity_type=r.entity_type,
                    entity_title=r.entity_title,
                    started_at=r.started_at.isoformat(),
                    days_open=round(days_open, 2),
                    days_overdue=round(days_open - _SLA, 2),
                    current_step=current_step,
                    owner_role=owner_role,
                )
            )

        items.sort(key=lambda x: x.days_overdue, reverse=True)
        return SLAOverdueOut(items=items)

    # ── Template SLA ──────────────────────────────────────────────────────────

    async def get_template_sla(self, workspace_id: uuid.UUID) -> SLATemplateOut:
        ctx = get_tenant_context()
        key = _sla_templates_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SLATemplateOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {str(t.id): t.name for t in templates}
        now = datetime.now(UTC)
        result = self._compute_template_sla(runs, now, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_SLA_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_template_sla(
        runs: list, now: datetime, template_names: dict[str, str]
    ) -> SLATemplateOut:
        from collections import defaultdict

        _SLA = WorkflowSLAService._WORKFLOW_SLA

        groups: dict[str | None, list] = defaultdict(list)
        for r in runs:
            if r.status in ("cancelled",):
                continue
            key: str | None = (
                str(r.workflow_template_id) if r.workflow_template_id else None
            )
            groups[key].append(r)

        items: list[SLATemplateItem] = []
        for tmpl_id, grp in groups.items():
            name = (
                template_names.get(tmpl_id, "Standalone (no template)")
                if tmpl_id
                else "Standalone (no template)"
            )
            overdue_count = 0
            days_open_all: list[float] = []
            days_overdue_list: list[float] = []

            for r in grp:
                if r.status in ("active", "pending"):
                    days_open = (now - r.started_at).total_seconds() / 86400
                    days_open_all.append(days_open)
                    if days_open > _SLA:
                        overdue_count += 1
                        days_overdue_list.append(days_open - _SLA)
                elif r.status == "completed" and r.completed_at and r.started_at:
                    dur = (r.completed_at - r.started_at).total_seconds() / 86400
                    days_open_all.append(max(dur, 0.0))

            n = len(grp)
            active_n = sum(1 for r in grp if r.status in ("active", "pending"))
            compliance_rate = (
                round((active_n - overdue_count) / active_n, 4)
                if active_n > 0
                else 1.0
            )
            avg_dur = (
                round(sum(days_open_all) / len(days_open_all), 4)
                if days_open_all
                else 0.0
            )
            avg_overdue = (
                round(sum(days_overdue_list) / len(days_overdue_list), 4)
                if days_overdue_list
                else 0.0
            )

            items.append(
                SLATemplateItem(
                    template_id=tmpl_id,
                    template_name=name,
                    runs=n,
                    overdue=overdue_count,
                    compliance_rate=compliance_rate,
                    average_duration_days=avg_dur,
                    average_days_overdue=avg_overdue,
                )
            )

        items.sort(key=lambda x: x.overdue, reverse=True)
        return SLATemplateOut(items=items)

    # ── Owner SLA ─────────────────────────────────────────────────────────────

    async def get_owner_sla(self, workspace_id: uuid.UUID) -> SLAOwnerOut:
        ctx = get_tenant_context()
        key = _sla_owner_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SLAOwnerOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        now = datetime.now(UTC)
        result = self._compute_owner_sla(runs, now)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_SLA_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_owner_sla(runs: list, now: datetime) -> SLAOwnerOut:
        from collections import defaultdict

        _STEP_SLA = WorkflowSLAService._STEP_SLA

        assigned_map: dict[str, int] = defaultdict(int)
        completed_map: dict[str, int] = defaultdict(int)
        overdue_map: dict[str, int] = defaultdict(int)
        duration_map: dict[str, list[float]] = defaultdict(list)

        for r in runs:
            if r.status == "cancelled":
                continue
            days_open = (now - r.started_at).total_seconds() / 86400

            for s in r.run_steps:
                if not s.required or s.status == "skipped":
                    continue
                role = s.owner_role
                assigned_map[role] += 1

                if s.status == "completed":
                    completed_map[role] += 1
                    if s.completed_at and r.started_at:
                        dur = (
                            s.completed_at - r.started_at
                        ).total_seconds() / 86400
                        duration_map[role].append(max(dur, 0.0))
                elif r.status in ("active", "pending") and days_open > _STEP_SLA:
                    overdue_map[role] += 1

        all_roles = set(assigned_map) | set(completed_map) | set(overdue_map)
        items: list[SLAOwnerItem] = []
        for role in sorted(all_roles):
            assigned = assigned_map[role]
            completed = completed_map[role]
            overdue = overdue_map[role]
            compliance_rate = (
                round(max(assigned - overdue, 0) / assigned, 4)
                if assigned > 0
                else 1.0
            )
            durs = duration_map[role]
            avg_days = round(sum(durs) / len(durs), 4) if durs else 0.0
            items.append(
                SLAOwnerItem(
                    owner_role=role,
                    assigned_steps=assigned,
                    completed_steps=completed,
                    overdue_steps=overdue,
                    compliance_rate=compliance_rate,
                    average_completion_days=avg_days,
                )
            )

        return SLAOwnerOut(items=items)

    # ── SLA trend ─────────────────────────────────────────────────────────────

    async def get_trend(
        self, workspace_id: uuid.UUID, period: int
    ) -> SLATrendOut:
        ctx = get_tenant_context()
        key = _sla_trend_key(ctx.org_id, workspace_id, period)
        try:
            cached = await get_redis().get(key)
            if cached:
                return SLATrendOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        now = datetime.now(UTC)
        result = self._compute_sla_trend(runs, now, period)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_SLA_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_sla_trend(runs: list, now: datetime, period: int) -> SLATrendOut:
        from datetime import date, timedelta

        _SLA = WorkflowSLAService._WORKFLOW_SLA
        _CRITICAL = WorkflowSLAService._CRITICAL_THRESHOLD

        today = now.date()
        start_date = today - timedelta(days=period - 1)

        buckets: dict[date, dict[str, int]] = {}
        for i in range(period):
            d = start_date + timedelta(days=i)
            buckets[d] = {"healthy": 0, "warning": 0, "critical": 0, "completed": 0}

        for r in runs:
            if r.status == "completed" and r.completed_at:
                d = r.completed_at.date()
                if d in buckets:
                    buckets[d]["completed"] += 1
            elif r.status in ("active", "pending") and r.started_at:
                d = r.started_at.date()
                if d in buckets:
                    days_open = (now - r.started_at).total_seconds() / 86400
                    if days_open <= _SLA:
                        buckets[d]["healthy"] += 1
                    elif days_open <= _CRITICAL:
                        buckets[d]["warning"] += 1
                    else:
                        buckets[d]["critical"] += 1

        result_buckets: list[SLATrendBucket] = []
        for d in sorted(buckets.keys()):
            b = buckets[d]
            result_buckets.append(
                SLATrendBucket(
                    date=d.isoformat(),
                    healthy=b["healthy"],
                    warning=b["warning"],
                    critical=b["critical"],
                    completed=b["completed"],
                )
            )

        return SLATrendOut(period=period, buckets=result_buckets)


# ── Workflow Effectiveness cache key helpers — Sprint 38 ──────────────────────

_EFF_TTL = 900


def _eff_summary_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_effectiveness_summary"


def _eff_templates_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_effectiveness_templates"


def _eff_entities_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_effectiveness_entities"


def _eff_duration_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_effectiveness_duration"


def _eff_completion_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_effectiveness_completion"


class WorkflowEffectivenessService:
    """Read-only effectiveness & ROI dashboard.

    Evaluates whether workflows improve business outcomes by comparing
    execution quality against historical results. Never mutates workflow state.
    """

    _FAST_THRESHOLD = 7   # days — completed in ≤7 days = fast
    _SLOW_THRESHOLD = 30  # days — completed in >30 days = slow

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = WorkflowRunRepo(session)
        self._template_repo = WorkflowTemplateRepo(session)

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_summary(self, workspace_id: uuid.UUID) -> EffectivenessSummaryOut:
        ctx = get_tenant_context()
        key = _eff_summary_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return EffectivenessSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_summary(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_EFF_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_summary(runs: list) -> EffectivenessSummaryOut:
        total = len(runs)
        completed_runs = [r for r in runs if r.status == "completed" and r.completed_at]

        integrity_warning = any(
            r.completed_at < r.started_at for r in completed_runs
        )

        total_completed = len(completed_runs)

        valid_durations = [
            (r.completed_at - r.started_at).total_seconds() / 86400
            for r in completed_runs
            if r.completed_at >= r.started_at
        ]
        avg_completion = (
            sum(valid_durations) / len(valid_durations) if valid_durations else 0.0
        )

        step_durations: list[float] = []
        for r in completed_runs:
            for s in r.run_steps:
                if s.status == "completed" and s.completed_at and s.completed_at >= r.started_at:
                    step_durations.append(
                        (s.completed_at - r.started_at).total_seconds() / 86400
                    )
        avg_step = sum(step_durations) / len(step_durations) if step_durations else 0.0

        runs_with_entity = sum(1 for r in runs if r.entity_type)
        entity_coverage = runs_with_entity / total if total else 0.0

        _fast = WorkflowEffectivenessService._FAST_THRESHOLD
        _slow = WorkflowEffectivenessService._SLOW_THRESHOLD
        fast_count = sum(1 for d in valid_durations if d <= _fast)
        slow_count = sum(1 for d in valid_durations if d > _slow)
        fast_rate = fast_count / total_completed if total_completed else 0.0
        slow_rate = slow_count / total_completed if total_completed else 0.0

        completion_rate = total_completed / total if total else 0.0
        eff_score = round(completion_rate * 100, 1)

        return EffectivenessSummaryOut(
            total_completed=total_completed,
            average_completion_days=round(avg_completion, 2),
            average_step_completion_days=round(avg_step, 2),
            entity_coverage=round(entity_coverage, 4),
            fast_completion_rate=round(fast_rate, 4),
            slow_completion_rate=round(slow_rate, 4),
            overall_effectiveness_score=eff_score,
            data_integrity_warning=integrity_warning,
        )

    # ── Template effectiveness ─────────────────────────────────────────────────

    async def get_template_effectiveness(
        self, workspace_id: uuid.UUID
    ) -> EffectivenessTemplateOut:
        ctx = get_tenant_context()
        key = _eff_templates_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return EffectivenessTemplateOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {str(t.id): t.name for t in templates}
        result = self._compute_template_effectiveness(runs, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_EFF_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_template_effectiveness(
        runs: list, template_names: dict[str, str]
    ) -> EffectivenessTemplateOut:
        groups: dict[str | None, list] = {}
        for r in runs:
            key = str(r.workflow_template_id) if r.workflow_template_id else None
            groups.setdefault(key, []).append(r)

        items: list[EffectivenessTemplateItem] = []
        for tid, group_runs in groups.items():
            total = len(group_runs)
            completed = [
                r for r in group_runs if r.status == "completed" and r.completed_at
            ]
            n_completed = len(completed)
            completion_rate = n_completed / total if total else 0.0

            valid_dur = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in completed
                if r.completed_at >= r.started_at
            ]
            avg_dur = sum(valid_dur) / len(valid_dur) if valid_dur else 0.0

            tname = template_names.get(tid, "Unknown") if tid else "No Template"
            items.append(
                EffectivenessTemplateItem(
                    template_id=tid,
                    template_name=tname,
                    runs=total,
                    completed=n_completed,
                    completion_rate=round(completion_rate, 4),
                    average_duration=round(avg_dur, 2),
                    effectiveness_score=round(completion_rate * 100, 1),
                )
            )

        items.sort(key=lambda x: x.effectiveness_score, reverse=True)
        return EffectivenessTemplateOut(items=items)

    # ── Entity type effectiveness ──────────────────────────────────────────────

    async def get_entity_type_effectiveness(
        self, workspace_id: uuid.UUID
    ) -> EffectivenessEntityOut:
        ctx = get_tenant_context()
        key = _eff_entities_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return EffectivenessEntityOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_entity_type_effectiveness(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_EFF_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_entity_type_effectiveness(runs: list) -> EffectivenessEntityOut:
        groups: dict[str, list] = {}
        for r in runs:
            etype = r.entity_type if r.entity_type else "other"
            groups.setdefault(etype, []).append(r)

        items: list[EffectivenessEntityItem] = []
        for etype, group_runs in groups.items():
            total = len(group_runs)
            completed = [
                r for r in group_runs if r.status == "completed" and r.completed_at
            ]
            n_completed = len(completed)
            completion_rate = n_completed / total if total else 0.0

            valid_dur = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in completed
                if r.completed_at >= r.started_at
            ]
            avg_dur = sum(valid_dur) / len(valid_dur) if valid_dur else 0.0

            items.append(
                EffectivenessEntityItem(
                    entity_type=etype,
                    workflow_count=total,
                    completion_rate=round(completion_rate, 4),
                    average_duration=round(avg_dur, 2),
                    effectiveness_score=round(completion_rate * 100, 1),
                )
            )

        items.sort(key=lambda x: x.effectiveness_score, reverse=True)
        return EffectivenessEntityOut(items=items)

    # ── Duration impact ───────────────────────────────────────────────────────

    async def get_duration_impact(self, workspace_id: uuid.UUID) -> DurationImpactOut:
        ctx = get_tenant_context()
        key = _eff_duration_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return DurationImpactOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        now = datetime.now(UTC)
        result = self._compute_duration_impact(runs, now)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_EFF_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _bucket_label(days: float) -> str:
        if days < 4:
            return "0–3 days"
        elif days < 8:
            return "4–7 days"
        elif days < 15:
            return "8–14 days"
        elif days < 31:
            return "15–30 days"
        else:
            return "30+ days"

    _BUCKET_ORDER = ["0–3 days", "4–7 days", "8–14 days", "15–30 days", "30+ days"]

    @staticmethod
    def _compute_duration_impact(runs: list, now: datetime) -> DurationImpactOut:
        bucket_runs: dict[str, list] = {
            label: [] for label in WorkflowEffectivenessService._BUCKET_ORDER
        }

        for r in runs:
            if r.status == "completed" and r.completed_at:
                raw = (r.completed_at - r.started_at).total_seconds() / 86400
                days = max(raw, 0.0)
            elif r.status == "cancelled" and r.cancelled_at:
                days = (r.cancelled_at - r.started_at).total_seconds() / 86400
            else:
                days = (now - r.started_at).total_seconds() / 86400
            label = WorkflowEffectivenessService._bucket_label(days)
            bucket_runs[label].append(r)

        buckets: list[DurationBucketItem] = []
        for label in WorkflowEffectivenessService._BUCKET_ORDER:
            group = bucket_runs[label]
            total = len(group)
            completed = sum(1 for r in group if r.status == "completed")
            completion_rate = completed / total if total else 0.0
            avg_steps = (
                sum(len(r.run_steps) for r in group) / total if total else 0.0
            )
            buckets.append(
                DurationBucketItem(
                    label=label,
                    completed=completed,
                    completion_rate=round(completion_rate, 4),
                    average_steps=round(avg_steps, 2),
                    effectiveness_score=round(completion_rate * 100, 1),
                )
            )
        return DurationImpactOut(buckets=buckets)

    # ── Completion impact ─────────────────────────────────────────────────────

    async def get_completion_impact(
        self, workspace_id: uuid.UUID
    ) -> CompletionImpactOut:
        ctx = get_tenant_context()
        key = _eff_completion_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return CompletionImpactOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        now = datetime.now(UTC)
        result = self._compute_completion_impact(runs, now)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_EFF_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_completion_impact(runs: list, now: datetime) -> CompletionImpactOut:
        completed_runs = [r for r in runs if r.status == "completed"]
        cancelled_runs = [r for r in runs if r.status == "cancelled"]
        active_runs = [r for r in runs if r.status in ("active", "pending")]

        def _avg_dur_completed(group: list) -> float:
            durations = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in group
                if r.completed_at and r.completed_at >= r.started_at
            ]
            return round(sum(durations) / len(durations), 2) if durations else 0.0

        def _avg_dur_active(group: list) -> float:
            durations = [
                (now - r.started_at).total_seconds() / 86400 for r in group
            ]
            return round(sum(durations) / len(durations), 2) if durations else 0.0

        items = [
            CompletionImpactItem(
                status="completed",
                count=len(completed_runs),
                average_duration=_avg_dur_completed(completed_runs),
                effectiveness_score=100.0,
            ),
            CompletionImpactItem(
                status="cancelled",
                count=len(cancelled_runs),
                average_duration=0.0,
                effectiveness_score=0.0,
            ),
            CompletionImpactItem(
                status="active",
                count=len(active_runs),
                average_duration=_avg_dur_active(active_runs),
                effectiveness_score=50.0,
            ),
        ]
        return CompletionImpactOut(items=items)


# ── Observability cache key helpers — Sprint 39 ───────────────────────────────

_OBS_TTL = 900  # 15 minutes


def _obs_bottlenecks_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_observability_bottlenecks"


def _obs_steps_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_observability_steps"


def _obs_owner_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_observability_owner"


def _obs_templates_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_observability_templates"


def _obs_flow_health_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:{workspace_id}:workflow_observability_flow_health"


# ── WorkflowObservabilityService — Sprint 39 ─────────────────────────────────


class WorkflowObservabilityService:
    """Read-only bottleneck and capacity analytics.

    All aggregations are computed in-memory from workflow_runs + run_steps.
    No writes. No mutations. No AI.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._run_repo = WorkflowRunRepo(session)
        self._template_repo = WorkflowTemplateRepo(session)

    # ── Bottlenecks ───────────────────────────────────────────────────────────

    async def get_bottlenecks(self, workspace_id: uuid.UUID) -> BottleneckObsOut:
        ctx = get_tenant_context()
        key = _obs_bottlenecks_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return BottleneckObsOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {str(t.id): t.name for t in templates}
        result = self._compute_bottlenecks(runs, template_names)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_OBS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_bottlenecks(
        runs: list, template_names: dict[str, str]
    ) -> BottleneckObsOut:
        # Group runs by template
        template_runs: dict[str, list] = {}
        for r in runs:
            key = (
                str(r.workflow_template_id) if r.workflow_template_id else "__none__"
            )
            template_runs.setdefault(key, []).append(r)

        items: list[BottleneckObsItem] = []
        for tmpl_key, t_runs in template_runs.items():
            tmpl_name = template_names.get(tmpl_key, "No Template")

            # Collect step durations grouped by step title
            step_durations: dict[str, list[float]] = {}
            for r in t_runs:
                if r.status != "completed":
                    continue
                for s in r.run_steps:
                    if s.status != "completed" or not s.completed_at:
                        continue
                    ref = s.started_at if s.started_at else r.started_at
                    if not ref:
                        continue
                    raw = (s.completed_at - ref).total_seconds() / 86400
                    days = max(raw, 0.0)
                    step_durations.setdefault(s.title, []).append(days)

            if not step_durations:
                continue

            # Find the slowest step by average
            slowest_name = max(
                step_durations,
                key=lambda t: sum(step_durations[t]) / len(step_durations[t]),
            )
            durations = step_durations[slowest_name]
            avg_days = round(sum(durations) / len(durations), 2)
            max_days = round(max(durations), 2)

            # runs_affected = completed runs that have this step
            runs_affected = sum(
                1
                for r in t_runs
                if r.status == "completed"
                and any(s.title == slowest_name for s in r.run_steps)
            )

            # bottleneck_score = fraction of avg run duration spent on this step
            run_durations = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in t_runs
                if r.status == "completed"
                and r.completed_at
                and r.completed_at >= r.started_at
            ]
            avg_run_dur = (
                sum(run_durations) / len(run_durations) if run_durations else 0.0
            )
            bottleneck_score = (
                round(min(avg_days / avg_run_dur * 100, 100.0), 1)
                if avg_run_dur > 0
                else 0.0
            )

            items.append(
                BottleneckObsItem(
                    template_name=tmpl_name,
                    slowest_step=slowest_name,
                    average_days=avg_days,
                    max_days=max_days,
                    runs_affected=runs_affected,
                    bottleneck_score=bottleneck_score,
                )
            )

        items.sort(key=lambda x: x.bottleneck_score, reverse=True)
        return BottleneckObsOut(items=items)

    # ── Step analysis ─────────────────────────────────────────────────────────

    async def get_step_analysis(self, workspace_id: uuid.UUID) -> StepAnalysisOut:
        ctx = get_tenant_context()
        key = _obs_steps_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return StepAnalysisOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_step_analysis(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_OBS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_step_analysis(runs: list) -> StepAnalysisOut:
        from statistics import median as _median

        # Collect all steps grouped by title
        step_groups: dict[str, list] = {}
        step_ref_run: dict[str, list] = {}  # step title → list of (step, run) pairs
        for r in runs:
            for s in r.run_steps:
                step_groups.setdefault(s.title, []).append(s)
                step_ref_run.setdefault(s.title, []).append((s, r))

        items: list[StepAnalysisItem] = []
        for step_name, steps in step_groups.items():
            total = len(steps)
            completed = [s for s in steps if s.status == "completed"]
            blocked = sum(1 for s in steps if s.status == "blocked")
            skipped = sum(1 for s in steps if s.status == "skipped")
            completion_rate = round(len(completed) / total, 4) if total > 0 else 0.0
            skip_rate = round(skipped / total, 4) if total > 0 else 0.0

            # Duration: (step.completed_at - step.started_at or run.started_at)
            durations: list[float] = []
            for s, r in step_ref_run[step_name]:
                if s.status != "completed" or not s.completed_at:
                    continue
                ref = s.started_at if s.started_at else r.started_at
                if not ref:
                    continue
                raw = (s.completed_at - ref).total_seconds() / 86400
                durations.append(max(raw, 0.0))

            avg_days = round(sum(durations) / len(durations), 2) if durations else 0.0
            med_days = round(_median(durations), 2) if durations else 0.0

            items.append(
                StepAnalysisItem(
                    step_name=step_name,
                    completed_count=len(completed),
                    average_completion_days=avg_days,
                    median_completion_days=med_days,
                    blocked_count=blocked,
                    skip_rate=skip_rate,
                    completion_rate=completion_rate,
                )
            )

        items.sort(key=lambda x: x.average_completion_days, reverse=True)
        return StepAnalysisOut(items=items)

    # ── Owner capacity ────────────────────────────────────────────────────────

    async def get_owner_capacity(self, workspace_id: uuid.UUID) -> OwnerCapacityOut:
        ctx = get_tenant_context()
        key = _obs_owner_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return OwnerCapacityOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_owner_capacity(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_OBS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_owner_capacity(runs: list) -> OwnerCapacityOut:
        role_steps: dict[str, list] = {}  # role → [(step, run), ...]
        for r in runs:
            for s in r.run_steps:
                role_steps.setdefault(s.owner_role, []).append((s, r))

        items: list[OwnerCapacityItem] = []
        for role, pairs in role_steps.items():
            total = len(pairs)
            completed = [(s, r) for s, r in pairs if s.status == "completed"]
            blocked = sum(1 for s, _ in pairs if s.status == "blocked")

            durations: list[float] = []
            for s, r in completed:
                if not s.completed_at:
                    continue
                ref = s.started_at if s.started_at else r.started_at
                if not ref:
                    continue
                raw = (s.completed_at - ref).total_seconds() / 86400
                durations.append(max(raw, 0.0))

            avg_days = round(sum(durations) / len(durations), 2) if durations else 0.0
            capacity_score = round(len(completed) / total * 100, 1) if total > 0 else 0.0

            items.append(
                OwnerCapacityItem(
                    owner_role=role,
                    assigned_steps=total,
                    completed_steps=len(completed),
                    blocked_steps=blocked,
                    average_completion_days=avg_days,
                    capacity_score=capacity_score,
                )
            )

        items.sort(key=lambda x: x.capacity_score, reverse=True)
        return OwnerCapacityOut(items=items)

    # ── Template capacity ─────────────────────────────────────────────────────

    async def get_template_capacity(
        self, workspace_id: uuid.UUID
    ) -> TemplateCapacityOut:
        ctx = get_tenant_context()
        key = _obs_templates_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return TemplateCapacityOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        templates = await self._template_repo.find_all_for_workspace(workspace_id)
        template_names: dict[str, str] = {str(t.id): t.name for t in templates}
        now = datetime.now(UTC)
        result = self._compute_template_capacity(runs, template_names, now)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_OBS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _compute_template_capacity(
        runs: list, template_names: dict[str, str], now: datetime
    ) -> TemplateCapacityOut:
        template_runs: dict[str, list] = {}
        for r in runs:
            key = (
                str(r.workflow_template_id) if r.workflow_template_id else "__none__"
            )
            template_runs.setdefault(key, []).append(r)

        items: list[TemplateCapacityItem] = []
        for tmpl_key, t_runs in template_runs.items():
            tmpl_name = template_names.get(tmpl_key, "No Template")
            active = sum(1 for r in t_runs if r.status in ("active", "pending"))
            completed = sum(1 for r in t_runs if r.status == "completed")

            # Average completion days — completed runs only
            comp_durations = [
                (r.completed_at - r.started_at).total_seconds() / 86400
                for r in t_runs
                if r.status == "completed"
                and r.completed_at
                and r.completed_at >= r.started_at
            ]
            avg_completion = (
                round(sum(comp_durations) / len(comp_durations), 2)
                if comp_durations
                else 0.0
            )

            # Average parallel runs via Little's Law approximation
            if t_runs:
                min_start = min(r.started_at for r in t_runs if r.started_at)
                span_secs = max(
                    (now - min_start).total_seconds(), 86400.0
                )  # at least 1 day
                total_duration_secs = sum(
                    (r.completed_at - r.started_at).total_seconds()
                    for r in t_runs
                    if r.status == "completed"
                    and r.completed_at
                    and r.completed_at >= r.started_at
                ) + sum(
                    (now - r.started_at).total_seconds()
                    for r in t_runs
                    if r.status in ("active", "pending")
                )
                avg_parallel = round(total_duration_secs / span_secs, 2)
            else:
                avg_parallel = 0.0

            # Capacity rating based on average parallel runs
            if avg_parallel < 2.0:
                rating = "low"
            elif avg_parallel < 5.0:
                rating = "medium"
            else:
                rating = "high"

            items.append(
                TemplateCapacityItem(
                    template_name=tmpl_name,
                    active_runs=active,
                    completed_runs=completed,
                    average_parallel_runs=avg_parallel,
                    average_completion_days=avg_completion,
                    capacity_rating=rating,
                )
            )

        items.sort(key=lambda x: x.average_parallel_runs, reverse=True)
        return TemplateCapacityOut(items=items)

    # ── Flow health ───────────────────────────────────────────────────────────

    async def get_flow_health(self, workspace_id: uuid.UUID) -> FlowHealthOut:
        ctx = get_tenant_context()
        key = _obs_flow_health_key(ctx.org_id, workspace_id)
        try:
            cached = await get_redis().get(key)
            if cached:
                return FlowHealthOut.model_validate_json(cached)
        except Exception:
            pass

        runs = await self._run_repo.find_all_for_workspace(workspace_id)
        result = self._compute_flow_health(runs)
        try:
            await get_redis().set(key, result.model_dump_json(), ex=_OBS_TTL)
        except Exception:
            pass
        return result

    @staticmethod
    def _classify_flow(run) -> str:
        """Returns 'healthy', 'warning', or 'critical' for a single run."""
        if run.status == "completed":
            return "healthy"
        if run.status == "cancelled":
            return "critical"
        # active / pending
        steps = run.run_steps
        total = len(steps)
        blocked = sum(1 for s in steps if s.status == "blocked")
        if blocked == 0:
            return "healthy"
        if total > 0 and blocked / total >= 0.5:
            return "critical"
        return "warning"

    @staticmethod
    def _compute_flow_health(runs: list) -> FlowHealthOut:
        healthy = 0
        warning = 0
        critical = 0
        data_integrity_warning = False

        run_durations: list[float] = []
        step_durations: list[float] = []

        for r in runs:
            classification = WorkflowObservabilityService._classify_flow(r)
            if classification == "healthy":
                healthy += 1
            elif classification == "warning":
                warning += 1
            else:
                critical += 1

            # Run duration — completed only
            if r.status == "completed" and r.completed_at and r.started_at:
                raw = (r.completed_at - r.started_at).total_seconds() / 86400
                if raw < 0:
                    data_integrity_warning = True
                else:
                    run_durations.append(raw)

            # Step duration — completed steps in completed runs
            if r.status == "completed":
                for s in r.run_steps:
                    if s.status == "completed" and s.completed_at and r.started_at:
                        ref = s.started_at if s.started_at else r.started_at
                        raw = (s.completed_at - ref).total_seconds() / 86400
                        step_durations.append(max(raw, 0.0))

        total = len(runs)
        flow_health_score = round(healthy / total * 100, 1) if total > 0 else 0.0

        avg_step = (
            round(sum(step_durations) / len(step_durations), 2)
            if step_durations
            else 0.0
        )
        avg_run = (
            round(sum(run_durations) / len(run_durations), 2)
            if run_durations
            else 0.0
        )

        return FlowHealthOut(
            healthy_flows=healthy,
            warning_flows=warning,
            critical_flows=critical,
            average_step_completion_days=avg_step,
            average_run_completion_days=avg_run,
            flow_health_score=flow_health_score,
            data_integrity_warning=data_integrity_warning,
        )
