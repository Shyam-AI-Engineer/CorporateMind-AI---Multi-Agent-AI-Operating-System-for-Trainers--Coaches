"""Customer Success ORM model — Sprint 47."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class CustomerSuccess(TenantBase):
    __tablename__ = "customer_success"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True, unique=True
    )

    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="watch")
    health_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )

    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_contact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_followup_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    expansion_opportunity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    renewal_probability: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
