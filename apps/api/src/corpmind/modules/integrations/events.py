"""Integration Hub domain events — Sprint 55."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ApiKeyCreated:
    key_id: uuid.UUID
    workspace_id: uuid.UUID
    key_prefix: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ApiKeyRevoked:
    key_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WebhookCreated:
    webhook_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WebhookUpdated:
    webhook_id: uuid.UUID
    workspace_id: uuid.UUID
    updated_fields: list[str]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WebhookDeleted:
    webhook_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
