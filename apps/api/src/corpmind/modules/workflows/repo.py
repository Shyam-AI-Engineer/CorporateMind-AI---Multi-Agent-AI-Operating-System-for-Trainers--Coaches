"""Workflow Templates & Playbooks + Execution Engine repositories — Sprint 33/34."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.workflows.models import (
    WorkflowRun,
    WorkflowRunStep,
    WorkflowStep,
    WorkflowTemplate,
)


class WorkflowTemplateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, template: WorkflowTemplate) -> WorkflowTemplate:
        self._session.add(template)
        await self._session.flush()
        await self._session.refresh(template)
        return template

    async def find_by_id(self, template_id: uuid.UUID) -> WorkflowTemplate | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, template_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(WorkflowTemplate)
            .where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def delete_by_id(self, template_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            delete(WorkflowTemplate).where(
                WorkflowTemplate.id == template_id,
                WorkflowTemplate.tenant_id == ctx.org_id,
            )
        )

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[WorkflowTemplate], str | None]:
        """Cursor-paginated list, newest-first."""
        ctx = get_tenant_context()
        stmt = (
            select(WorkflowTemplate)
            .where(
                WorkflowTemplate.tenant_id == ctx.org_id,
                WorkflowTemplate.workspace_id == workspace_id,
            )
            .order_by(WorkflowTemplate.created_at.desc(), WorkflowTemplate.id.desc())
        )

        if category:
            stmt = stmt.where(WorkflowTemplate.category == category)
        if is_active is not None:
            stmt = stmt.where(WorkflowTemplate.is_active == is_active)

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (WorkflowTemplate.created_at < cursor_ts)
                    | (
                        (WorkflowTemplate.created_at == cursor_ts)
                        & (WorkflowTemplate.id < cursor_id)
                    )
                )
            except Exception:
                pass

        result = await self._session.execute(stmt.limit(limit + 1))
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw = f"{last.created_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return items, next_cursor

    async def find_all_for_workspace(self, workspace_id: uuid.UUID) -> list[WorkflowTemplate]:
        """Load all templates for a workspace (used by analytics service)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowTemplate)
            .where(
                WorkflowTemplate.tenant_id == ctx.org_id,
                WorkflowTemplate.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())


class WorkflowStepRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, step: WorkflowStep) -> WorkflowStep:
        self._session.add(step)
        await self._session.flush()
        await self._session.refresh(step)
        return step

    async def find_by_id(self, step_id: uuid.UUID) -> WorkflowStep | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowStep).where(
                WorkflowStep.id == step_id,
                WorkflowStep.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_template(self, template_id: uuid.UUID) -> list[WorkflowStep]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowStep)
            .where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.tenant_id == ctx.org_id,
            )
            .order_by(WorkflowStep.step_order.asc())
        )
        return list(result.scalars().all())

    async def max_step_order(self, template_id: uuid.UUID) -> int:
        ctx = get_tenant_context()
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.max(WorkflowStep.step_order)).where(
                WorkflowStep.workflow_template_id == template_id,
                WorkflowStep.tenant_id == ctx.org_id,
            )
        )
        return result.scalar() or 0

    async def update_fields(self, step_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(WorkflowStep)
            .where(
                WorkflowStep.id == step_id,
                WorkflowStep.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def delete_by_id(self, step_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            delete(WorkflowStep).where(
                WorkflowStep.id == step_id,
                WorkflowStep.tenant_id == ctx.org_id,
            )
        )

    async def bulk_update_order(
        self, updates: list[tuple[uuid.UUID, int]]
    ) -> None:
        """Bulk-update step_order for multiple steps in one transaction.

        Uses a deferred unique constraint so intermediate states don't clash.
        updates: list of (step_id, new_order)
        """
        ctx = get_tenant_context()
        # Use negative temporary values to avoid mid-transaction unique violations
        # then set the real values. The constraint is DEFERRABLE INITIALLY DEFERRED,
        # so the final check only happens at commit.
        for step_id, new_order in updates:
            await self._session.execute(
                update(WorkflowStep)
                .where(
                    WorkflowStep.id == step_id,
                    WorkflowStep.tenant_id == ctx.org_id,
                )
                .values(step_order=new_order)
            )


# ── Execution Engine Repositories — Sprint 34 ────────────────────────────────


class WorkflowRunRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: WorkflowRun) -> WorkflowRun:
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def find_by_id(self, run_id: uuid.UUID) -> WorkflowRun | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id,
                WorkflowRun.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, run_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        status_filter: str | None = None,
    ) -> tuple[list[WorkflowRun], str | None]:
        """Cursor-paginated list, newest-first (by started_at)."""
        ctx = get_tenant_context()
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
            )
            .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
        )

        if status_filter:
            stmt = stmt.where(WorkflowRun.status == status_filter)

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (WorkflowRun.started_at < cursor_ts)
                    | (
                        (WorkflowRun.started_at == cursor_ts)
                        & (WorkflowRun.id < cursor_id)
                    )
                )
            except Exception:
                pass

        result = await self._session.execute(stmt.limit(limit + 1))
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw = f"{last.started_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return items, next_cursor


    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[WorkflowRun], str | None]:
        """Cursor-paginated list of runs attached to an entity, newest-first."""
        ctx = get_tenant_context()
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.entity_type == entity_type,
                WorkflowRun.entity_id == entity_id,
            )
            .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
        )

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (WorkflowRun.started_at < cursor_ts)
                    | (
                        (WorkflowRun.started_at == cursor_ts)
                        & (WorkflowRun.id < cursor_id)
                    )
                )
            except Exception:
                pass

        result = await self._session.execute(stmt.limit(limit + 1))
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw = f"{last.started_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return items, next_cursor

    async def find_active_entity_run(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> WorkflowRun | None:
        """Return the single active/pending run for an entity, or None."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRun).where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.entity_type == entity_type,
                WorkflowRun.entity_id == entity_id,
                WorkflowRun.status.in_(["pending", "active"]),
            )
        )
        return result.scalar_one_or_none()


    async def find_by_entity(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[WorkflowRun], str | None]:
        """Cursor-paginated list of runs attached to an entity, newest-first."""
        ctx = get_tenant_context()
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.entity_type == entity_type,
                WorkflowRun.entity_id == entity_id,
            )
            .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
        )

        if cursor:
            try:
                raw = base64.b64decode(cursor.encode()).decode()
                ts_str, id_str = raw.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (WorkflowRun.started_at < cursor_ts)
                    | (
                        (WorkflowRun.started_at == cursor_ts)
                        & (WorkflowRun.id < cursor_id)
                    )
                )
            except Exception:
                pass

        result = await self._session.execute(stmt.limit(limit + 1))
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw = f"{last.started_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return items, next_cursor

    async def find_active_entity_run(
        self,
        workspace_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> WorkflowRun | None:
        """Return the single active/pending run for an entity, or None."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRun).where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.entity_type == entity_type,
                WorkflowRun.entity_id == entity_id,
                WorkflowRun.status.in_(["pending", "active"]),
            )
        )
        return result.scalar_one_or_none()

    async def find_all_for_workspace(self, workspace_id: uuid.UUID) -> list[WorkflowRun]:
        """Load all runs for a workspace (used by analytics service)."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == ctx.org_id,
                WorkflowRun.workspace_id == workspace_id,
            )
            .order_by(WorkflowRun.started_at.desc())
        )
        return list(result.scalars().all())


class WorkflowRunStepRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, step: WorkflowRunStep) -> WorkflowRunStep:
        self._session.add(step)
        await self._session.flush()
        await self._session.refresh(step)
        return step

    async def find_by_id(self, step_id: uuid.UUID) -> WorkflowRunStep | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRunStep).where(
                WorkflowRunStep.id == step_id,
                WorkflowRunStep.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, step_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(WorkflowRunStep)
            .where(
                WorkflowRunStep.id == step_id,
                WorkflowRunStep.tenant_id == ctx.org_id,
            )
            .values(**values)
        )

    async def find_by_run(self, run_id: uuid.UUID) -> list[WorkflowRunStep]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(WorkflowRunStep)
            .where(
                WorkflowRunStep.workflow_run_id == run_id,
                WorkflowRunStep.tenant_id == ctx.org_id,
            )
            .order_by(WorkflowRunStep.step_order.asc())
        )
        return list(result.scalars().all())
