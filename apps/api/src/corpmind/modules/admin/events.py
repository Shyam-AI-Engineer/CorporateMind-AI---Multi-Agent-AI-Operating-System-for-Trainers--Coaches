"""Admin module domain events — Sprint 54."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class OrganizationSettingsUpdated:
    org_id: uuid.UUID
    updated_fields: list[str]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OrganizationSettingsCreated:
    org_id: uuid.UUID
    organization_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
