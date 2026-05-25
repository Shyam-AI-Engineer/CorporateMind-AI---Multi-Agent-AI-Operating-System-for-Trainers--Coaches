"""Outreach domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class MessageSent:
    message_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MessageBounced:
    message_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    bounce_type: str  # hard | soft | spam_complaint
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ReplyReceived:
    message_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    raw_reply_hash: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
