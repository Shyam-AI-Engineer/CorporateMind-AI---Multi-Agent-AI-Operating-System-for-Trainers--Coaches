"""Unit tests for workers/tasks/analytics.py — compute_daily_rollup, run_campaign_optimizer, prune_semantic_cache."""

from __future__ import annotations

from unittest.mock import patch

from corpmind.workers.tasks.analytics import (
    compute_daily_rollup,
    prune_semantic_cache,
    run_campaign_optimizer,
)


# ── compute_daily_rollup ───────────────────────────────────────────────────────

class TestComputeDailyRollup:
    def test_returns_dict_with_rollup_date(self):
        """Task now fans out and returns a summary dict, not None."""
        result = compute_daily_rollup.run()
        assert isinstance(result, dict)
        assert "rollup_date" in result
        assert "enqueued" in result
        assert "failed" in result

    def test_logs_start_event_as_first_call(self):
        """First log call must be the start event with the date kwarg."""
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            compute_daily_rollup.run()
        # info is called at least once (start) — may also log fan_out_complete
        assert mock_log.info.call_count >= 1
        first_call = mock_log.info.call_args_list[0]
        assert first_call.args[0] == "analytics.daily_rollup.start"

    def test_log_date_kwarg_is_string(self):
        """The 'date' kwarg in the start log must be a YYYY-MM-DD string."""
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            compute_daily_rollup.run()
        first_call = mock_log.info.call_args_list[0]
        date_val = first_call.kwargs["date"]
        assert isinstance(date_val, str)
        assert len(date_val) == 10  # YYYY-MM-DD

    def test_rollup_date_is_yesterday(self):
        """Rollup date in the returned dict is yesterday's date string."""
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
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


# ── prune_semantic_cache ───────────────────────────────────────────────────────

class TestPruneSemanticCache:
    def test_returns_none(self):
        result = prune_semantic_cache.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            prune_semantic_cache.run()
        mock_log.info.assert_called_once_with("ai.cache_prune.start")
