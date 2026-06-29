"""Notification center domain events — Sprint 32."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class NotificationCreated:
    notification_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    priority: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class NotificationRead:
    notification_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class NotificationDeleted:
    notification_id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AllNotificationsRead:
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    count_updated: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
