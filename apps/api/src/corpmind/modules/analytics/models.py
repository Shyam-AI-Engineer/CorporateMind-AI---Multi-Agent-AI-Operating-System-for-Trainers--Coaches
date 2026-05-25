"""Analytics module models: daily rollup tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class AnalyticsDaily(TenantBase):
    """Pre-computed daily rollup per tenant per channel.

    Computed by Celery beat; never computed in request handlers.
    """

    __tablename__ = "analytics_daily"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rollup_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    outreach_sent: Mapped[int] = mapped_column(Integer, default=0)
    outreach_delivered: Mapped[int] = mapped_column(Integer, default=0)
    outreach_opened: Mapped[int] = mapped_column(Integer, default=0)
    outreach_replied: Mapped[int] = mapped_column(Integer, default=0)
    compliance_blocks: Mapped[int] = mapped_column(Integer, default=0)
    meetings_scheduled: Mapped[int] = mapped_column(Integer, default=0)
    meetings_completed: Mapped[int] = mapped_column(Integer, default=0)
    ai_spend_inr: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
