"""CRM domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class LeadStageChanged:
    lead_id: uuid.UUID
    tenant_id: uuid.UUID
    from_stage: str
    to_stage: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MeetingBooked:
    lead_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Reply-driven automation events (Sprint 4C) ────────────────────────────────
# These are emitted by ReplyAutomationService after a ReplyClassified event is
# consumed.  Sprint 4D+ can consume them for notifications, analytics, etc.
# All carry the source_inbox_message_id so consumers can correlate back to the
# original reply.


@dataclass(frozen=True)
class LeadEngaged:
    """Emitted when an `interested` reply advanced a lead to engaged
    (or when the lead was already engaged-or-past and we logged a no-op)."""

    lead_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    source_inbox_message_id: uuid.UUID
    # advanced | already_engaged_or_later
    transition: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class LeadCold:
    """Emitted when a `not_interested` reply marked a lead lost.

    Naming asymmetry: the underlying DB transition is to `lost` (terminal),
    but the spec calls this "cold" in the business vocabulary.  Consumers
    receive both LeadCold (semantic) and LeadStageChanged (transition).
    """

    lead_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    source_inbox_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FollowUpRequired:
    """Emitted for `question` intent — caller wants information now."""

    follow_up_task_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    lead_id: uuid.UUID | None
    source_inbox_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class FollowUpScheduled:
    """Emitted for `out_of_office` intent — follow-up deferred to scheduled_for."""

    follow_up_task_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    lead_id: uuid.UUID | None
    scheduled_for: datetime
    source_inbox_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ContactBounced:
    """Emitted when a `bounce` reply flipped HRContact.email_deliverable=False."""

    contact_id: uuid.UUID
    tenant_id: uuid.UUID
    source_inbox_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ContactUnsubscribed:
    """Emitted when an `unsubscribe` intent cleared the channel opt-in.

    `channel` identifies which opt-in was revoked (e.g. "whatsapp").  Email
    unsubscribes use the existing unsubscribe_list table and a separate path.
    """

    contact_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    source_inbox_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class BookingWebhookReceived:
    """Emitted when a booking webhook payload passes HMAC verification.

    Fired before contact matching — even skipped events emit this so dashboards
    can track raw inbound webhook volume vs. applied rate.
    """

    workspace_id: uuid.UUID
    tenant_id: uuid.UUID
    provider: str
    provider_event_id: str
    event_type: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MeetingAutoScheduled:
    """Emitted when a booking webhook successfully sets meeting_scheduled_at on a lead."""

    lead_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    scheduled_at: datetime | None
    provider: str
    provider_event_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AutomationFailed:
    """Emitted when a validation gate prevented any CRM mutation.

    `reason` vocabulary (controlled application-side):
      no_outbound_match | contact_not_found | lead_not_found |
      tenant_mismatch | internal_error
    """

    inbox_message_id: uuid.UUID
    tenant_id: uuid.UUID
    intent: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
