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
