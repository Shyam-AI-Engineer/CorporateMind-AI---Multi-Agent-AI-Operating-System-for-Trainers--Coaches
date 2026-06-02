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
    def test_returns_none(self):
        result = compute_daily_rollup.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            compute_daily_rollup.run()
        mock_log.info.assert_called_once()
        assert mock_log.info.call_args.args[0] == "analytics.daily_rollup.start"

    def test_log_includes_date_kwarg(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            compute_daily_rollup.run()
        call_kwargs = mock_log.info.call_args.kwargs
        assert "date" in call_kwargs

    def test_log_date_is_string(self):
        with patch("corpmind.workers.tasks.analytics.log") as mock_log:
            compute_daily_rollup.run()
        date_val = mock_log.info.call_args.kwargs["date"]
        assert isinstance(date_val, str)
        assert len(date_val) == 10  # YYYY-MM-DD


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
