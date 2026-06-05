"""Inbox module models: connected Gmail accounts and synced inbound messages.

Phase 1 scope: Gmail OAuth connections and reply tracking via Message-ID matching.
Gmail API client, sync worker, and API endpoints are implemented in later phases.

Encryption:
    email_address_enc, refresh_token_enc, access_token_enc, body_snippet_enc
    are stored as AES-256-GCM ciphertext (base64url) via corpmind.core.encryption.
    All encrypt/decrypt calls happen in the service layer — never at model level.

Deduplication:
    InboxConnection.email_address_hash  — HMAC-SHA256(email, tenant_id.bytes)
    InboxMessage uniqueness             — (connection_id, provider_message_id)
    Both follow the same pattern as unsubscribe_list.contact_hash.

RLS:
    Both tables are TenantBase — tenant_id is auto-added as the first column.
    ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY applied in migration.
    Policy uses the hardened NULLIF predicate (same as all tables post-b9f4e7d2a1c8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class InboxConnection(TenantBase):
    """A Gmail inbox connected by a trainer for inbound reply tracking.

    OAuth credentials (refresh_token, access_token) and the plain email address
    are stored AES-256-GCM encrypted at column level.  Only email_address_hash
    (HMAC-SHA256 keyed by tenant_id.bytes) is stored in plaintext — used for
    dedup checks and lookup without requiring decryption.

    Unique constraint enforced at DB level:
        uq_inbox_connections_tenant_email_hash  on (tenant_id, email_address_hash)
    Prevents a trainer from connecting the same Gmail account twice per tenant.

    provider field supports future expansion to Outlook, Yahoo, etc.
    Phase 1: "gmail" only.
    """

    __tablename__ = "inbox_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # "gmail" for Phase 1; "outlook" | "yahoo" for future phases.
    provider: Mapped[str] = mapped_column(String(30), default="gmail", nullable=False)

    # ── Encrypted credentials ─────────────────────────────────────────────────
    # Stored as AES-256-GCM base64url ciphertext (corpmind.core.encryption).
    # Service layer calls encrypt() on write, decrypt() on read.
    email_address_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable — access token can be re-derived from refresh_token at sync time.
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Lookup hash ───────────────────────────────────────────────────────────
    # HMAC-SHA256(plaintext_email, tenant_id.bytes).hexdigest() — 64 hex chars.
    # Follows the same pattern as unsubscribe_list.contact_hash.
    # Enables unique-connection enforcement and existence checks without decryption.
    email_address_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # ── OAuth metadata ────────────────────────────────────────────────────────
    # Space-separated OAuth scopes granted at connection time.
    # e.g. "https://www.googleapis.com/auth/gmail.readonly"
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Sync state ────────────────────────────────────────────────────────────
    # active | needs_reauth | revoked | error
    status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False, index=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last provider error message — cleared on successful sync.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    connected_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InboxMessage(TenantBase):
    """A single inbound email synced from a connected Gmail inbox.

    Thread matching:
        smtp_message_id is extracted from the In-Reply-To / References headers of
        the inbound email and compared against outbound_messages.smtp_message_id.
        When a match is found, outbound_message_id is populated and match_method
        records how the match was established.

    Body storage:
        body_snippet_enc holds the first ~500 characters, AES-256-GCM encrypted.
        body_truncated=True signals that the full body was not stored (Phase 2
        will add an inbox_message_bodies table for full-body storage).

    Unique constraint enforced at DB level:
        uq_inbox_messages_connection_provider_message
        on (connection_id, provider_message_id)
    Prevents duplicate rows if a sync job runs twice for the same Gmail message.
    """

    __tablename__ = "inbox_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inbox_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Provider identifiers ──────────────────────────────────────────────────
    # Gmail message ID (e.g. "17a3b4c5d6e7f890") — opaque string from Gmail API.
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Gmail thread ID — enables thread-level reply grouping.
    provider_thread_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # ── Thread matching ───────────────────────────────────────────────────────
    # Extracted from In-Reply-To or References headers; compared against
    # outbound_messages.smtp_message_id to identify which outbound we sent.
    smtp_message_id: Mapped[str | None] = mapped_column(
        String(512), nullable=True, index=True
    )
    # Raw In-Reply-To header value (single Message-ID, RFC 2822).
    in_reply_to: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Raw References header value (space-separated list of Message-IDs, RFC 2822).
    # Named references_header to avoid the PostgreSQL reserved keyword.
    references_header: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set after matching; SET NULL preserves inbox record if outbound is deleted.
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # How the outbound match was established:
    # "message_id" | "in_reply_to" | "thread_id" | "subject" | null (unmatched)
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Email headers ─────────────────────────────────────────────────────────
    # from_address stored in plaintext — sender identity is used for display and
    # reply-intent classification; it is the counterparty's address, not our
    # contacts' PII.  Matches the existing pattern for contact_email in audit logs
    # (hashed there; here it is the sender of an inbound, not a recipient).
    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # ── Encrypted body snippet ────────────────────────────────────────────────
    # AES-256-GCM encrypted first ~500 chars of plain-text body.
    # Text (unbounded) — ciphertext for 500 chars of input is ~700 base64 chars;
    # no String(N) bound to avoid silent truncation of the ciphertext.
    body_snippet_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when the full body exceeds the 500-char snippet limit.
    body_truncated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Classification ────────────────────────────────────────────────────────
    # Populated by ReplyClassifierAgent (Phase 2).
    # interested | not_interested | question | out_of_office | auto_reply | unknown
    reply_intent: Mapped[str | None] = mapped_column(String(50), nullable=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
