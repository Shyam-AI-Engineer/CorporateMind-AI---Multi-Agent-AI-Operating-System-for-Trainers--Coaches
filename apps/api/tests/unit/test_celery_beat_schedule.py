"""Unit tests for workers/celery_beat_schedule.py.

Covers:
- Module imports without error (triggers all 6 module-level statements)
- All 9 schedule entries are registered
- Task names match the canonical Celery task registration names
- Cadences: daily crontabs use the correct UTC hour; intervals use the right timedelta
- Queue routing: each job lands on the correct worker queue
- Scheduler backend is PersistentScheduler
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from celery.schedules import crontab

import corpmind.workers.celery_beat_schedule  # noqa: F401 — triggers all module-level stmts
from corpmind.workers.celery_app import app

# Snapshot taken after module load; beat_schedule is module-level state.
_SCHEDULE = app.conf.beat_schedule


# ── Import ─────────────────────────────────────────────────────────────────────

class TestBeatScheduleImport:
    def test_module_imports_without_error(self):
        import corpmind.workers.celery_beat_schedule  # noqa: F401

    def test_persistent_scheduler_configured(self):
        assert app.conf.beat_scheduler == "celery.beat:PersistentScheduler"


# ── Registered entries ─────────────────────────────────────────────────────────

class TestBeatScheduleEntries:
    def test_nine_entries_registered(self):
        assert len(_SCHEDULE) == 9

    def test_analytics_daily_rollup_registered(self):
        assert "analytics.daily_rollup" in _SCHEDULE

    def test_campaigns_optimizer_registered(self):
        assert "campaigns.optimizer" in _SCHEDULE

    def test_churn_save_refresh_registered(self):
        assert "crm.churn_save_refresh" in _SCHEDULE

    def test_cache_prune_registered(self):
        assert "ai.cache_prune" in _SCHEDULE

    def test_hr_contact_vector_refresh_registered(self):
        assert "hr.contact_vector_refresh" in _SCHEDULE

    def test_dlq_reaper_registered(self):
        assert "celery.dlq_reaper" in _SCHEDULE

    def test_advance_followup_cadence_registered(self):
        assert "outreach.advance_followup_cadence" in _SCHEDULE

    def test_social_publisher_registered(self):
        assert "social.publish_scheduled_posts" in _SCHEDULE


# ── Task names ─────────────────────────────────────────────────────────────────

class TestBeatScheduleTaskNames:
    def test_daily_rollup_task_name(self):
        assert _SCHEDULE["analytics.daily_rollup"]["task"] == (
            "corpmind.workers.tasks.analytics.compute_daily_rollup"
        )

    def test_optimizer_task_name(self):
        assert _SCHEDULE["campaigns.optimizer"]["task"] == (
            "corpmind.workers.tasks.analytics.run_campaign_optimizer"
        )

    def test_churn_save_task_name(self):
        assert _SCHEDULE["crm.churn_save_refresh"]["task"] == (
            "corpmind.workers.tasks.agents.refresh_churn_save_segments"
        )

    def test_dlq_reaper_task_name(self):
        assert _SCHEDULE["celery.dlq_reaper"]["task"] == (
            "corpmind.workers.tasks.agents.reap_dead_letter_queue"
        )

    def test_cache_prune_task_name(self):
        assert _SCHEDULE["ai.cache_prune"]["task"] == (
            "corpmind.workers.tasks.analytics.prune_semantic_cache"
        )

    def test_hr_vector_refresh_task_name(self):
        assert _SCHEDULE["hr.contact_vector_refresh"]["task"] == (
            "corpmind.workers.tasks.ingestion.refresh_contact_vectors"
        )

    def test_followup_cadence_task_name(self):
        assert _SCHEDULE["outreach.advance_followup_cadence"]["task"] == (
            "corpmind.workers.tasks.outreach.advance_followup_cadence"
        )

    def test_social_publisher_task_name(self):
        assert _SCHEDULE["social.publish_scheduled_posts"]["task"] == (
            "corpmind.workers.tasks.social.publish_scheduled_posts"
        )


# ── Cadence ────────────────────────────────────────────────────────────────────

class TestBeatScheduleCadence:
    def test_daily_rollup_is_crontab(self):
        assert isinstance(_SCHEDULE["analytics.daily_rollup"]["schedule"], crontab)

    def test_daily_rollup_runs_at_0100_utc(self):
        assert _SCHEDULE["analytics.daily_rollup"]["schedule"] == crontab(hour=1, minute=0)

    def test_optimizer_runs_at_0200_utc(self):
        assert _SCHEDULE["campaigns.optimizer"]["schedule"] == crontab(hour=2, minute=0)

    def test_churn_save_runs_at_0300_utc(self):
        assert _SCHEDULE["crm.churn_save_refresh"]["schedule"] == crontab(hour=3, minute=0)

    def test_cache_prune_runs_weekly_monday(self):
        assert _SCHEDULE["ai.cache_prune"]["schedule"] == crontab(
            day_of_week=1, hour=4, minute=0
        )

    def test_hr_vector_refresh_runs_weekly_sunday(self):
        assert _SCHEDULE["hr.contact_vector_refresh"]["schedule"] == crontab(
            day_of_week=0, hour=5, minute=0
        )

    def test_dlq_reaper_runs_at_0600_utc(self):
        assert _SCHEDULE["celery.dlq_reaper"]["schedule"] == crontab(hour=6, minute=0)

    def test_followup_cadence_runs_every_30_minutes(self):
        assert _SCHEDULE["outreach.advance_followup_cadence"]["schedule"] == timedelta(minutes=30)

    def test_social_publisher_runs_every_15_minutes(self):
        assert _SCHEDULE["social.publish_scheduled_posts"]["schedule"] == timedelta(minutes=15)


# ── Queue routing ──────────────────────────────────────────────────────────────

class TestBeatScheduleQueues:
    def test_analytics_rollup_routes_to_analytics_queue(self):
        assert _SCHEDULE["analytics.daily_rollup"]["options"]["queue"] == "analytics"

    def test_optimizer_routes_to_analytics_queue(self):
        assert _SCHEDULE["campaigns.optimizer"]["options"]["queue"] == "analytics"

    def test_cache_prune_routes_to_analytics_queue(self):
        assert _SCHEDULE["ai.cache_prune"]["options"]["queue"] == "analytics"

    def test_churn_save_routes_to_agents_queue(self):
        assert _SCHEDULE["crm.churn_save_refresh"]["options"]["queue"] == "agents"

    def test_dlq_reaper_routes_to_agents_queue(self):
        assert _SCHEDULE["celery.dlq_reaper"]["options"]["queue"] == "agents"

    def test_followup_cadence_routes_to_outreach_queue(self):
        assert _SCHEDULE["outreach.advance_followup_cadence"]["options"]["queue"] == "outreach"

    def test_social_publisher_routes_to_social_queue(self):
        assert _SCHEDULE["social.publish_scheduled_posts"]["options"]["queue"] == "social"

    def test_hr_vector_refresh_routes_to_ingestion_queue(self):
        assert _SCHEDULE["hr.contact_vector_refresh"]["options"]["queue"] == "ingestion"
