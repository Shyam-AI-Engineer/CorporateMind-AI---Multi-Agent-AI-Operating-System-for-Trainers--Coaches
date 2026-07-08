"""Organization administration models — Sprint 54: Organization Administration Center."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class OrganizationSettings(TenantBase):
    """One row per tenant — captures org-wide administrative configuration."""

    __tablename__ = "organization_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="My Organization"
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    date_format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DD/MM/YYYY"
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    default_workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    default_training_duration_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    default_invoice_due_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
