"""Unit tests for workers/tasks/analytics.py — compute_daily_rollup, run_campaign_optimizer, prune_semantic_cache."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from corpmind.workers.tasks.analytics import (
    _compute_tenant_rollup,
    compute_daily_rollup,
    prune_semantic_cache,
    run_campaign_optimizer,
)


# ── compute_daily_rollup ───────────────────────────────────────────────────────

def _make_fan_out_return(rollup_date_str: str) -> dict:
    return {"rollup_date": rollup_date_str, "enqueued": 0, "failed": 0}


class TestComputeDailyRollup:
    def test_returns_dict_with_rollup_date(self):
        """Task now fans out and returns a summary dict, not None.

        asyncio.run is mocked so the test does not require a live DB or
        event-loop (the session-scoped asyncpg loop conflicts with asyncio.run).
        """
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _make_fan_out_return(yesterday)
            result = compute_daily_rollup.run()
        assert isinstance(result, dict)
        assert "rollup_date" in result
        assert "enqueued" in result
        assert "failed" in result

    def test_logs_start_event_as_first_call(self):
        """First log call must be the start event with the date kwarg."""
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
        ):
            mock_aio.run.return_value = _make_fan_out_return(yesterday)
            compute_daily_rollup.run()
        assert mock_log.info.call_count >= 1
        first_call = mock_log.info.call_args_list[0]
        assert first_call.args[0] == "analytics.daily_rollup.start"

    def test_log_date_kwarg_is_string(self):
        """The 'date' kwarg in the start log must be a YYYY-MM-DD string."""
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
        ):
            mock_aio.run.return_value = _make_fan_out_return(yesterday)
            compute_daily_rollup.run()
        first_call = mock_log.info.call_args_list[0]
        date_val = first_call.kwargs["date"]
        assert isinstance(date_val, str)
        assert len(date_val) == 10  # YYYY-MM-DD

    def test_rollup_date_is_yesterday(self):
        """Rollup date in the returned dict is yesterday's date string."""
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _make_fan_out_return(yesterday)
            result = compute_daily_rollup.run()
        assert result["rollup_date"] == yesterday


# ── run_campaign_optimizer ─────────────────────────────────────────────────────

class TestRunCampaignOptimizer:
    def test_returns_none(self):
        result = run_campaign_optimizer.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            run_campaign_optimizer.run()
        mock_log.info.assert_called_once_with("analytics.optimizer.start")


# ── WA reply count (Sprint 17B) ───────────────────────────────────────────────

class TestWAReplyCountQuery:
    def test_wa_replied_query_targets_inbox_messages(self):
        """_compute_tenant_rollup source must query inbox_messages for WA replies.

        Sprint 17A had a placeholder 'outreach_replied=0'.  Sprint 17B wires the
        real query.  This test guards against regression back to a hardcoded zero.
        """
        source = inspect.getsource(_compute_tenant_rollup)
        assert "inbox_messages" in source, (
            "WA reply count must query inbox_messages, not use a hardcoded 0"
        )
        assert "reply_intent IS NOT NULL" in source, (
            "WA reply count must filter on reply_intent IS NOT NULL"
        )
        assert "wa_replied" in source, (
            "WA reply count result must be stored in wa_replied variable"
        )

    def test_wa_replied_not_hardcoded_zero(self):
        """Ensure the hardcoded-zero Sprint 17A placeholder is gone."""
        source = inspect.getsource(_compute_tenant_rollup)
        assert "outreach_replied=0" not in source, (
            "Sprint 17B removes the hardcoded-zero placeholder"
        )


# ── prune_semantic_cache ───────────────────────────────────────────────────────

class TestPruneSemanticCache:
    def test_returns_none(self):
        result = prune_semantic_cache.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            prune_semantic_cache.run()
        mock_log.info.assert_called_once_with("ai.cache_prune.start")
