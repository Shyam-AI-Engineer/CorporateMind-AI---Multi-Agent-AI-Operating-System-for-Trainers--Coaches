"""Analytics Celery tasks — rollups, optimizer, cache prune."""

from __future__ import annotations

import structlog
from celery import Task

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
def compute_daily_rollup(self: Task) -> None:
    """Compute analytics_daily rollup for all tenants for yesterday."""
    import asyncio
    from datetime import UTC, date, timedelta
    log.info("analytics.daily_rollup.start", date=str(date.today() - timedelta(days=1)))
    # TODO(Phase 1): fan out per-tenant rollup via chord


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
