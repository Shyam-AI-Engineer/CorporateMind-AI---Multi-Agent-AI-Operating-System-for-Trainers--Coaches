"""WhatsApp module schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class WhatsAppTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    category: str
    body: str
    approval_status: str
    meta_template_id: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class WhatsAppTemplateListOut(BaseModel):
    items: list[WhatsAppTemplateOut]
    total: int


class WhatsAppSessionOut(BaseModel):
    contact_id: uuid.UUID
    window_expires_at: datetime
    is_active: bool
    model_config = {"from_attributes": True}


# ── Webhook inbound (delivery receipts, Sprint 16A) ───────────────────────────

class DeliveryReceiptStatus(BaseModel):
    """One status object from Meta webhook statuses array."""
    id: str
    status: str          # sent | delivered | read | failed
    timestamp: str
    recipient_id: str
    errors: list[dict] = []


class MetaWebhookChange(BaseModel):
    value: dict
    field: str


class MetaWebhookEntry(BaseModel):
    id: str
    changes: list[MetaWebhookChange]


class MetaWebhookPayload(BaseModel):
    object: str
    entry: list[MetaWebhookEntry]
