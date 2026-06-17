"""CRM repository — LeadRepo + ActivityRepo + FollowUpTaskRepo + AutomationLogRepo."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.crm.models import (
    Activity,
    BookingWebhookEvent,
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

    async def find_by_id(self, task_id: uuid.UUID) -> FollowUpTask | None:
        """Tenant-scoped fetch by primary key — used by the 8C approval surface."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(FollowUpTask).where(
                FollowUpTask.id == task_id,
                FollowUpTask.tenant_id == ctx.org_id,
            )
        )
        return result.scalar_one_or_none()

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

    # ── Cadence support (Sprint 8B — ADR-0008) ────────────────────────────────

    async def list_due(self, *, limit: int = 50) -> list[FollowUpTask]:
        """Pending tasks whose schedule has arrived, oldest-first.

        Due = status='pending' AND (scheduled_for IS NULL OR scheduled_for <= now()).
        NULL scheduled_for means "do-asap" (question follow-ups) and sorts first.
        RLS + the explicit tenant filter keep this scoped to the caller's tenant —
        the cadence runs this inside a per-tenant subtask that has already called
        set_rls_tenant().  `now()` is evaluated DB-side for clock consistency.
        """
        ctx = get_tenant_context()
        stmt = (
            select(FollowUpTask)
            .where(
                FollowUpTask.tenant_id == ctx.org_id,
                FollowUpTask.status == "pending",
                (FollowUpTask.scheduled_for.is_(None))
                | (FollowUpTask.scheduled_for <= func.now()),
            )
            .order_by(
                FollowUpTask.scheduled_for.asc().nullsfirst(),
                FollowUpTask.created_at.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def claim(self, task_id: uuid.UUID) -> bool:
        """Atomically transition pending→processing for exactly one worker.

        Returns True only for the worker whose guarded UPDATE matched the row
        while it was still 'pending'.  Concurrent callers see zero affected rows
        and get False — this is the authoritative double-processing guard
        (ADR-0008 §8).  Increments `attempts` so a poison row can be retired.
        Must run inside the RLS-scoped transaction (SET LOCAL is txn-bound).
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            update(FollowUpTask)
            .where(
                FollowUpTask.id == task_id,
                FollowUpTask.tenant_id == ctx.org_id,
                FollowUpTask.status == "pending",
            )
            .values(status="processing", attempts=FollowUpTask.attempts + 1)
            .returning(FollowUpTask.id)
        )
        return result.first() is not None

    async def mark_done(
        self, task_id: uuid.UUID, *, result_outbound_message_id: uuid.UUID
    ) -> None:
        """Terminal: the follow-up was generated and sent (auto path)."""
        await self._set_terminal(
            task_id,
            status="done",
            result_outbound_message_id=result_outbound_message_id,
        )

    async def mark_awaiting_approval(
        self, task_id: uuid.UUID, *, result_outbound_message_id: uuid.UUID
    ) -> None:
        """Park: draft generated, held for human approval (HITL / Sprint 8C)."""
        await self._set_terminal(
            task_id,
            status="awaiting_approval",
            result_outbound_message_id=result_outbound_message_id,
        )

    async def mark_cancelled(self, task_id: uuid.UUID, *, reason: str) -> None:
        """Terminal: blocked by compliance, unresolvable, or retries exhausted.

        Appends the reason to notes (preserving the original) so the timeline /
        forensic queries explain why nothing was sent.
        """
        ctx = get_tenant_context()
        await self._session.execute(
            update(FollowUpTask)
            .where(FollowUpTask.id == task_id, FollowUpTask.tenant_id == ctx.org_id)
            .values(
                status="cancelled",
                notes=func.concat(
                    func.coalesce(FollowUpTask.notes, ""),
                    f" | Auto-cancelled: {reason}",
                ),
            )
        )

    async def defer(self, task_id: uuid.UUID, *, scheduled_for: datetime) -> None:
        """Return a claimed task to the queue with a future schedule.

        Used by the quiet-hours gate: the row was claimed (processing) but the
        recipient-local time is outside the send window, so we release it back to
        'pending' with scheduled_for set to the next in-window moment.  No LLM
        spend occurred.  Only affects rows still in 'processing'.
        """
        ctx = get_tenant_context()
        await self._session.execute(
            update(FollowUpTask)
            .where(
                FollowUpTask.id == task_id,
                FollowUpTask.tenant_id == ctx.org_id,
                FollowUpTask.status == "processing",
            )
            .values(status="pending", scheduled_for=scheduled_for)
        )

    async def reset_stuck_processing(self, *, older_than: datetime) -> int:
        """Reaper: return long-stuck 'processing' rows to 'pending'.

        A worker that crashed after claim but before a terminal transition leaves
        a row in 'processing'.  Any row last touched before `older_than` (caller
        passes now - time_limit) is reclaimable.  Returns the number reset.
        Idempotent: a still-alive worker's row that gets reset will simply be
        re-claimed (the claim is atomic), so the reaper threshold ≥ task time_limit.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            update(FollowUpTask)
            .where(
                FollowUpTask.tenant_id == ctx.org_id,
                FollowUpTask.status == "processing",
                FollowUpTask.updated_at < older_than,
            )
            .values(status="pending")
        )
        return result.rowcount  # type: ignore[union-attr]

    async def _set_terminal(
        self,
        task_id: uuid.UUID,
        *,
        status: str,
        result_outbound_message_id: uuid.UUID,
    ) -> None:
        ctx = get_tenant_context()
        await self._session.execute(
            update(FollowUpTask)
            .where(FollowUpTask.id == task_id, FollowUpTask.tenant_id == ctx.org_id)
            .values(
                status=status,
                result_outbound_message_id=result_outbound_message_id,
            )
        )


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


# ── BookingWebhookEventRepo (Sprint 14 — ADR-0009) ───────────────────────────

class BookingWebhookEventRepo:
    """Idempotency anchor for inbound booking webhook events.

    UNIQUE(tenant_id, provider, provider_event_id) prevents double-processing
    when a booking tool retries a webhook.  The reserve() call is the exclusive
    gate: only the first caller for a given (provider, event_id) pair gets True.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        provider: str,
        provider_event_id: str,
        event_type: str,
        invitee_email: str,
        scheduled_at: datetime | None,
        raw_payload: dict,  # type: ignore[type-arg]
    ) -> uuid.UUID | None:
        """Atomically claim this (provider, provider_event_id) for processing.

        Returns the new event row's UUID when inserted for the first time.
        Returns None when ON CONFLICT DO NOTHING fired (already processed).
        Initial outcome is 'processing'; caller updates via mark_outcome().
        """
        event_id = uuid.uuid4()
        stmt = (
            pg_insert(BookingWebhookEvent)
            .values(
                id=event_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                provider=provider,
                provider_event_id=provider_event_id,
                event_type=event_type,
                invitee_email=invitee_email.lower(),
                scheduled_at=scheduled_at,
                raw_payload=raw_payload,
                outcome="processing",
            )
            .on_conflict_do_nothing(
                constraint="uq_booking_webhook_events_tenant_provider_event"
            )
        )
        result = await self._session.execute(stmt)
        return event_id if result.rowcount > 0 else None  # type: ignore[union-attr]

    async def mark_outcome(
        self,
        event_id: uuid.UUID,
        *,
        outcome: str,
        lead_id: uuid.UUID | None = None,
    ) -> None:
        """Update the event row with the processing outcome and optional matched lead."""
        from datetime import UTC

        values: dict[str, object] = {
            "outcome": outcome,
            "processed_at": datetime.now(UTC),
        }
        if lead_id is not None:
            values["lead_id"] = lead_id
        await self._session.execute(
            update(BookingWebhookEvent)
            .where(BookingWebhookEvent.id == event_id)
            .values(**values)
        )

    async def find_by_provider_event(
        self, *, tenant_id: uuid.UUID, provider: str, provider_event_id: str
    ) -> BookingWebhookEvent | None:
        result = await self._session.execute(
            select(BookingWebhookEvent).where(
                BookingWebhookEvent.tenant_id == tenant_id,
                BookingWebhookEvent.provider == provider,
                BookingWebhookEvent.provider_event_id == provider_event_id,
            )
        )
        return result.scalar_one_or_none()
