"""Campaign domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CampaignCreated:
    campaign_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CampaignLaunched:
    campaign_id: uuid.UUID
    tenant_id: uuid.UUID
    recipient_count: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CampaignPaused:
    campaign_id: uuid.UUID
    tenant_id: uuid.UUID
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CampaignRejected:
    campaign_id: uuid.UUID
    tenant_id: uuid.UUID
    rejected_by: str  # "hitl" | "compliance"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
