"""Compliance module models: audit events, unsubscribe list."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import Base, TenantBase


class AuditEvent(Base):
    """Append-only audit log for all compliance-relevant actions.

    NOT tenant-scoped via RLS — admin panel reads across tenants.
    Retention: 7 years (Enterprise), 2 years (others).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)  # user | agent | system
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recipient_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # HMAC, not raw
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)  # allowed | blocked
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnsubscribeEntry(TenantBase):
    """Cross-channel global unsubscribe list per tenant."""

    __tablename__ = "unsubscribe_list"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)  # None = all channels
    unsubscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
