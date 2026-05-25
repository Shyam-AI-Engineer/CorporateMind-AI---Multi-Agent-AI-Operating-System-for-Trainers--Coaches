"""Agent Celery tasks — run LangGraph workflows asynchronously."""

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
    retry_backoff_max=60,
    retry_jitter=True,
    soft_time_limit=270,
    time_limit=300,
    queue="agents",
    name="corpmind.workers.tasks.agents.run_agent_workflow",
)
def run_agent_workflow(self: Task, *, workflow_id: str, tenant_id: str, state: dict) -> dict:
    """Execute a LangGraph agent workflow. Checkpoints on soft time limit."""
    import asyncio
    task_key = f"agent:{workflow_id}"
    log.info("agent.task.start", task_key=task_key, tenant_id=tenant_id)

    # TODO(Phase 1): resolve agent from state.intent, call agent.run()
    return {"status": "completed", "workflow_id": workflow_id}


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    soft_time_limit=270,
    time_limit=300,
    queue="agents",
    name="corpmind.workers.tasks.agents.refresh_churn_save_segments",
)
def refresh_churn_save_segments(self: Task) -> None:
    """Refresh churn-save lead segments across all tenants."""
    log.info("crm.churn_save_refresh.start")
    # TODO(Phase 1): iterate tenants, run CampaignOptimizer for each


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    soft_time_limit=270,
    time_limit=300,
    queue="agents",
    name="corpmind.workers.tasks.agents.reap_dead_letter_queue",
)
def reap_dead_letter_queue(self: Task) -> None:
    """Surface DLQ failures grouped by fingerprint to LLMOpsGuardian."""
    log.info("dlq.reaper.start")
    # TODO(Phase 1): scan dlq.* queues, group by error fingerprint, alert
