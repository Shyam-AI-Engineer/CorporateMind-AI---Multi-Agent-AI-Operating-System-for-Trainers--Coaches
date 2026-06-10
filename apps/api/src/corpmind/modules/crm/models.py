"""CRM module models: leads, activity log, follow-up tasks, automation log.

Sprint 4C added Activity, FollowUpTask, and InboxMessageAutomationLog to support
reply-driven automation.  All three are TenantBase + RLS-enabled.  Activity and
FollowUpTask are queryable by lead / contact / source inbox message.
InboxMessageAutomationLog is the idempotency anchor — a UNIQUE constraint on
(tenant_id, inbox_message_id) ensures the same reply is automated at most once.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class Lead(TenantBase):
    """CRM lead record for a contact in the pipeline."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(
        String(50), default="discovered", nullable=False, index=True
    )  # discovered | engaged | meeting_scheduled | meeting_completed | booked | lost
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Activity(TenantBase):
    """Append-only CRM activity log row.

    One row per automated action driven by the inbox automation pipeline.
    `lead_id` is nullable because some activities are tied to a contact but
    have no live lead (e.g. bounce on a contact that no campaign ever
    targeted, automation_failed when the lead lookup itself missed).
    `type` vocabulary is application-controlled — see
    ReplyAutomationService for the allowlist.
    """

    __tablename__ = "crm_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_inbox_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    source_outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FollowUpTask(TenantBase):
    """A follow-up action queued by the reply automation pipeline.

    Schedule semantics:
      - scheduled_for IS NULL ⇒ "do as soon as possible" (used for `question`)
      - scheduled_for in the future ⇒ scheduled reminder (used for `out_of_office`)

    `status` lifecycle: pending → done | cancelled.  No scheduler wiring this
    sprint; a future sprint consumes these rows.

    Idempotency: UNIQUE(tenant_id, source_inbox_message_id) protects against
    duplicate tasks for the same inbound reply even if the higher-level
    automation log is bypassed.
    """

    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_inbox_message_id",
            name="uq_follow_up_tasks_tenant_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source_inbox_message_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    source_outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InboxMessageAutomationLog(TenantBase):
    """Single-row marker that an inbox message has had automation applied.

    The primary idempotency anchor for reply automation.  Insert with
    ON CONFLICT DO NOTHING — if the row already exists, the automation
    short-circuits and emits no further events.  Survives inbox_message
    deletion (no FK) so replays don't double-fire after cleanup jobs.
    """

    __tablename__ = "inbox_message_automation_log"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "inbox_message_id",
            name="uq_inbox_message_automation_log_tenant_msg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inbox_message_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # applied | failed | skipped
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
