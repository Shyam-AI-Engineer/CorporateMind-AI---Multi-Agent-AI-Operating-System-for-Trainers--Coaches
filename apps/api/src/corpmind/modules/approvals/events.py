"""Approval workflow domain events — Sprint 31."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ApprovalRequestCreated:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    requested_by: str
    priority: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ApprovalAssigned:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    assigned_reviewer: str
    assigned_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ApprovalApproved:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewed_by: str
    comments: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ApprovalRejected:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewed_by: str
    comments: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ApprovalCancelled:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    cancelled_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
