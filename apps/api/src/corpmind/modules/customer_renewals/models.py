"""Customer Renewal ORM model — Sprint 48."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class CustomerRenewal(TenantBase):
    __tablename__ = "customer_renewals"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    contract_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    renewal_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="annual"
    )
    renewal_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="planned"
    )
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    probability: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    expected_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
