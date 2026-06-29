"""Proposals domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ProposalGenerated:
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalSent:
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalApproved:
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    approved_by: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalRejected:
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    rejected_by: uuid.UUID
    rejected_reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalDeliveryQueued:
    """Fired when deliver() queues an approved proposal for SMTP dispatch."""
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    outbound_message_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalDeliveryBlocked:
    """Fired when deliver() is called but ComplianceGuard blocks the send."""
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    outbound_message_id: uuid.UUID
    compliance_reason: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# Sprint 18A — client-response events

@dataclass(frozen=True)
class ProposalAccepted:
    """Fired when the client accepts the proposal and confirms the engagement."""
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    actual_value_inr: object  # Decimal at runtime; typed as object to avoid import
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ProposalDeclined:
    """Fired when the client declines the proposal."""
    proposal_id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    reason: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
