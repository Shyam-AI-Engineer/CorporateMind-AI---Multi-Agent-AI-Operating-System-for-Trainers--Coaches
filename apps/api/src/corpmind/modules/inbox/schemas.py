"""Inbox module Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InboxConnectionCreate(BaseModel):
    """Input DTO — what the OAuth handler passes to the service layer before encryption.

    The service is responsible for:
      - AES-256-GCM encrypting email_address  → email_address_enc
      - AES-256-GCM encrypting refresh_token  → refresh_token_enc
      - AES-256-GCM encrypting access_token   → access_token_enc (when present)
      - HMAC-SHA256(email_address, tenant_id.bytes) → email_address_hash
    The repo receives an InboxConnection ORM object with the encrypted values;
    it never sees plaintext credentials.
    """

    workspace_id: uuid.UUID
    provider: str = Field(default="gmail", pattern=r"^(gmail|outlook|yahoo)$")
    email_address: str = Field(max_length=320)
    refresh_token: str
    access_token: str | None = None
    scopes: str
    token_expiry_at: datetime | None = None
    connected_by: uuid.UUID


class InboxConnectionOut(BaseModel):
    """Output DTO returned to API callers.

    email_address is the decrypted value — the service decrypts before constructing
    this DTO.  No token fields are exposed; access/refresh tokens stay server-side.
    Constructed manually by the service (no from_attributes) because the ORM model
    stores email_address_enc, not email_address.
    """

    id: uuid.UUID
    workspace_id: uuid.UUID
    provider: str
    email_address: str
    scopes: str
    token_expiry_at: datetime | None
    status: str
    last_sync_at: datetime | None
    last_error: str | None
    connected_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ConnectionHealthOut(BaseModel):
    """Result of a connection health check.

    healthy=True means the refresh token is valid and Gmail API access was confirmed.
    reason is populated only when healthy=False; it describes the failure category.
    status mirrors the value persisted to InboxConnection.status so callers can
    update their UI without issuing a follow-up GET /connection.
    """

    healthy: bool
    reason: str | None = None
    status: str


class InboxMessageOut(BaseModel):
    """Output DTO for a single synced inbound message.

    body_snippet is the decrypted value — the service decrypts body_snippet_enc
    before constructing this DTO.  Constructed manually by the service (no
    from_attributes) because the ORM column is body_snippet_enc, not body_snippet.
    """

    id: uuid.UUID
    connection_id: uuid.UUID
    provider_message_id: str
    provider_thread_id: str | None
    smtp_message_id: str | None
    in_reply_to: str | None
    outbound_message_id: uuid.UUID | None
    match_method: str | None
    from_address: str
    subject: str | None
    received_at: datetime
    body_snippet: str | None
    body_truncated: bool
    reply_intent: str | None
    # Classification metadata populated by ReplyClassifierAgent (Sprint 4B).
    # NULL when the message has not been classified (older rows + worker errors).
    confidence: float | None = None
    classified_at: datetime | None = None
    classification_model: str | None = None
    synced_at: datetime


# ── Read-only list DTOs (Sprint 5 prerequisite layer) ─────────────────────────

class InboxConnectionListOut(BaseModel):
    """Paginated list of inbox connections for a workspace."""

    items: list[InboxConnectionOut]
    total: int
    limit: int
    offset: int


class InboxMessageListOut(BaseModel):
    """Paginated list of inbox messages.

    Returned by GET /api/v1/inbox/messages.  Body snippets are decrypted in the
    service before serialization, mirroring the single-message GET behaviour.
    """

    items: list[InboxMessageOut]
    total: int
    limit: int
    offset: int
