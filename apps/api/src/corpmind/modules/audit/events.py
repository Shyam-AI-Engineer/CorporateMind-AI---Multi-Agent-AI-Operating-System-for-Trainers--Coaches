"""Audit module domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AuditEventLogged:
    """Emitted after an audit log entry is successfully persisted."""

    log_id: uuid.UUID
    action: str
    module: str
    severity: str
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
