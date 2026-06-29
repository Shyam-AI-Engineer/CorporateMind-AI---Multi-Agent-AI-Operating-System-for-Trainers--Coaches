"""Analytics module models: daily rollup + Sprint 19 intelligence summary tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
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
    # Sprint 18A — revenue metrics
    proposals_accepted: Mapped[int] = mapped_column(Integer, default=0)
    closed_revenue_inr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalyticsCampaignSummary(TenantBase):
    """Pre-computed campaign ROI snapshot — one row per campaign.

    Refreshed daily by compute_campaign_summary Celery beat task.
    Uses ON CONFLICT DO UPDATE so re-runs are idempotent.
    All-touch attribution: revenue from contacts in multiple campaigns
    is counted under each campaign (documented in API response).
    avg_days_to_accept = AVG(client_accepted_at - sent_at) in days (Sprint 19 Amendment 1).
    """

    __tablename__ = "analytics_campaign_summary"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "campaign_id",
            name="uq_analytics_campaign_summary_tenant_campaign",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    campaign_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Reach
    recipients_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_delivered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replies_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Pipeline
    leads_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Revenue
    closed_revenue_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    avg_deal_size_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, nullable=False)
    avg_days_to_accept: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalyticsTrainerSummary(TenantBase):
    """Per-workspace daily time-series — one row per (workspace_id, rollup_date).

    Refreshed daily by compute_trainer_summary Celery beat task.
    Stores daily deltas (same philosophy as analytics_daily).
    Win rate is NOT stored — computed at service layer from period sums
    to avoid misleading per-day rates on sparse data.
    avg_days_to_accept = AVG(client_accepted_at - sent_at) in days for
    proposals accepted on rollup_date (Sprint 19 Amendment 1).
    """

    __tablename__ = "analytics_trainer_summary"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "rollup_date",
            name="uq_analytics_trainer_summary_tenant_ws_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    rollup_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    niche: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proposals_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_revenue_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    avg_deal_size_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pipeline_value_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    avg_days_to_accept: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Sprint 21 — Recommendation Tracking ──────────────────────────────────────


class RecommendationSnapshot(TenantBase):
    """State snapshot of a single recommendation at generation time.

    Written by AnalyticsService.get_recommendations() on every cache miss.
    ON CONFLICT DO UPDATE on (tenant_id, workspace_id, rec_type, snapshot_date)
    makes re-runs idempotent.

    confidence_score / confidence_level are frozen at generation time so that
    confidence calibration can compare predicted vs. observed outcome months later,
    even if the scoring formula has since changed.
    """

    __tablename__ = "recommendation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "rec_type",
            "snapshot_date",
            name="uq_rec_snapshot_tenant_ws_type_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rec_type: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(10), default="low", nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    supporting_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecommendationFeedback(TenantBase):
    """Explicit trainer feedback on a recommendation snapshot.

    One row per (tenant_id, workspace_id, snapshot_id); ON CONFLICT DO UPDATE
    so trainers can change their mind within the same snapshot period.

    outcome values: helpful | not_helpful | dismissed
    notes: optional free-text, scrubbed via Presidio at the service layer.
    """

    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "snapshot_id",
            name="uq_rec_feedback_tenant_ws_snapshot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    rec_type: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecommendationOutcome(TenantBase):
    """Inferred acted / success flags for a recommendation snapshot.

    Populated daily by the compute_recommendation_outcomes Celery beat task.
    acted: True if the trainer launched a campaign/proposal matching the
           recommendation's direction within 30 days of snapshot_date.
    success: True/False set 60 days after acted; None until then.
    outcome_delta: the measured metric improvement (e.g. delta win_rate).
    Sprint 21: acted detection is implemented for channel and campaign types.
               industry / topic / pricing outcome detection is deferred to Sprint 22.
    """

    __tablename__ = "recommendation_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "snapshot_id",
            name="uq_rec_outcome_tenant_ws_snapshot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    rec_type: Mapped[str] = mapped_column(String(30), nullable=False)
    acted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_resource_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    success_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_delta: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecommendationAction(TenantBase):
    """Trainer-initiated action against a recommendation snapshot.

    One row per (tenant_id, workspace_id, recommendation_id).
    ON CONFLICT DO UPDATE allows action_type to change (e.g. snoozed → accepted).

    action_type: what the trainer did (accepted / dismissed / snoozed / completed).
    status is NOT stored here — it is derived at the service layer so that
    "expired" (snooze_until in the past) is computed without a background job.
    """

    __tablename__ = "recommendation_actions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "recommendation_id",
            name="uq_rec_actions_tenant_ws_rec",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snooze_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Sprint 26A — execution workflow fields (all nullable; added via expand migration)
    execution_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RecommendationQualityScore(TenantBase):
    """Daily pre-computed quality score per (workspace, rec_type).

    Computed by compute_recommendation_quality_scores Celery beat task.
    Sprint 21 formula: quality_score = round(helpful / total_feedback * 100)
                       NULL (low_confidence=True) when total_feedback < 3.
    Sprint 22 will add adoption_rate and success_rate to the formula.

    The unique constraint on (tenant_id, workspace_id, rec_type, score_date)
    makes ON CONFLICT DO UPDATE upserts idempotent.
    """

    __tablename__ = "recommendation_quality_scores"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "rec_type",
            "score_date",
            name="uq_rec_quality_tenant_ws_type_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    rec_type: Mapped[str] = mapped_column(String(30), nullable=False)
    score_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shown_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    acted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    feedback_helpful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    feedback_not_helpful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    feedback_dismissed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    adoption_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0, nullable=False)
    success_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0, nullable=False)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
