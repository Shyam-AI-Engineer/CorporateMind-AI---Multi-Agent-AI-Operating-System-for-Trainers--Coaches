"""Operations module domain events — Sprint 29."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class BusinessTaskCreated:
    task_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    priority: str
    created_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class BusinessTaskStatusChanged:
    task_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    old_status: str
    new_status: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class BusinessTaskDeleted:
    task_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
