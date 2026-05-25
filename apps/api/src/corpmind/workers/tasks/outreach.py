"""Outreach Celery tasks — send pipelines."""

from __future__ import annotations

import structlog
from celery import Task

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=60,
    time_limit=90,
    queue="outreach",
    name="corpmind.workers.tasks.outreach.send_message",
)
def send_message(
    self: Task,
    *,
    message_id: str,
    tenant_id: str,
    channel: str,
    request_id: str,
) -> dict:
    """Send a single outbound message via the appropriate channel adapter."""
    task_key = f"outreach:{message_id}"
    log.info("outreach.send.start", task_key=task_key, channel=channel)
    # TODO(Phase 1): get message from DB, run ComplianceGuard, call channel adapter
    return {"status": "sent", "message_id": message_id}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    soft_time_limit=270,
    time_limit=300,
    queue="outreach",
    name="corpmind.workers.tasks.outreach.advance_followup_cadence",
)
def advance_followup_cadence(self: Task) -> None:
    """Advance follow-up sequences for all due messages across tenants."""
    log.info("outreach.cadence.start")
    # TODO(Phase 1): query due follow-ups, enqueue send_message for each
