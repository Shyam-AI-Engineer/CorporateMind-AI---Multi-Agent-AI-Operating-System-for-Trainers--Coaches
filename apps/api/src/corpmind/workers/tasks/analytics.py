"""Analytics Celery tasks — rollups, optimizer, cache prune."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.compute_daily_rollup",
)
def compute_daily_rollup(self: Task) -> dict:
    """Compute analytics_daily rollup for all tenants for yesterday.

    Fan-out pattern:
      1. Query all org IDs (no RLS — cross-tenant read).
      2. Enqueue one _rollup_tenant sub-task per org.

    The parent task holds no DB connection while sub-tasks run.
    Each sub-task sets its own RLS context and upserts one row into
    analytics_daily using ON CONFLICT DO UPDATE so re-runs are safe.
    """
    rollup_date = date.today() - timedelta(days=1)
    log.info("analytics.daily_rollup.start", date=str(rollup_date))
    try:
        return asyncio.run(_fan_out_rollup(rollup_date=rollup_date))
    except SoftTimeLimitExceeded:
        log.warning("analytics.daily_rollup.soft_timeout")
        raise self.retry(countdown=300) from None
    except Exception as exc:
        log.error("analytics.daily_rollup.error", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _fan_out_rollup(*, rollup_date: date) -> dict:
    """Query all active orgs and enqueue per-tenant rollup sub-tasks."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.modules.identity.models import Org

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    enqueued = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(select(Org.id))
            org_ids: list[uuid.UUID] = [row[0] for row in result.all()]

        for org_id in org_ids:
            try:
                _rollup_tenant.apply_async(
                    kwargs={
                        "tenant_id": str(org_id),
                        "rollup_date": str(rollup_date),
                    },
                    queue="analytics",
                )
                enqueued += 1
            except Exception as exc:
                failed += 1
                log.error(
                    "analytics.daily_rollup.enqueue_failed",
                    tenant_id=str(org_id),
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    log.info(
        "analytics.daily_rollup.fan_out_complete",
        rollup_date=str(rollup_date),
        enqueued=enqueued,
        failed=failed,
    )
    return {"rollup_date": str(rollup_date), "enqueued": enqueued, "failed": failed}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    queue="analytics",
    name="corpmind.workers.tasks.analytics._rollup_tenant",
)
def _rollup_tenant(self: Task, *, tenant_id: str, rollup_date: str) -> dict:
    """Compute and upsert one analytics_daily row for a single tenant."""
    try:
        return asyncio.run(
            _compute_tenant_rollup(
                tenant_id=uuid.UUID(tenant_id),
                rollup_date=date.fromisoformat(rollup_date),
            )
        )
    except SoftTimeLimitExceeded:
        log.warning("analytics.rollup_tenant.soft_timeout", tenant_id=tenant_id)
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error("analytics.rollup_tenant.error", tenant_id=tenant_id, error=str(exc))
        raise self.retry(exc=exc) from exc


async def _compute_tenant_rollup(
    *, tenant_id: uuid.UUID, rollup_date: date
) -> dict:
    """Run all aggregation queries for one tenant and upsert analytics_daily."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.modules.analytics.repo import AnalyticsDailyRepo

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=tenant_id,  # no single workspace scope for rollups
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )
    token = set_tenant_context(ctx)

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            d = rollup_date
            d_str = str(d)

            def scalar(row: object) -> int:
                return int(row) if row is not None else 0  # type: ignore[arg-type]

            # ── Outreach metrics (from campaign_recipients + outbound_messages) ──
            sent_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM outbound_messages"
                    " WHERE tenant_id = :tid AND sent_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            outreach_sent = scalar(sent_row.scalar_one())

            delivered_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM campaign_recipients"
                    " WHERE tenant_id = :tid AND delivered_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            outreach_delivered = scalar(delivered_row.scalar_one())

            opened_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM campaign_recipients"
                    " WHERE tenant_id = :tid AND opened_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            outreach_opened = scalar(opened_row.scalar_one())

            replied_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM inbox_messages"
                    " WHERE tenant_id = :tid AND received_at::date = :d"
                    " AND reply_intent = 'interested'"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            outreach_replied = scalar(replied_row.scalar_one())

            # ── Compliance ────────────────────────────────────────────────────────
            blocks_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM campaign_recipients"
                    " WHERE tenant_id = :tid AND status = 'compliance_blocked'"
                    " AND sent_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            compliance_blocks = scalar(blocks_row.scalar_one())

            # ── CRM pipeline ──────────────────────────────────────────────────────
            meetings_sched_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM leads"
                    " WHERE tenant_id = :tid AND meeting_scheduled_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            meetings_scheduled = scalar(meetings_sched_row.scalar_one())

            meetings_comp_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM leads"
                    " WHERE tenant_id = :tid AND stage = 'meeting_completed'"
                    " AND updated_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            meetings_completed = scalar(meetings_comp_row.scalar_one())

            leads_created_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM leads"
                    " WHERE tenant_id = :tid AND created_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            leads_created = scalar(leads_created_row.scalar_one())

            leads_booked_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM leads"
                    " WHERE tenant_id = :tid AND booked_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            leads_booked = scalar(leads_booked_row.scalar_one())

            # ── Proposals ─────────────────────────────────────────────────────────
            props_gen_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM proposals"
                    " WHERE tenant_id = :tid AND created_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            proposals_generated = scalar(props_gen_row.scalar_one())

            props_appr_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM proposals"
                    " WHERE tenant_id = :tid AND approved_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            proposals_approved = scalar(props_appr_row.scalar_one())

            props_sent_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM proposals"
                    " WHERE tenant_id = :tid AND sent_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            proposals_sent = scalar(props_sent_row.scalar_one())

            # ── WhatsApp per-channel metrics ───────────────────────────────────
            # Reads outbound_messages directly (not campaign_recipients) because
            # WA delivery/read timestamps live on outbound_messages (Sprint 16B).
            wa_sent_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM outbound_messages"
                    " WHERE tenant_id = :tid AND channel = 'whatsapp'"
                    " AND sent_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            wa_sent = scalar(wa_sent_row.scalar_one())

            wa_delivered_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM outbound_messages"
                    " WHERE tenant_id = :tid AND channel = 'whatsapp'"
                    " AND delivered_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            wa_delivered = scalar(wa_delivered_row.scalar_one())

            wa_read_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM outbound_messages"
                    " WHERE tenant_id = :tid AND channel = 'whatsapp'"
                    " AND read_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            wa_opened = scalar(wa_read_row.scalar_one())

            wa_blocks_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM outbound_messages"
                    " WHERE tenant_id = :tid AND channel = 'whatsapp'"
                    " AND status = 'blocked'"
                    " AND updated_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            wa_blocks = scalar(wa_blocks_row.scalar_one())

            # ── Sprint 18A — revenue rollup ───────────────────────────────────────
            props_accepted_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM proposals"
                    " WHERE tenant_id = :tid AND client_accepted_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            proposals_accepted = scalar(props_accepted_row.scalar_one())

            closed_rev_row = await session.execute(
                text(
                    "SELECT COALESCE(SUM(actual_value_inr), 0) FROM proposals"
                    " WHERE tenant_id = :tid AND client_accepted_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            closed_revenue_inr = float(closed_rev_row.scalar_one() or 0)

            # ── Upsert (channel=None = cross-channel aggregate) ───────────────────
            repo = AnalyticsDailyRepo(session)
            await repo.upsert_rollup(
                tenant_id=tenant_id,
                rollup_date=d,
                channel=None,
                outreach_sent=outreach_sent,
                outreach_delivered=outreach_delivered,
                outreach_opened=outreach_opened,
                outreach_replied=outreach_replied,
                compliance_blocks=compliance_blocks,
                meetings_scheduled=meetings_scheduled,
                meetings_completed=meetings_completed,
                leads_created=leads_created,
                leads_booked=leads_booked,
                proposals_generated=proposals_generated,
                proposals_approved=proposals_approved,
                proposals_sent=proposals_sent,
                ai_spend_inr=0.0,  # model_runs table not yet wired — Phase 2
                proposals_accepted=proposals_accepted,
                closed_revenue_inr=closed_revenue_inr,
            )

            wa_replied_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM inbox_messages"
                    " WHERE tenant_id = :tid AND channel = 'whatsapp'"
                    " AND reply_intent IS NOT NULL"
                    " AND received_at::date = :d"
                ),
                {"tid": tenant_id, "d": d_str},
            )
            wa_replied = scalar(wa_replied_row.scalar_one())

            # ── Upsert per-channel WhatsApp row ──────────────────────────────────
            # CRM / proposal metrics are cross-channel and not meaningful per channel;
            # set them to zero in the channel-specific row.
            await repo.upsert_rollup(
                tenant_id=tenant_id,
                rollup_date=d,
                channel="whatsapp",
                outreach_sent=wa_sent,
                outreach_delivered=wa_delivered,
                outreach_opened=wa_opened,
                outreach_replied=wa_replied,
                compliance_blocks=wa_blocks,
                meetings_scheduled=0,
                meetings_completed=0,
                leads_created=0,
                leads_booked=0,
                proposals_generated=0,
                proposals_approved=0,
                proposals_sent=0,
                ai_spend_inr=0.0,
            )
            await session.commit()

        log.info(
            "analytics.rollup_tenant.complete",
            tenant_id=str(tenant_id),
            rollup_date=str(d),
            outreach_sent=outreach_sent,
            outreach_replied=outreach_replied,
            leads_created=leads_created,
            leads_booked=leads_booked,
            proposals_generated=proposals_generated,
        )
        return {
            "tenant_id": str(tenant_id),
            "rollup_date": str(d),
            "outreach_sent": outreach_sent,
            "leads_created": leads_created,
        }
    finally:
        clear_tenant_context(token)
        await engine.dispose()


# ── Sprint 19 — Campaign ROI summary rollup ──────────────────────────────────


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.compute_campaign_summary",
)
def compute_campaign_summary(self: Task) -> dict:
    """Refresh analytics_campaign_summary for all tenants.

    Fan-out pattern (same as compute_daily_rollup):
      1. Query all org IDs.
      2. Enqueue one _summarise_tenant_campaigns sub-task per org.
    """
    log.info("analytics.campaign_summary.start")
    try:
        return asyncio.run(_fan_out_campaign_summary())
    except SoftTimeLimitExceeded:
        log.warning("analytics.campaign_summary.soft_timeout")
        raise self.retry(countdown=300) from None
    except Exception as exc:
        log.error("analytics.campaign_summary.error", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _fan_out_campaign_summary() -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.modules.identity.models import Org

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    enqueued = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(select(Org.id))
            org_ids: list[uuid.UUID] = [row[0] for row in result.all()]

        for org_id in org_ids:
            try:
                _summarise_tenant_campaigns.apply_async(
                    kwargs={"tenant_id": str(org_id)},
                    queue="analytics",
                )
                enqueued += 1
            except Exception as exc:
                failed += 1
                log.error(
                    "analytics.campaign_summary.enqueue_failed",
                    tenant_id=str(org_id),
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    log.info(
        "analytics.campaign_summary.fan_out_complete",
        enqueued=enqueued,
        failed=failed,
    )
    return {"enqueued": enqueued, "failed": failed}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=120,
    time_limit=180,
    queue="analytics",
    name="corpmind.workers.tasks.analytics._summarise_tenant_campaigns",
)
def _summarise_tenant_campaigns(self: Task, *, tenant_id: str) -> dict:
    """Compute and upsert analytics_campaign_summary for one tenant."""
    try:
        return asyncio.run(_compute_tenant_campaign_summaries(tenant_id=uuid.UUID(tenant_id)))
    except SoftTimeLimitExceeded:
        log.warning("analytics.summarise_campaigns.soft_timeout", tenant_id=tenant_id)
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error("analytics.summarise_campaigns.error", tenant_id=tenant_id, error=str(exc))
        raise self.retry(exc=exc) from exc


async def _compute_tenant_campaign_summaries(*, tenant_id: uuid.UUID) -> dict:
    """Aggregate per-campaign metrics and upsert analytics_campaign_summary.

    Attribution is all-touch: every campaign a contact appeared in via
    campaign_recipients gets revenue credited (via leads → proposals join).
    """
    from decimal import Decimal

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.modules.analytics.repo import AnalyticsCampaignSummaryRepo

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=tenant_id,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )
    token = set_tenant_context(ctx)
    upserted = 0

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            campaigns_result = await session.execute(
                text(
                    "SELECT id, workspace_id, name, channel, status"
                    " FROM campaigns WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
            campaigns = campaigns_result.mappings().all()

            repo = AnalyticsCampaignSummaryRepo(session)

            for camp in campaigns:
                camp_id = camp["id"]
                wid = camp["workspace_id"]

                metrics = await session.execute(
                    text(
                        "SELECT"
                        "  COUNT(cr.id)                                              AS recipients_count,"
                        "  COUNT(cr.id) FILTER (WHERE cr.sent_at IS NOT NULL)        AS messages_sent,"
                        "  COUNT(cr.id) FILTER (WHERE cr.delivered_at IS NOT NULL)   AS messages_delivered,"
                        "  COUNT(cr.id) FILTER (WHERE cr.replied_at IS NOT NULL)     AS replies_received,"
                        "  COUNT(DISTINCT l.id)                                      AS leads_created,"
                        "  COUNT(DISTINCT p.id) FILTER (WHERE p.id IS NOT NULL)      AS proposals_generated,"
                        "  COUNT(DISTINCT p.id) FILTER"
                        "    (WHERE p.status = 'sent')                               AS proposals_sent,"
                        "  COUNT(DISTINCT p.id) FILTER"
                        "    (WHERE p.client_status = 'accepted')                    AS proposals_accepted,"
                        "  COALESCE(SUM(p.actual_value_inr)"
                        "    FILTER (WHERE p.client_status = 'accepted'), 0)         AS closed_revenue_inr,"
                        "  AVG(p.actual_value_inr)"
                        "    FILTER (WHERE p.client_status = 'accepted')             AS avg_deal_size_inr,"
                        "  AVG(EXTRACT(EPOCH FROM (p.client_accepted_at - p.sent_at)) / 86400.0)"
                        "    FILTER (WHERE p.client_status = 'accepted'"
                        "              AND p.sent_at IS NOT NULL"
                        "              AND p.client_accepted_at IS NOT NULL)         AS avg_days_to_accept"
                        " FROM campaign_recipients cr"
                        " LEFT JOIN leads l"
                        "   ON l.campaign_recipient_id = cr.id AND l.tenant_id = cr.tenant_id"
                        " LEFT JOIN proposals p"
                        "   ON p.lead_id = l.id AND p.tenant_id = cr.tenant_id"
                        " WHERE cr.tenant_id = :tid AND cr.campaign_id = :cid"
                    ),
                    {"tid": tenant_id, "cid": camp_id},
                )
                row = metrics.mappings().first()
                if row is None:
                    continue

                props_sent = int(row["proposals_sent"] or 0)
                props_accepted = int(row["proposals_accepted"] or 0)
                win_rate = (
                    Decimal(str(round(props_accepted / props_sent, 4)))
                    if props_sent > 0
                    else Decimal("0")
                )

                await repo.upsert_summary(
                    tenant_id=tenant_id,
                    campaign_id=camp_id,
                    workspace_id=wid,
                    campaign_name=camp["name"],
                    channel=camp["channel"],
                    campaign_status=camp["status"],
                    recipients_count=int(row["recipients_count"] or 0),
                    messages_sent=int(row["messages_sent"] or 0),
                    messages_delivered=int(row["messages_delivered"] or 0),
                    replies_received=int(row["replies_received"] or 0),
                    leads_created=int(row["leads_created"] or 0),
                    proposals_generated=int(row["proposals_generated"] or 0),
                    proposals_sent=props_sent,
                    proposals_accepted=props_accepted,
                    closed_revenue_inr=Decimal(str(row["closed_revenue_inr"] or 0)),
                    avg_deal_size_inr=(
                        Decimal(str(round(float(row["avg_deal_size_inr"]), 2)))
                        if row["avg_deal_size_inr"] is not None
                        else None
                    ),
                    win_rate=win_rate,
                    avg_days_to_accept=(
                        Decimal(str(round(float(row["avg_days_to_accept"]), 2)))
                        if row["avg_days_to_accept"] is not None
                        else None
                    ),
                )
                upserted += 1

            await session.commit()

        log.info(
            "analytics.summarise_campaigns.complete",
            tenant_id=str(tenant_id),
            upserted=upserted,
        )
        return {"tenant_id": str(tenant_id), "upserted": upserted}
    finally:
        clear_tenant_context(token)
        await engine.dispose()


# ── Sprint 19 — Trainer summary rollup ───────────────────────────────────────


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.compute_trainer_summary",
)
def compute_trainer_summary(self: Task) -> dict:
    """Refresh analytics_trainer_summary for all tenants for yesterday.

    Fan-out: parent queries all (org_id, workspace_id) pairs and enqueues
    one _summarise_tenant_trainers sub-task per workspace.
    """
    rollup_date = date.today() - timedelta(days=1)
    log.info("analytics.trainer_summary.start", date=str(rollup_date))
    try:
        return asyncio.run(_fan_out_trainer_summary(rollup_date=rollup_date))
    except SoftTimeLimitExceeded:
        log.warning("analytics.trainer_summary.soft_timeout")
        raise self.retry(countdown=300) from None
    except Exception as exc:
        log.error("analytics.trainer_summary.error", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _fan_out_trainer_summary(*, rollup_date: date) -> dict:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    enqueued = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT tenant_id, workspace_id"
                    " FROM trainer_profiles"
                )
            )
            pairs = result.all()

        for tenant_id, workspace_id in pairs:
            try:
                _summarise_tenant_trainers.apply_async(
                    kwargs={
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                        "rollup_date": str(rollup_date),
                    },
                    queue="analytics",
                )
                enqueued += 1
            except Exception as exc:
                failed += 1
                log.error(
                    "analytics.trainer_summary.enqueue_failed",
                    tenant_id=str(tenant_id),
                    workspace_id=str(workspace_id),
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    log.info(
        "analytics.trainer_summary.fan_out_complete",
        rollup_date=str(rollup_date),
        enqueued=enqueued,
        failed=failed,
    )
    return {"rollup_date": str(rollup_date), "enqueued": enqueued, "failed": failed}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    queue="analytics",
    name="corpmind.workers.tasks.analytics._summarise_tenant_trainers",
)
def _summarise_tenant_trainers(
    self: Task, *, tenant_id: str, workspace_id: str, rollup_date: str
) -> dict:
    """Compute and upsert one analytics_trainer_summary row."""
    try:
        return asyncio.run(
            _compute_workspace_trainer_summary(
                tenant_id=uuid.UUID(tenant_id),
                workspace_id=uuid.UUID(workspace_id),
                rollup_date=date.fromisoformat(rollup_date),
            )
        )
    except SoftTimeLimitExceeded:
        log.warning(
            "analytics.summarise_trainers.soft_timeout",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error(
            "analytics.summarise_trainers.error",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _compute_workspace_trainer_summary(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    rollup_date: date,
) -> dict:
    """Aggregate daily trainer metrics for one workspace and upsert the row."""
    from decimal import Decimal

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.modules.analytics.repo import AnalyticsTrainerSummaryRepo

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=workspace_id,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )
    token = set_tenant_context(ctx)
    d_str = str(rollup_date)

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            niche_result = await session.execute(
                text(
                    "SELECT niche FROM trainer_profiles"
                    " WHERE tenant_id = :tid AND workspace_id = :wid"
                    " ORDER BY created_at DESC LIMIT 1"
                ),
                {"tid": tenant_id, "wid": workspace_id},
            )
            niche_row = niche_result.mappings().first()
            niche = niche_row["niche"] if niche_row else None

            metrics_result = await session.execute(
                text(
                    "SELECT"
                    "  COUNT(*) FILTER (WHERE created_at::date = :d)             AS proposals_generated,"
                    "  COUNT(*) FILTER (WHERE sent_at::date = :d)                AS proposals_sent,"
                    "  COUNT(*) FILTER (WHERE client_accepted_at::date = :d)     AS proposals_accepted,"
                    "  COALESCE(SUM(actual_value_inr)"
                    "    FILTER (WHERE client_accepted_at::date = :d), 0)        AS closed_revenue_inr,"
                    "  AVG(actual_value_inr)"
                    "    FILTER (WHERE client_accepted_at::date = :d"
                    "              AND actual_value_inr IS NOT NULL)             AS avg_deal_size_inr,"
                    "  COALESCE(SUM(expected_value_inr)"
                    "    FILTER (WHERE status = 'sent'"
                    "              AND client_status IS NULL), 0)                AS pipeline_value_inr,"
                    "  AVG(EXTRACT(EPOCH FROM (client_accepted_at - sent_at)) / 86400.0)"
                    "    FILTER (WHERE client_accepted_at::date = :d"
                    "              AND sent_at IS NOT NULL"
                    "              AND client_accepted_at IS NOT NULL)           AS avg_days_to_accept"
                    " FROM proposals"
                    " WHERE tenant_id = :tid AND workspace_id = :wid"
                ),
                {"tid": tenant_id, "wid": workspace_id, "d": d_str},
            )
            row = metrics_result.mappings().first()

            repo = AnalyticsTrainerSummaryRepo(session)
            await repo.upsert_summary(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                rollup_date=rollup_date,
                niche=niche,
                proposals_generated=int(row["proposals_generated"] or 0) if row else 0,
                proposals_sent=int(row["proposals_sent"] or 0) if row else 0,
                proposals_accepted=int(row["proposals_accepted"] or 0) if row else 0,
                closed_revenue_inr=Decimal(str(row["closed_revenue_inr"] or 0)) if row else Decimal("0"),
                avg_deal_size_inr=(
                    Decimal(str(round(float(row["avg_deal_size_inr"]), 2)))
                    if row and row["avg_deal_size_inr"] is not None
                    else None
                ),
                pipeline_value_inr=Decimal(str(row["pipeline_value_inr"] or 0)) if row else Decimal("0"),
                avg_days_to_accept=(
                    Decimal(str(round(float(row["avg_days_to_accept"]), 2)))
                    if row and row["avg_days_to_accept"] is not None
                    else None
                ),
            )
            await session.commit()

        log.info(
            "analytics.summarise_trainers.complete",
            tenant_id=str(tenant_id),
            workspace_id=str(workspace_id),
            rollup_date=d_str,
        )
        return {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "rollup_date": d_str,
        }
    finally:
        clear_tenant_context(token)
        await engine.dispose()


@app.task(
    bind=True,
    acks_late=True,
    max_retries=1,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.run_campaign_optimizer",
)
def run_campaign_optimizer(self: Task) -> None:
    """Run CampaignOptimizer agent for all active tenants."""
    log.info("analytics.optimizer.start")


# ── Sprint 21 — Recommendation Outcomes ──────────────────────────────────────


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.compute_recommendation_outcomes",
)
def compute_recommendation_outcomes(self: Task) -> dict:
    """Detect acted outcomes for recommendation snapshots (daily at 02:15 UTC).

    Sprint 21 scope: channel type only — checks whether a campaign was launched
    on the recommended channel within 30 days of snapshot_date.
    industry / topic / pricing / campaign → acted=False (Sprint 22).
    Fan-out: one sub-task per (tenant, workspace) pair with snapshots.
    """
    rollup_date = date.today() - timedelta(days=1)
    log.info("analytics.rec_outcomes.start", date=str(rollup_date))
    try:
        return asyncio.run(_fan_out_rec_outcomes(rollup_date=rollup_date))
    except SoftTimeLimitExceeded:
        log.warning("analytics.rec_outcomes.soft_timeout")
        raise self.retry(countdown=300) from None
    except Exception as exc:
        log.error("analytics.rec_outcomes.error", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _fan_out_rec_outcomes(*, rollup_date: date) -> dict:
    """Query all (tenant, workspace) pairs with snapshots and fan out sub-tasks."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    enqueued = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT tenant_id, workspace_id"
                    " FROM recommendation_snapshots"
                )
            )
            pairs = result.all()

        for tenant_id, workspace_id in pairs:
            try:
                _compute_tenant_rec_outcomes.apply_async(
                    kwargs={
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                        "rollup_date": str(rollup_date),
                    },
                    queue="analytics",
                )
                enqueued += 1
            except Exception as exc:
                failed += 1
                log.error(
                    "analytics.rec_outcomes.enqueue_failed",
                    tenant_id=str(tenant_id),
                    workspace_id=str(workspace_id),
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    log.info(
        "analytics.rec_outcomes.fan_out_complete",
        rollup_date=str(rollup_date),
        enqueued=enqueued,
        failed=failed,
    )
    return {"rollup_date": str(rollup_date), "enqueued": enqueued, "failed": failed}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    queue="analytics",
    name="corpmind.workers.tasks.analytics._compute_tenant_rec_outcomes",
)
def _compute_tenant_rec_outcomes(
    self: Task, *, tenant_id: str, workspace_id: str, rollup_date: str
) -> dict:
    """Compute recommendation outcomes for one (tenant, workspace) pair."""
    try:
        return asyncio.run(
            _detect_rec_outcomes_for_workspace(
                tenant_id=uuid.UUID(tenant_id),
                workspace_id=uuid.UUID(workspace_id),
                rollup_date=date.fromisoformat(rollup_date),
            )
        )
    except SoftTimeLimitExceeded:
        log.warning(
            "analytics.rec_outcomes.soft_timeout",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error(
            "analytics.rec_outcomes.error",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _detect_rec_outcomes_for_workspace(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    rollup_date: date,
) -> dict:
    """Upsert acted=True/False for unprocessed snapshots in one workspace.

    Channel type: acted=True if any campaign with matching channel was created
    within 30 days after snapshot_date.
    All other types: acted=False in Sprint 21 (detection deferred to Sprint 22).
    """
    from datetime import datetime, time, timedelta as td, timezone

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.modules.analytics.repo import RecommendationOutcomeRepo, RecommendationSnapshotRepo

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=workspace_id,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )
    token = set_tenant_context(ctx)
    processed = 0
    acted_count = 0

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            cutoff = rollup_date - td(days=30)
            snap_repo = RecommendationSnapshotRepo(session)
            snapshots = await snap_repo.list_unprocessed_older_than(
                workspace_id=workspace_id,
                cutoff_date=cutoff,
            )

            outcome_repo = RecommendationOutcomeRepo(session)
            for snap in snapshots:
                acted = False
                acted_at = None
                acted_resource_id = None

                if snap.rec_type == "channel":
                    rec_channel = (snap.supporting_data or {}).get("channel")
                    if rec_channel:
                        # Use timezone-aware UTC datetimes — campaigns.created_at is TIMESTAMPTZ.
                        window_start = datetime.combine(snap.snapshot_date, time.min, tzinfo=timezone.utc)
                        window_end = datetime.combine(
                            snap.snapshot_date + td(days=30), time.min, tzinfo=timezone.utc
                        )
                        row = await session.execute(
                            text(
                                "SELECT id, created_at FROM campaigns"
                                " WHERE tenant_id = :tid"
                                "   AND workspace_id = :wid"
                                "   AND channel = :ch"
                                "   AND status NOT IN ('draft', 'rejected')"
                                "   AND created_at >= :ws"
                                "   AND created_at < :we"
                                " ORDER BY created_at ASC LIMIT 1"
                            ),
                            {
                                "tid": tenant_id,
                                "wid": workspace_id,
                                "ch": rec_channel,
                                "ws": window_start,
                                "we": window_end,
                            },
                        )
                        campaign_row = row.mappings().first()
                        if campaign_row:
                            acted = True
                            acted_at = campaign_row["created_at"]
                            acted_resource_id = campaign_row["id"]

                await outcome_repo.upsert_outcome(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    snapshot_id=snap.id,
                    rec_type=snap.rec_type,
                    acted=acted,
                    acted_at=acted_at,
                    acted_resource_id=acted_resource_id,
                    success=None,
                    success_measured_at=None,
                    outcome_delta=None,
                    computed_at=datetime.now(timezone.utc),
                )
                processed += 1
                if acted:
                    acted_count += 1

            await session.commit()

    finally:
        clear_tenant_context(token)
        await engine.dispose()

    log.info(
        "analytics.rec_outcomes.complete",
        tenant_id=str(tenant_id),
        workspace_id=str(workspace_id),
        processed=processed,
        acted=acted_count,
    )
    return {
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "processed": processed,
        "acted": acted_count,
    }


# ── Sprint 21 — Recommendation Quality Scores ────────────────────────────────


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=600,
    time_limit=900,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.compute_recommendation_quality_scores",
)
def compute_recommendation_quality_scores(self: Task) -> dict:
    """Roll up feedback + outcomes into quality scores (daily at 02:30 UTC).

    Aggregates the last 90 days of snapshots, feedback, and outcomes per
    (workspace, rec_type).  Sprint 21 quality formula:
      quality_score = round(helpful / total_feedback * 100)
      NULL (low_confidence=True) when total_feedback < 3.
    Fan-out: one sub-task per (tenant, workspace) pair.
    """
    rollup_date = date.today() - timedelta(days=1)
    log.info("analytics.rec_quality.start", date=str(rollup_date))
    try:
        return asyncio.run(_fan_out_rec_quality(rollup_date=rollup_date))
    except SoftTimeLimitExceeded:
        log.warning("analytics.rec_quality.soft_timeout")
        raise self.retry(countdown=300) from None
    except Exception as exc:
        log.error("analytics.rec_quality.error", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _fan_out_rec_quality(*, rollup_date: date) -> dict:
    """Query all (tenant, workspace) pairs with snapshots and fan out sub-tasks."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    enqueued = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT DISTINCT tenant_id, workspace_id"
                    " FROM recommendation_snapshots"
                )
            )
            pairs = result.all()

        for tenant_id, workspace_id in pairs:
            try:
                _compute_tenant_rec_quality.apply_async(
                    kwargs={
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                        "rollup_date": str(rollup_date),
                    },
                    queue="analytics",
                )
                enqueued += 1
            except Exception as exc:
                failed += 1
                log.error(
                    "analytics.rec_quality.enqueue_failed",
                    tenant_id=str(tenant_id),
                    workspace_id=str(workspace_id),
                    error=str(exc),
                )
    finally:
        await engine.dispose()

    log.info(
        "analytics.rec_quality.fan_out_complete",
        rollup_date=str(rollup_date),
        enqueued=enqueued,
        failed=failed,
    )
    return {"rollup_date": str(rollup_date), "enqueued": enqueued, "failed": failed}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    queue="analytics",
    name="corpmind.workers.tasks.analytics._compute_tenant_rec_quality",
)
def _compute_tenant_rec_quality(
    self: Task, *, tenant_id: str, workspace_id: str, rollup_date: str
) -> dict:
    """Aggregate quality scores for one (tenant, workspace) pair."""
    try:
        return asyncio.run(
            _rollup_rec_quality_for_workspace(
                tenant_id=uuid.UUID(tenant_id),
                workspace_id=uuid.UUID(workspace_id),
                rollup_date=date.fromisoformat(rollup_date),
            )
        )
    except SoftTimeLimitExceeded:
        log.warning(
            "analytics.rec_quality.soft_timeout",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error(
            "analytics.rec_quality.error",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _rollup_rec_quality_for_workspace(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    rollup_date: date,
) -> dict:
    """Aggregate feedback + outcomes and upsert one quality_score row per rec_type.

    Sprint 21 quality formula:
      total_feedback = helpful + not_helpful + dismissed
      quality_score  = round(helpful / total_feedback * 100)  when total >= 3
      quality_score  = NULL (low_confidence=True)             when total < 3
    shown_count   = snapshot rows in the 90-day window.
    acted_count   = outcome rows where acted=True.
    success_count = outcome rows where success=True (0 in Sprint 21).
    ignored_count = snapshots with an outcome row but acted=False and no feedback.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
    from corpmind.modules.analytics.repo import RecommendationQualityScoreRepo

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    ctx = TenantContext(
        org_id=tenant_id,
        workspace_id=workspace_id,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )
    token = set_tenant_context(ctx)
    upserted = 0

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_id)

            from_date = rollup_date - timedelta(days=89)  # 90-day window

            rows = await session.execute(
                text(
                    """
                    SELECT
                        s.rec_type,
                        COUNT(DISTINCT s.id)                                         AS shown_count,
                        COUNT(DISTINCT o.snapshot_id) FILTER (WHERE o.acted = TRUE)  AS acted_count,
                        COUNT(DISTINCT o.snapshot_id) FILTER (WHERE o.success = TRUE) AS success_count,
                        COUNT(DISTINCT f.id) FILTER (WHERE f.outcome = 'helpful')    AS feedback_helpful,
                        COUNT(DISTINCT f.id) FILTER (WHERE f.outcome = 'not_helpful') AS feedback_not_helpful,
                        COUNT(DISTINCT f.id) FILTER (WHERE f.outcome = 'dismissed')  AS feedback_dismissed,
                        COUNT(DISTINCT o.snapshot_id)
                            FILTER (WHERE o.acted = FALSE AND f.id IS NULL)          AS ignored_count
                    FROM recommendation_snapshots s
                    LEFT JOIN recommendation_outcomes o ON o.snapshot_id = s.id
                        AND o.tenant_id = s.tenant_id
                    LEFT JOIN recommendation_feedback f ON f.snapshot_id = s.id
                        AND f.tenant_id = s.tenant_id
                    WHERE s.tenant_id = :tid
                      AND s.workspace_id = :wid
                      AND s.snapshot_date >= :from_date
                      AND s.snapshot_date <= :rollup_date
                    GROUP BY s.rec_type
                    """
                ),
                {
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "from_date": from_date,
                    "rollup_date": rollup_date,
                },
            )
            rec_rows = rows.mappings().all()

            quality_repo = RecommendationQualityScoreRepo(session)
            for r in rec_rows:
                helpful = int(r["feedback_helpful"] or 0)
                not_helpful = int(r["feedback_not_helpful"] or 0)
                dismissed = int(r["feedback_dismissed"] or 0)
                total_feedback = helpful + not_helpful + dismissed

                quality_score = (
                    round(helpful / total_feedback * 100) if total_feedback >= 3 else None
                )
                low_confidence = quality_score is None

                from decimal import Decimal as D
                acted = int(r["acted_count"] or 0)
                shown = int(r["shown_count"] or 0)
                adoption_rate = D(str(round(acted / shown, 4))) if shown > 0 else D("0")

                await quality_repo.upsert_score(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    rec_type=r["rec_type"],
                    score_date=rollup_date,
                    shown_count=shown,
                    acted_count=acted,
                    success_count=int(r["success_count"] or 0),
                    ignored_count=int(r["ignored_count"] or 0),
                    feedback_helpful=helpful,
                    feedback_not_helpful=not_helpful,
                    feedback_dismissed=dismissed,
                    adoption_rate=adoption_rate,
                    success_rate=D("0"),  # Sprint 22
                    quality_score=quality_score,
                    low_confidence=low_confidence,
                )
                upserted += 1

            await session.commit()

    finally:
        clear_tenant_context(token)
        await engine.dispose()

    log.info(
        "analytics.rec_quality.complete",
        tenant_id=str(tenant_id),
        workspace_id=str(workspace_id),
        upserted=upserted,
    )
    return {
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "upserted": upserted,
    }


@app.task(
    bind=True,
    acks_late=True,
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
    queue="analytics",
    name="corpmind.workers.tasks.analytics.prune_semantic_cache",
)
def prune_semantic_cache(self: Task) -> None:
    """Apply LFU eviction + 30-day hard TTL to Qdrant prompt cache."""
    log.info("ai.cache_prune.start")
