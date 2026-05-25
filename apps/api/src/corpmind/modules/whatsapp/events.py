"""WhatsApp domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class WhatsAppWindowOpened:
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    expires_at: datetime
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class WhatsAppTemplateRejected:
    tenant_id: uuid.UUID
    template_id: uuid.UUID
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
