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
