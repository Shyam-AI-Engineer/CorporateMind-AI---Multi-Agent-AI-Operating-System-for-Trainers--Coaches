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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
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
    # Sprint 14: provider_event_id from booking webhook that set meeting_scheduled_at.
    # NULL for manually-entered times via the UI.
    booking_provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    `status` lifecycle (Sprint 8B):
      pending ──claim──► processing ──┬─ done            (auto-sent)
                                      ├─ awaiting_approval (parked for HITL / 8C)
                                      └─ cancelled        (blocked / unresolvable)
      processing ──► pending          (quiet-hours deferral or stuck-row reaper)

    Idempotency: UNIQUE(tenant_id, source_inbox_message_id) protects against
    duplicate tasks for the same inbound reply even if the higher-level
    automation log is bypassed.  The cadence (Sprint 8B) adds send-time
    idempotency on top via the atomic claim (pending→processing) + a Redis lock.
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
    # Sprint 8B (expand migration b1d7c4e9f2a8): the outbound draft this follow-up
    # produced — set when the cadence generates+sends/parks.  Nullable: a task that
    # is cancelled before generation never has one.  Links the task to its message
    # for the Activity Timeline and forensic queries.
    result_outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    # Number of times the cadence has claimed this task.  Incremented on every
    # claim; a ceiling guards against a poison row looping forever (→ cancelled).
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BookingWebhookEvent(TenantBase):
    """Idempotency anchor for inbound booking webhook events (ADR-0009).

    UNIQUE(tenant_id, provider, provider_event_id) prevents double-processing
    of retried webhooks.  outcome vocabulary (app-controlled string):
      processing | applied | skipped | failed
    'applied' means the CRM lead was updated.
    'skipped' means the event arrived but no CRM action was taken
              (contact not found, no active lead, unrecognised event type).
    'failed'  means processing threw an unexpected error.
    """

    __tablename__ = "booking_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "provider_event_id",
            name="uq_booking_webhook_events_tenant_provider_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Provider name: calendly | cal_com | tidycal | savvycal | generic
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Event type from the booking tool: booking.created | booking.cancelled | booking.rescheduled
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    invitee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), default="processing", nullable=False)
    # Set to the matched CRM lead when outcome='applied'
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
