"""Customer Renewal domain events — Sprint 48."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class RenewalCreated:
    renewal_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    renewal_type: str
    renewal_status: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RenewalUpdated:
    renewal_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RenewalStatusChanged:
    renewal_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    previous_status: str
    new_status: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RenewalProposalAttached:
    renewal_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    proposal_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
