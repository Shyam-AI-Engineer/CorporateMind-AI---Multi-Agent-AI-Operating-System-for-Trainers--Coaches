"""Billing module models: subscriptions, usage metering, invoices."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class Subscription(TenantBase):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ai_run_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    outreach_send_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    ai_budget_inr: Mapped[float] = mapped_column(Float, default=400.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageMeter(TenantBase):
    """Running usage counter for the current billing period."""

    __tablename__ = "usage_meters"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    ai_runs_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outreach_sends_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_spend_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
