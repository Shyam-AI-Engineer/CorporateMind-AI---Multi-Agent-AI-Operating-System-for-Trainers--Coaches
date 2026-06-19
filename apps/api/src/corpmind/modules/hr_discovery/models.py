"""HR discovery module models: companies and HR contacts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class Company(TenantBase):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_count_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HRContact(TenantBase):
    """Opted-in HR decision-maker contact.

    Contacts without complete opt-in evidence are non_contactable.
    email_deliverable is set to False on hard bounce (never retried).
    """

    __tablename__ = "hr_contacts"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_deliverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opt_in_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_contactable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ── WhatsApp channel fields (Sprint 16A / ADR-0010) ──────────────────────
    # E.164-normalised phone for WA dispatch (raw `phone` retained for display).
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    whatsapp_opt_in_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_deliverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    whatsapp_last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
