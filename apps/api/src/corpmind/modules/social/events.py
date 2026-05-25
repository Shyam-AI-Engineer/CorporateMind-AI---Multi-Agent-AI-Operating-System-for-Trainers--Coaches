"""Social domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class SocialPostPublished:
    post_id: uuid.UUID
    tenant_id: uuid.UUID
    channel: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
