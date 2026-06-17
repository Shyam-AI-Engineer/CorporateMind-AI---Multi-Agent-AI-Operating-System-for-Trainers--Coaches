"""Analytics module models: daily rollup tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class AnalyticsDaily(TenantBase):
    """Pre-computed daily rollup per tenant per channel.

    Computed by Celery beat; never computed in request handlers.
    The unique constraint on (tenant_id, rollup_date, channel) enables
    ON CONFLICT DO UPDATE upserts so re-running the rollup is idempotent.
    """

    __tablename__ = "analytics_daily"
    __table_args__ = (
        # NULLS NOT DISTINCT so two channel=NULL rows conflict (Postgres 15+).
        # Defined via raw DDL in the migration; SQLAlchemy UniqueConstraint
        # is kept here for ORM introspection only — it does not regenerate DDL.
        UniqueConstraint(
            "tenant_id",
            "rollup_date",
            "channel",
            name="uq_analytics_daily_tenant_date_channel",
            info={"nulls_not_distinct": True},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rollup_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Outreach metrics
    outreach_sent: Mapped[int] = mapped_column(Integer, default=0)
    outreach_delivered: Mapped[int] = mapped_column(Integer, default=0)
    outreach_opened: Mapped[int] = mapped_column(Integer, default=0)
    outreach_replied: Mapped[int] = mapped_column(Integer, default=0)
    compliance_blocks: Mapped[int] = mapped_column(Integer, default=0)
    # CRM pipeline metrics
    meetings_scheduled: Mapped[int] = mapped_column(Integer, default=0)
    meetings_completed: Mapped[int] = mapped_column(Integer, default=0)
    leads_created: Mapped[int] = mapped_column(Integer, default=0)
    leads_booked: Mapped[int] = mapped_column(Integer, default=0)
    # Proposal funnel metrics
    proposals_generated: Mapped[int] = mapped_column(Integer, default=0)
    proposals_approved: Mapped[int] = mapped_column(Integer, default=0)
    proposals_sent: Mapped[int] = mapped_column(Integer, default=0)
    # Cost
    ai_spend_inr: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
