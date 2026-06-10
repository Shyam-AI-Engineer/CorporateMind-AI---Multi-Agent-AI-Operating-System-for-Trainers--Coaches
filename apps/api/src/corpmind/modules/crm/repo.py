"""CRM repository — LeadRepo + ActivityRepo + FollowUpTaskRepo + AutomationLogRepo."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.models import (
    Activity,
    FollowUpTask,
    InboxMessageAutomationLog,
    Lead,
)

log = structlog.get_logger(__name__)


class LeadRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, lead: Lead) -> Lead:
        self._session.add(lead)
        await self._session.flush()
        log.info("crm.lead_row_created", lead_id=str(lead.id))
        return lead

    async def find_by_id(self, lead_id: uuid.UUID) -> Lead | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead).where(
                Lead.id == lead_id,
                Lead.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_active_by_contact(
        self, contact_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Lead | None:
        """Return the most recent non-terminal lead for this contact in this workspace."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.workspace_id == workspace_id,
                Lead.tenant_id == ctx.org_id,
                Lead.stage.not_in(("booked", "lost")),
            )
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_active_by_contact_any_workspace(
        self, contact_id: uuid.UUID
    ) -> Lead | None:
        """Return the most recent non-terminal lead for this contact in this tenant.

        Used by ReplyAutomationService when only the outbound→contact mapping is
        known and the originating campaign (and therefore workspace) cannot be
        resolved.  RLS + tenant_id filter keep this safely tenant-scoped.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead)
            .where(
                Lead.contact_id == contact_id,
                Lead.tenant_id == ctx.org_id,
                Lead.stage.not_in(("booked", "lost")),
            )
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_pipeline(
        self,
        workspace_id: uuid.UUID,
        *,
        stage: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        ctx = get_tenant_context()
        stmt = select(Lead).where(
            Lead.workspace_id == workspace_id,
            Lead.tenant_id == ctx.org_id,
        )
        if stage:
            stmt = stmt.where(Lead.stage == stage)
        stmt = stmt.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_stage(self, workspace_id: uuid.UUID) -> dict[str, int]:
        """Return a mapping of stage → count for all leads in a workspace."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Lead.stage, func.count().label("cnt"))
            .where(Lead.workspace_id == workspace_id, Lead.tenant_id == ctx.org_id)
            .group_by(Lead.stage)
        )
        return {row[0]: row[1] for row in result}

    async def count_pipeline(
        self, workspace_id: uuid.UUID, *, stage: str | None = None
    ) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(Lead)
            .where(Lead.workspace_id == workspace_id, Lead.tenant_id == ctx.org_id)
        )
        if stage:
            stmt = stmt.where(Lead.stage == stage)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update_fields(self, lead_id: uuid.UUID, **values: object) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(Lead)
            .where(Lead.id == lead_id, Lead.tenant_id == ctx.org_id)
            .values(**values)
        )


# ── ActivityRepo (Sprint 4C) ──────────────────────────────────────────────────

class ActivityRepo:
    """Append-only activity log used by ReplyAutomationService."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, activity: Activity) -> Activity:
        self._session.add(activity)
        await self._session.flush()
        return activity

    async def list_for_lead(
        self, lead_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Activity]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Activity)
            .where(Activity.lead_id == lead_id, Activity.tenant_id == ctx.org_id)
            .order_by(Activity.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_inbox_message(
        self, inbox_message_id: uuid.UUID
    ) -> Activity | None:
        """Used by idempotency assertions and integration tests."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(Activity).where(
                Activity.source_inbox_message_id == inbox_message_id,
                Activity.tenant_id == ctx.org_id,
            )
        )
        return result.scalars().first()

    async def list_filtered(
        self,
        *,
        workspace_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Activity]:
        """Paginated activity list, ordered by created_at DESC.

        At least one of workspace_id / lead_id / contact_id is expected to be
        set in normal use; the route layer enforces that requirement so the
        repository stays free of routing concerns.
        """
        ctx = get_tenant_context()
        stmt = select(Activity).where(Activity.tenant_id == ctx.org_id)
        if workspace_id is not None:
            stmt = stmt.where(Activity.workspace_id == workspace_id)
        if lead_id is not None:
            stmt = stmt.where(Activity.lead_id == lead_id)
        if contact_id is not None:
            stmt = stmt.where(Activity.contact_id == contact_id)
        stmt = stmt.order_by(Activity.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        workspace_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
    ) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(Activity)
            .where(Activity.tenant_id == ctx.org_id)
        )
        if workspace_id is not None:
            stmt = stmt.where(Activity.workspace_id == workspace_id)
        if lead_id is not None:
            stmt = stmt.where(Activity.lead_id == lead_id)
        if contact_id is not None:
            stmt = stmt.where(Activity.contact_id == contact_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()


# ── FollowUpTaskRepo (Sprint 4C) ──────────────────────────────────────────────

class FollowUpTaskRepo:
    """Repository for FollowUpTask rows produced by reply automation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, task: FollowUpTask) -> FollowUpTask:
        self._session.add(task)
        await self._session.flush()
        return task

    async def find_by_inbox_message(
        self, inbox_message_id: uuid.UUID
    ) -> FollowUpTask | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(FollowUpTask).where(
                FollowUpTask.source_inbox_message_id == inbox_message_id,
                FollowUpTask.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        workspace_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FollowUpTask]:
        """Paginated follow-up list per workspace.

        Sort order: scheduled_for ASC NULLS FIRST so "do asap" items (NULL)
        appear before timed reminders.  Within same bucket, oldest created
        comes first — a fair queue for follow-up workers.
        """
        ctx = get_tenant_context()
        stmt = select(FollowUpTask).where(
            FollowUpTask.tenant_id == ctx.org_id,
            FollowUpTask.workspace_id == workspace_id,
        )
        if status is not None:
            stmt = stmt.where(FollowUpTask.status == status)
        stmt = stmt.order_by(
            FollowUpTask.scheduled_for.asc().nullsfirst(),
            FollowUpTask.created_at.asc(),
        ).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        workspace_id: uuid.UUID,
        status: str | None = None,
    ) -> int:
        ctx = get_tenant_context()
        stmt = (
            select(func.count())
            .select_from(FollowUpTask)
            .where(
                FollowUpTask.tenant_id == ctx.org_id,
                FollowUpTask.workspace_id == workspace_id,
            )
        )
        if status is not None:
            stmt = stmt.where(FollowUpTask.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()


# ── AutomationLogRepo (Sprint 4C) ─────────────────────────────────────────────

class AutomationLogRepo:
    """Idempotency anchor — UNIQUE(tenant_id, inbox_message_id) guards every
    reply-driven automation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        inbox_message_id: uuid.UUID,
        intent: str,
        outcome: str,
        reason: str | None = None,
    ) -> bool:
        """Atomically claim this inbox_message_id for automation.

        Returns True when the row was inserted (first time seeing this message).
        Returns False when ON CONFLICT DO NOTHING fired (already processed).

        Inserts with the FINAL outcome (applied/failed/skipped) — there is no
        update path.  This guarantees that a crashing worker mid-automation
        leaves an "applied" row that prevents replay (the per-table UNIQUE
        constraints downstream catch the rare partial-write case).
        """
        ctx = get_tenant_context()
        stmt = (
            pg_insert(InboxMessageAutomationLog)
            .values(
                id=uuid.uuid4(),
                tenant_id=ctx.org_id,
                inbox_message_id=inbox_message_id,
                outcome=outcome,
                intent=intent,
                reason=reason,
            )
            .on_conflict_do_nothing(
                constraint="uq_inbox_message_automation_log_tenant_msg"
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[union-attr]

    async def find_by_inbox_message(
        self, inbox_message_id: uuid.UUID
    ) -> InboxMessageAutomationLog | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(InboxMessageAutomationLog).where(
                InboxMessageAutomationLog.inbox_message_id == inbox_message_id,
                InboxMessageAutomationLog.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()
