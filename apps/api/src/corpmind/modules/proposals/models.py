"""Proposals module models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class Proposal(TenantBase):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    cloudinary_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Sprint 12A — approval workflow (expand step; see migration c2e8f5a4d9b7)
    approval_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_approval",         # Python-side default for in-memory objects
        server_default="pending_approval",  # DB-side default for SQL INSERT / backfill
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sprint 12B — delivery tracking (expand step; see migration e4a9b2c7f1d6)
    # NULL  = delivery not yet initiated.
    # Set   = deliver() was called; see outbound_messages.status for execution state.
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )

    # Sprint 18A — revenue attribution (expand step; see migration b4d8e3f1a9c7)
    # lead_id closes the Proposal → Lead → Campaign attribution gap.
    # client_status is an independent state dimension from status (delivery) and
    # approval_status (internal workflow).  NULL = no client response yet.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    expected_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    client_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    client_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
