"""Customer domain events — Sprint 41."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CustomerCreated:
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    company_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerUpdated:
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerArchived:
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerHealthChanged:
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    from_health: str
    to_health: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CustomerOwnerAssigned:
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    owner_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
