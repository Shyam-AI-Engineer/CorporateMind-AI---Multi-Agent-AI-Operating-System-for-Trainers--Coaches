"""Integration Hub schemas — Sprint 55."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Supported webhook event types ────────────────────────────────────────────

SUPPORTED_WEBHOOK_EVENTS: frozenset[str] = frozenset({
    "customer.created",
    "customer.updated",
    "customer.deleted",
    "invoice.created",
    "invoice.paid",
    "invoice.overdue",
    "invoice.cancelled",
    "payment.received",
    "payment.failed",
    "training.session.started",
    "training.session.completed",
    "training.certificate.issued",
    "renewal.upcoming",
    "renewal.completed",
    "workflow.started",
    "workflow.completed",
    "workflow.failed",
    "api_key.revoked",
})

# ── API Key schemas ───────────────────────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    """Public view — key_hash is intentionally absent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned exactly once at key creation. Contains the plaintext key."""

    plain_key: str


class ApiKeyListOut(BaseModel):
    items: list[ApiKeyOut]
    total: int


# ── Webhook schemas ───────────────────────────────────────────────────────────


class WebhookCreate(BaseModel):
    workspace_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=2048)
    events: list[str] = Field(default_factory=list)


class WebhookUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=2048)
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookOut(BaseModel):
    """Public view — secret is intentionally absent from list/get."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    url: str
    events: list[str]
    is_active: bool
    last_delivery_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime


class WebhookCreatedOut(WebhookOut):
    """Returned exactly once at webhook creation. Contains the signing secret."""

    secret: str


class WebhookListOut(BaseModel):
    items: list[WebhookOut]
    total: int
