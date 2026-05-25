"""Celery Beat schedule — all autonomous cron-like jobs.

All entries here are version-controlled. No crontab entries outside this file.
Per-tenant timezone is respected inside the task itself (tasks receive the
tenant's org.timezone and compute the local window before executing).

Schedule format: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
"""

from __future__ import annotations

from datetime import timedelta

from celery.schedules import crontab

from corpmind.workers.celery_app import app

app.conf.beat_schedule = {
    # ── Analytics rollup (daily at 01:00 UTC) ─────────────────────────────────
    "analytics.daily_rollup": {
        "task": "corpmind.workers.tasks.analytics.compute_daily_rollup",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "analytics"},
    },

    # ── Campaign optimizer (daily at 02:00 UTC) ────────────────────────────────
    "campaigns.optimizer": {
        "task": "corpmind.workers.tasks.analytics.run_campaign_optimizer",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "analytics"},
    },

    # ── Churn-save segment refresh (daily at 03:00 UTC) ───────────────────────
    "crm.churn_save_refresh": {
        "task": "corpmind.workers.tasks.agents.refresh_churn_save_segments",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "agents"},
    },

    # ── Semantic prompt cache prune (weekly Monday 04:00 UTC) ─────────────────
    "ai.cache_prune": {
        "task": "corpmind.workers.tasks.analytics.prune_semantic_cache",
        "schedule": crontab(day_of_week=1, hour=4, minute=0),
        "options": {"queue": "analytics"},
    },

    # ── HR contact vector refresh (weekly Sunday 05:00 UTC) ───────────────────
    "hr.contact_vector_refresh": {
        "task": "corpmind.workers.tasks.ingestion.refresh_contact_vectors",
        "schedule": crontab(day_of_week=0, hour=5, minute=0),
        "options": {"queue": "ingestion"},
    },

    # ── DLQ reaper (daily at 06:00 UTC) ───────────────────────────────────────
    "celery.dlq_reaper": {
        "task": "corpmind.workers.tasks.agents.reap_dead_letter_queue",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": "agents"},
    },

    # ── Follow-up cadence advancement (every 30 minutes) ──────────────────────
    "outreach.advance_followup_cadence": {
        "task": "corpmind.workers.tasks.outreach.advance_followup_cadence",
        "schedule": timedelta(minutes=30),
        "options": {"queue": "outreach"},
    },
}

app.conf.beat_scheduler = "celery.beat:PersistentScheduler"
