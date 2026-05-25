"""Celery application configuration.

6 named queues, each with isolated workers and per-tenant concurrency caps.
Every task must declare: bind, acks_late, max_retries, retry_backoff, time_limit.

Queue routing:
  agents      — LangGraph agent runs
  outreach    — message send pipelines
  social      — IG/FB/TG/LI scheduled posts
  ingestion   — OCR, transcription, embedding
  analytics   — daily rollups, optimizer jobs
  scrape      — low-priority, isolated egress
"""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_ready

from corpmind.core.config import settings

app = Celery("corpmind")

app.config_from_object(
    {
        "broker_url": settings.CELERY_BROKER_URL,
        "result_backend": settings.CELERY_RESULT_BACKEND,
        "broker_connection_retry_on_startup": True,

        # Serialization
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],

        # Reliability
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "worker_prefetch_multiplier": 1,  # prevent queue hoarding

        # Queues — each worker process declares which queues it consumes
        "task_queues": {
            "agents":    {"exchange": "agents",    "routing_key": "agents"},
            "outreach":  {"exchange": "outreach",  "routing_key": "outreach"},
            "social":    {"exchange": "social",    "routing_key": "social"},
            "ingestion": {"exchange": "ingestion", "routing_key": "ingestion"},
            "analytics": {"exchange": "analytics", "routing_key": "analytics"},
            "scrape":    {"exchange": "scrape",    "routing_key": "scrape"},
        },
        "task_default_queue": "agents",

        # Dead-letter queue — exhausted tasks land here
        "task_queues": {
            **{
                q: {"exchange": q, "routing_key": q}
                for q in ["agents", "outreach", "social", "ingestion", "analytics", "scrape"]
            },
            **{
                f"dlq.{q}": {"exchange": f"dlq.{q}", "routing_key": f"dlq.{q}"}
                for q in ["agents", "outreach", "social", "ingestion", "analytics", "scrape"]
            },
        },

        # Time limits (seconds)
        "task_soft_time_limit": 270,  # 90% of hard limit — allows clean checkpoint
        "task_time_limit": 300,

        # Result expiry
        "result_expires": 3600,  # 1 hour — results aren't long-lived
    }
)


# ── Auto-discover tasks ────────────────────────────────────────────────────────
app.autodiscover_tasks(
    [
        "corpmind.workers.tasks.agents",
        "corpmind.workers.tasks.outreach",
        "corpmind.workers.tasks.analytics",
        "corpmind.workers.tasks.ingestion",
    ]
)


@worker_ready.connect
def on_worker_ready(**kwargs: object) -> None:
    import structlog
    log = structlog.get_logger(__name__)
    log.info("celery.worker_ready")
