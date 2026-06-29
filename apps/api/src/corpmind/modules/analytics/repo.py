"""Analytics repository — reads pre-computed rollup tables."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.analytics.models import (
    AnalyticsCampaignSummary,
    AnalyticsDaily,
    AnalyticsTrainerSummary,
    RecommendationAction,
    RecommendationFeedback,
    RecommendationOutcome,
    RecommendationQualityScore,
    RecommendationSnapshot,
)


class AnalyticsDailyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_date_range(
        self, from_date: date, to_date: date
    ) -> list[AnalyticsDaily]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AnalyticsDaily)
            .where(
                AnalyticsDaily.tenant_id == ctx.org_id,
                AnalyticsDaily.rollup_date >= from_date,
                AnalyticsDaily.rollup_date <= to_date,
            )
            .order_by(AnalyticsDaily.rollup_date.desc())
        )
        return list(result.scalars().all())

    async def upsert_rollup(
        self,
        *,
        tenant_id: uuid.UUID,
        rollup_date: date,
        channel: str | None,
        outreach_sent: int,
        outreach_delivered: int,
        outreach_opened: int,
        outreach_replied: int,
        compliance_blocks: int,
        meetings_scheduled: int,
        meetings_completed: int,
        leads_created: int,
        leads_booked: int,
        proposals_generated: int,
        proposals_approved: int,
        proposals_sent: int,
        ai_spend_inr: float,
        proposals_accepted: int = 0,
        closed_revenue_inr: float = 0.0,
    ) -> None:
        """Insert or replace a daily rollup row.

        ON CONFLICT DO UPDATE replaces all metric columns so re-running the
        rollup corrects any previously-written values rather than duplicating.
        The unique constraint uq_analytics_daily_tenant_date_channel ensures
        exactly one row per (tenant, date, channel).
        """
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "rollup_date": rollup_date,
            "channel": channel,
            "outreach_sent": outreach_sent,
            "outreach_delivered": outreach_delivered,
            "outreach_opened": outreach_opened,
            "outreach_replied": outreach_replied,
            "compliance_blocks": compliance_blocks,
            "meetings_scheduled": meetings_scheduled,
            "meetings_completed": meetings_completed,
            "leads_created": leads_created,
            "leads_booked": leads_booked,
            "proposals_generated": proposals_generated,
            "proposals_approved": proposals_approved,
            "proposals_sent": proposals_sent,
            "ai_spend_inr": ai_spend_inr,
            "proposals_accepted": proposals_accepted,
            "closed_revenue_inr": closed_revenue_inr,
            "computed_at": datetime.now(UTC),
        }
        skip = {"id", "tenant_id", "rollup_date", "channel"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(AnalyticsDaily)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_analytics_daily_tenant_date_channel",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)


# ── Sprint 19 — Campaign ROI summary ─────────────────────────────────────────


class AnalyticsCampaignSummaryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AnalyticsCampaignSummary]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AnalyticsCampaignSummary)
            .where(
                AnalyticsCampaignSummary.tenant_id == ctx.org_id,
                AnalyticsCampaignSummary.workspace_id == workspace_id,
            )
            .order_by(AnalyticsCampaignSummary.closed_revenue_inr.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_workspace(self, workspace_id: uuid.UUID) -> int:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(func.count())
            .select_from(AnalyticsCampaignSummary)
            .where(
                AnalyticsCampaignSummary.tenant_id == ctx.org_id,
                AnalyticsCampaignSummary.workspace_id == workspace_id,
            )
        )
        return result.scalar_one() or 0

    async def upsert_summary(
        self,
        *,
        tenant_id: uuid.UUID,
        campaign_id: uuid.UUID,
        workspace_id: uuid.UUID,
        campaign_name: str,
        channel: str,
        campaign_status: str,
        recipients_count: int,
        messages_sent: int,
        messages_delivered: int,
        replies_received: int,
        leads_created: int,
        proposals_generated: int,
        proposals_sent: int,
        proposals_accepted: int,
        closed_revenue_inr: Decimal,
        avg_deal_size_inr: Decimal | None,
        win_rate: Decimal,
        avg_days_to_accept: Decimal | None,
    ) -> None:
        """Insert or replace a campaign ROI snapshot row."""
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "workspace_id": workspace_id,
            "campaign_name": campaign_name,
            "channel": channel,
            "campaign_status": campaign_status,
            "recipients_count": recipients_count,
            "messages_sent": messages_sent,
            "messages_delivered": messages_delivered,
            "replies_received": replies_received,
            "leads_created": leads_created,
            "proposals_generated": proposals_generated,
            "proposals_sent": proposals_sent,
            "proposals_accepted": proposals_accepted,
            "closed_revenue_inr": closed_revenue_inr,
            "avg_deal_size_inr": avg_deal_size_inr,
            "win_rate": win_rate,
            "avg_days_to_accept": avg_days_to_accept,
            "last_refreshed_at": datetime.now(UTC),
        }
        skip = {"id", "tenant_id", "campaign_id"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(AnalyticsCampaignSummary)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_analytics_campaign_summary_tenant_campaign",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)


# ── Sprint 19 — Trainer summary ───────────────────────────────────────────────


class AnalyticsTrainerSummaryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_workspace_date_range(
        self,
        workspace_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> list[AnalyticsTrainerSummary]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AnalyticsTrainerSummary)
            .where(
                AnalyticsTrainerSummary.tenant_id == ctx.org_id,
                AnalyticsTrainerSummary.workspace_id == workspace_id,
                AnalyticsTrainerSummary.rollup_date >= from_date,
                AnalyticsTrainerSummary.rollup_date <= to_date,
            )
            .order_by(AnalyticsTrainerSummary.rollup_date.desc())
        )
        return list(result.scalars().all())

    async def upsert_summary(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        rollup_date: date,
        niche: str | None,
        proposals_generated: int,
        proposals_sent: int,
        proposals_accepted: int,
        closed_revenue_inr: Decimal,
        avg_deal_size_inr: Decimal | None,
        pipeline_value_inr: Decimal,
        avg_days_to_accept: Decimal | None,
    ) -> None:
        """Insert or replace a trainer daily summary row."""
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "rollup_date": rollup_date,
            "niche": niche,
            "proposals_generated": proposals_generated,
            "proposals_sent": proposals_sent,
            "proposals_accepted": proposals_accepted,
            "closed_revenue_inr": closed_revenue_inr,
            "avg_deal_size_inr": avg_deal_size_inr,
            "pipeline_value_inr": pipeline_value_inr,
            "avg_days_to_accept": avg_days_to_accept,
            "computed_at": datetime.now(UTC),
        }
        skip = {"id", "tenant_id", "workspace_id", "rollup_date"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(AnalyticsTrainerSummary)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_analytics_trainer_summary_tenant_ws_date",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)


# ── Sprint 21 — Recommendation Tracking repos ────────────────────────────────


class RecommendationSnapshotRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        rec_type: str,
        snapshot_date: date,
        confidence_score: int,
        confidence_level: str,
        title: str,
        supporting_data: dict,
        generated_at: datetime,
    ) -> uuid.UUID:
        """Insert or update a snapshot row; return its id."""
        row_id = uuid.uuid4()
        values = {
            "id": row_id,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "rec_type": rec_type,
            "snapshot_date": snapshot_date,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "title": title,
            "supporting_data": supporting_data,
            "generated_at": generated_at,
        }
        skip = {"id", "tenant_id", "workspace_id", "rec_type", "snapshot_date"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(RecommendationSnapshot)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_rec_snapshot_tenant_ws_type_date",
                set_=update_cols,
            )
            .returning(RecommendationSnapshot.id)
        )
        result = await self._session.execute(stmt)
        returned_id: uuid.UUID = result.scalar_one()
        return returned_id

    async def find_recent(
        self,
        *,
        workspace_id: uuid.UUID,
        rec_type: str,
        since_date: date,
    ) -> RecommendationSnapshot | None:
        """Return the most recent snapshot for (workspace, rec_type) since since_date."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(RecommendationSnapshot)
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
                RecommendationSnapshot.rec_type == rec_type,
                RecommendationSnapshot.snapshot_date >= since_date,
            )
            .order_by(RecommendationSnapshot.snapshot_date.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def find_by_id(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> RecommendationSnapshot | None:
        """Return a snapshot by its primary key, scoped to tenant + workspace."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(RecommendationSnapshot)
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
                RecommendationSnapshot.id == recommendation_id,
            )
        )
        return result.scalars().first()

    async def list_workspace_pairs(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return all distinct (tenant_id, workspace_id) pairs with snapshots.

        Used by the fan-out Celery tasks — runs without RLS context.
        """
        result = await self._session.execute(
            select(
                RecommendationSnapshot.tenant_id,
                RecommendationSnapshot.workspace_id,
            ).distinct()
        )
        return [(row[0], row[1]) for row in result.all()]

    async def list_unprocessed_older_than(
        self,
        *,
        workspace_id: uuid.UUID,
        cutoff_date: date,
    ) -> list[RecommendationSnapshot]:
        """Return snapshots older than cutoff_date with no outcome row yet."""
        ctx = get_tenant_context()
        # Snapshots that do NOT yet have an outcome row
        existing_outcome_ids = (
            select(RecommendationOutcome.snapshot_id).where(
                RecommendationOutcome.tenant_id == ctx.org_id,
                RecommendationOutcome.workspace_id == workspace_id,
            )
        )
        result = await self._session.execute(
            select(RecommendationSnapshot)
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
                RecommendationSnapshot.snapshot_date <= cutoff_date,
                RecommendationSnapshot.id.not_in(existing_outcome_ids),
            )
            .order_by(RecommendationSnapshot.snapshot_date.asc())
        )
        return list(result.scalars().all())

    async def count_by_workspace_type(
        self,
        *,
        workspace_id: uuid.UUID,
        rec_type: str,
        from_date: date,
        to_date: date,
    ) -> int:
        """Count snapshots for a rec_type in the period."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(func.count())
            .select_from(RecommendationSnapshot)
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
                RecommendationSnapshot.rec_type == rec_type,
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
        )
        return result.scalar_one() or 0

    async def list_type_counts(
        self,
        *,
        workspace_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> list[tuple[str, int]]:
        """Return [(rec_type, count)] sorted by count DESC for the period.

        Used by RecommendationPortfolioService to compute distribution and
        Shannon entropy without fetching full ORM objects.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationSnapshot.rec_type,
                func.count().label("cnt"),
            )
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
            .group_by(RecommendationSnapshot.rec_type)
            .order_by(func.count().desc())
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def list_versions(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> list[tuple[date, int, float]]:
        """Return [(snapshot_date, count, avg_confidence)] ordered newest first.

        Each distinct snapshot_date is a version epoch — one recommendation
        generation run.  Used by RecommendationLearningService to build the
        version history and identify current / previous versions.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationSnapshot.snapshot_date,
                func.count().label("cnt"),
                func.avg(RecommendationSnapshot.confidence_score).label("avg_conf"),
            )
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
            )
            .group_by(RecommendationSnapshot.snapshot_date)
            .order_by(RecommendationSnapshot.snapshot_date.desc())
        )
        return [(row[0], int(row[1]), float(row[2] or 0.0)) for row in result.all()]

    async def find_latest_snapshot_date_per_type(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> dict[str, date]:
        """Return {rec_type: latest snapshot_date} across all time for the workspace.

        No date-range filter — used by coverage endpoint to detect missing or
        stale recommendation types regardless of the analysis period.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationSnapshot.rec_type,
                func.max(RecommendationSnapshot.snapshot_date).label("latest_date"),
            )
            .where(
                RecommendationSnapshot.tenant_id == ctx.org_id,
                RecommendationSnapshot.workspace_id == workspace_id,
            )
            .group_by(RecommendationSnapshot.rec_type)
        )
        return {row[0]: row[1] for row in result.all()}


class RecommendationFeedbackRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_feedback(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        rec_type: str,
        outcome: str,
        notes: str | None,
        recorded_at: datetime,
    ) -> None:
        """Insert or update feedback for a snapshot (trainers may change their mind)."""
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "snapshot_id": snapshot_id,
            "rec_type": rec_type,
            "outcome": outcome,
            "notes": notes,
            "recorded_at": recorded_at,
        }
        skip = {"id", "tenant_id", "workspace_id", "snapshot_id"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(RecommendationFeedback)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_rec_feedback_tenant_ws_snapshot",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)

    async def aggregate_by_type(
        self,
        *,
        workspace_id: uuid.UUID,
        rec_type: str,
        from_date: date,
        to_date: date,
    ) -> dict[str, int]:
        """Return {helpful, not_helpful, dismissed} counts for a rec_type in the period.

        Joins to recommendation_snapshots to filter by snapshot_date.
        """
        ctx = get_tenant_context()
        rows = await self._session.execute(
            select(
                RecommendationFeedback.outcome,
                func.count().label("cnt"),
            )
            .join(
                RecommendationSnapshot,
                RecommendationFeedback.snapshot_id == RecommendationSnapshot.id,
            )
            .where(
                RecommendationFeedback.tenant_id == ctx.org_id,
                RecommendationFeedback.workspace_id == workspace_id,
                RecommendationFeedback.rec_type == rec_type,
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
            .group_by(RecommendationFeedback.outcome)
        )
        counts: dict[str, int] = {"helpful": 0, "not_helpful": 0, "dismissed": 0}
        for row in rows.all():
            if row[0] in counts:
                counts[row[0]] = int(row[1])
        return counts


class OutcomeWithTiming(NamedTuple):
    """Joined view of a recommendation_outcome + its parent snapshot timing fields.

    Used by RecommendationLifecycleService to compute timing metrics without
    pulling full ORM objects.  The snapshot_date field drives age-bucket assignment
    for decay analysis; snapshot_generated_at drives days-to-action/success.
    """

    rec_type: str
    acted: bool
    acted_at: datetime | None
    success: bool | None
    success_measured_at: datetime | None
    snapshot_generated_at: datetime
    snapshot_date: date


class RecommendationOutcomeRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_with_snapshot(
        self,
        *,
        workspace_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> list[OutcomeWithTiming]:
        """Return all outcome rows joined with snapshot timing for the date range.

        Joins recommendation_outcomes → recommendation_snapshots on snapshot_id.
        Filters on snapshot.snapshot_date so the period meaning is consistent with
        other analytics endpoints.  Returns only fields needed for lifecycle and
        decay analysis — not full ORM objects.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationOutcome.rec_type,
                RecommendationOutcome.acted,
                RecommendationOutcome.acted_at,
                RecommendationOutcome.success,
                RecommendationOutcome.success_measured_at,
                RecommendationSnapshot.generated_at.label("snapshot_generated_at"),
                RecommendationSnapshot.snapshot_date,
            )
            .join(
                RecommendationSnapshot,
                RecommendationOutcome.snapshot_id == RecommendationSnapshot.id,
            )
            .where(
                RecommendationOutcome.tenant_id == ctx.org_id,
                RecommendationOutcome.workspace_id == workspace_id,
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
            .order_by(RecommendationSnapshot.snapshot_date.desc())
        )
        return [
            OutcomeWithTiming(
                rec_type=row.rec_type,
                acted=row.acted,
                acted_at=row.acted_at,
                success=row.success,
                success_measured_at=row.success_measured_at,
                snapshot_generated_at=row.snapshot_generated_at,
                snapshot_date=row.snapshot_date,
            )
            for row in result.all()
        ]

    async def upsert_outcome(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        rec_type: str,
        acted: bool,
        acted_at: datetime | None,
        acted_resource_id: uuid.UUID | None,
        success: bool | None,
        success_measured_at: datetime | None,
        outcome_delta: Decimal | None,
        computed_at: datetime,
    ) -> None:
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "snapshot_id": snapshot_id,
            "rec_type": rec_type,
            "acted": acted,
            "acted_at": acted_at,
            "acted_resource_id": acted_resource_id,
            "success": success,
            "success_measured_at": success_measured_at,
            "outcome_delta": outcome_delta,
            "computed_at": computed_at,
        }
        skip = {"id", "tenant_id", "workspace_id", "snapshot_id"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(RecommendationOutcome)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_rec_outcome_tenant_ws_snapshot",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)

    async def aggregate_by_type_for_period(
        self,
        *,
        workspace_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> dict[str, tuple[int, int, int]]:
        """Return {rec_type: (total_outcomes, acted_count, success_count)} in period.

        Joins to recommendation_snapshots to filter by snapshot_date.
        Used by RecommendationPortfolioService to compute per-type acted/success rates.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationOutcome.rec_type,
                func.count().label("total"),
                func.count()
                .filter(RecommendationOutcome.acted.is_(True))
                .label("acted"),
                func.count()
                .filter(RecommendationOutcome.success.is_(True))
                .label("success"),
            )
            .join(
                RecommendationSnapshot,
                RecommendationOutcome.snapshot_id == RecommendationSnapshot.id,
            )
            .where(
                RecommendationOutcome.tenant_id == ctx.org_id,
                RecommendationOutcome.workspace_id == workspace_id,
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
            .group_by(RecommendationOutcome.rec_type)
        )
        return {
            row[0]: (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0))
            for row in result.all()
        }

    async def aggregate_by_version(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> dict[date, tuple[int, int]]:
        """Return {snapshot_date: (acted_count, successful_count)}.

        Joins recommendation_outcomes to recommendation_snapshots to group acted
        and successful counts by the snapshot generation date (the version epoch).
        Used by RecommendationLearningService for per-version adoption and success metrics.
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationSnapshot.snapshot_date,
                func.count()
                .filter(RecommendationOutcome.acted.is_(True))
                .label("acted"),
                func.count()
                .filter(RecommendationOutcome.success.is_(True))
                .label("successful"),
            )
            .join(
                RecommendationSnapshot,
                RecommendationOutcome.snapshot_id == RecommendationSnapshot.id,
            )
            .where(
                RecommendationOutcome.tenant_id == ctx.org_id,
                RecommendationOutcome.workspace_id == workspace_id,
            )
            .group_by(RecommendationSnapshot.snapshot_date)
        )
        return {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in result.all()}

    async def count_acted_by_type(
        self,
        *,
        workspace_id: uuid.UUID,
        rec_type: str,
        from_date: date,
        to_date: date,
    ) -> tuple[int, int]:
        """Return (acted_count, success_count) for a rec_type in the period."""
        ctx = get_tenant_context()
        rows = await self._session.execute(
            select(
                func.count().label("acted_count"),
                func.count()
                .filter(RecommendationOutcome.success.is_(True))
                .label("success_count"),
            )
            .join(
                RecommendationSnapshot,
                RecommendationOutcome.snapshot_id == RecommendationSnapshot.id,
            )
            .where(
                RecommendationOutcome.tenant_id == ctx.org_id,
                RecommendationOutcome.workspace_id == workspace_id,
                RecommendationOutcome.rec_type == rec_type,
                RecommendationOutcome.acted.is_(True),
                RecommendationSnapshot.snapshot_date >= from_date,
                RecommendationSnapshot.snapshot_date <= to_date,
            )
        )
        row = rows.first()
        if row is None:
            return 0, 0
        return int(row[0] or 0), int(row[1] or 0)


class RecommendationQualityScoreRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_score(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        rec_type: str,
        score_date: date,
        shown_count: int,
        acted_count: int,
        success_count: int,
        ignored_count: int,
        feedback_helpful: int,
        feedback_not_helpful: int,
        feedback_dismissed: int,
        adoption_rate: Decimal,
        success_rate: Decimal,
        quality_score: int | None,
        low_confidence: bool,
    ) -> None:
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "rec_type": rec_type,
            "score_date": score_date,
            "shown_count": shown_count,
            "acted_count": acted_count,
            "success_count": success_count,
            "ignored_count": ignored_count,
            "feedback_helpful": feedback_helpful,
            "feedback_not_helpful": feedback_not_helpful,
            "feedback_dismissed": feedback_dismissed,
            "adoption_rate": adoption_rate,
            "success_rate": success_rate,
            "quality_score": quality_score,
            "low_confidence": low_confidence,
            "computed_at": datetime.now(UTC),
        }
        skip = {"id", "tenant_id", "workspace_id", "rec_type", "score_date"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        stmt = (
            pg_insert(RecommendationQualityScore)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_rec_quality_tenant_ws_type_date",
                set_=update_cols,
            )
        )
        await self._session.execute(stmt)

    async def list_by_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        from_date: date,
        to_date: date,
    ) -> list[RecommendationQualityScore]:
        """Return all quality score rows for a workspace in the date range."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(RecommendationQualityScore)
            .where(
                RecommendationQualityScore.tenant_id == ctx.org_id,
                RecommendationQualityScore.workspace_id == workspace_id,
                RecommendationQualityScore.score_date >= from_date,
                RecommendationQualityScore.score_date <= to_date,
            )
            .order_by(RecommendationQualityScore.score_date.desc())
        )
        return list(result.scalars().all())

    async def aggregate_by_version(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> dict[date, float]:
        """Return {score_date: avg_quality_score} for dates with non-null scores.

        Null quality_score rows (low_confidence=True) are excluded from the average.
        Used by RecommendationLearningService to match a quality signal to each
        version epoch (snapshot_date).
        """
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(
                RecommendationQualityScore.score_date,
                func.avg(RecommendationQualityScore.quality_score).label("avg_score"),
            )
            .where(
                RecommendationQualityScore.tenant_id == ctx.org_id,
                RecommendationQualityScore.workspace_id == workspace_id,
                RecommendationQualityScore.quality_score.isnot(None),
            )
            .group_by(RecommendationQualityScore.score_date)
        )
        return {row[0]: float(row[1]) for row in result.all()}


# ── Sprint 25B — Recommendation Action Center ────────────────────────────────


class RecommendationActionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        action_type: str,
        reason: str | None,
        snooze_until: date | None,
    ) -> RecommendationAction:
        """Insert or replace an action for (tenant, workspace, recommendation_id).

        ON CONFLICT DO UPDATE allows changing from snoozed → accepted, etc.
        Returns the persisted row so the service can build the response.
        """
        now = datetime.now(UTC)
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "recommendation_id": recommendation_id,
            "action_type": action_type,
            "reason": reason,
            "snooze_until": snooze_until,
            "created_at": now,
            "updated_at": now,
        }
        skip = {"id", "tenant_id", "workspace_id", "recommendation_id", "created_at"}
        update_cols = {k: v for k, v in values.items() if k not in skip}
        update_cols["updated_at"] = now
        stmt = (
            pg_insert(RecommendationAction)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_rec_actions_tenant_ws_rec",
                set_=update_cols,
            )
            .returning(RecommendationAction)
        )
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        assert row is not None
        return row

    async def list_by_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> list[RecommendationAction]:
        """Return all action rows for a workspace ordered newest first."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(RecommendationAction)
            .where(
                RecommendationAction.tenant_id == ctx.org_id,
                RecommendationAction.workspace_id == workspace_id,
            )
            .order_by(RecommendationAction.updated_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_recommendation(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
    ) -> RecommendationAction | None:
        """Return the action for a specific recommendation, if any."""
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(RecommendationAction)
            .where(
                RecommendationAction.tenant_id == ctx.org_id,
                RecommendationAction.workspace_id == workspace_id,
                RecommendationAction.recommendation_id == recommendation_id,
            )
        )
        return result.scalars().first()

    async def update_execution(
        self,
        *,
        workspace_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        fields: dict,
    ) -> RecommendationAction | None:
        """Update execution fields on an existing recommendation_actions row.

        Returns the refreshed row after the update, or None if the row does not
        exist. Uses flush + re-fetch to avoid SQLAlchemy identity-map staleness
        that occurs when UPDATE is issued on a row already loaded in the session.
        Only the keys in `fields` are written; all other columns are untouched.
        """
        from sqlalchemy import update as sa_update

        ctx = get_tenant_context()
        fields = {**fields, "updated_at": datetime.now(UTC)}
        stmt = (
            sa_update(RecommendationAction)
            .where(
                RecommendationAction.tenant_id == ctx.org_id,
                RecommendationAction.workspace_id == workspace_id,
                RecommendationAction.recommendation_id == recommendation_id,
            )
            .values(**fields)
            .execution_options(synchronize_session="evaluate")
        )
        await self._session.execute(stmt)
        return await self.find_by_recommendation(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
        )
