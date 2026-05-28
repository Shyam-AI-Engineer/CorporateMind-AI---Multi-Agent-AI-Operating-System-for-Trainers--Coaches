"""Social post scheduling task.

Phase 1 stub — channel adapters (IG, FB, TG, LinkedIn) are not yet wired.
This task is registered so the beat schedule does not produce 'unknown task'
errors.  Implement the publish loop here when a channel adapter is added.
"""

from __future__ import annotations

import structlog

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    name="corpmind.workers.tasks.social.publish_scheduled_posts",
    queue="social",
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=240,
    time_limit=300,
    ignore_result=True,
)
def publish_scheduled_posts(self: object) -> None:  # type: ignore[type-arg]
    """Publish social_posts rows whose scheduled_at is past and status='scheduled'.

    No-op until a channel adapter is registered.  When implemented:
    1. Query social_posts WHERE status='scheduled' AND scheduled_at <= NOW().
    2. For each post, call the appropriate channel adapter.
    3. Update status to 'published' or 'failed'.
    """
    log.info("social.publish_scheduled_posts.noop")
