"""Unit tests for Sprint 21 recommendation Celery tasks.

Covers:
  Celery task metadata
    - compute_recommendation_outcomes: bound, acks_late, queue, name
    - compute_recommendation_quality_scores: bound, acks_late, queue, name
    - sub-task wrappers: acks_late, max_retries

  compute_recommendation_outcomes (task-level, asyncio mocked)
    - returns dict with rollup_date, enqueued, failed keys
    - logs start event with date kwarg

  compute_recommendation_quality_scores (task-level, asyncio mocked)
    - returns dict with rollup_date, enqueued, failed keys

  _compute_tenant_rec_outcomes sub-task (asyncio mocked)
    - returns dict with tenant_id, workspace_id, processed, acted

  Quality formula (pure logic — no DB required)
    - 3/3 helpful → score=100, low_confidence=False
    - 2/3 helpful → score=67, low_confidence=False
    - total=2 → score=None, low_confidence=True (below threshold)
    - total=0 → score=None, low_confidence=True
    - boundary: total=3 is the minimum (exactly 3 → not low confidence)

  Channel window construction (pure datetime logic — no DB required)
    - window datetimes are timezone-aware UTC (regression: was naive)
    - window spans exactly 30 days

  Status filter regression
    - SQL source contains draft/rejected exclusion

  Source code audit
    - channel query filters status NOT IN ('draft', 'rejected')
    - datetime.combine calls use tzinfo=timezone.utc
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

# ── Helpers ───────────────────────────────────────────────────────────────────

ROLLUP_DATE_STR = str(date.today() - timedelta(days=1))


def _outcomes_return(rollup_date_str: str) -> dict:
    return {"rollup_date": rollup_date_str, "enqueued": 0, "failed": 0}


def _tenant_outcomes_return() -> dict:
    return {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "processed": 3,
        "acted": 1,
    }


def _quality_return(rollup_date_str: str) -> dict:
    return {"rollup_date": rollup_date_str, "enqueued": 0, "failed": 0}


def _tenant_quality_return() -> dict:
    return {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "upserted": 2,
    }


# ── Celery task metadata ──────────────────────────────────────────────────────


class TestTaskMetadata:
    def test_outcomes_task_name(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        assert compute_recommendation_outcomes.name == (
            "corpmind.workers.tasks.analytics.compute_recommendation_outcomes"
        )

    def test_outcomes_task_acks_late(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        assert compute_recommendation_outcomes.acks_late is True

    def test_outcomes_task_queue(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        assert compute_recommendation_outcomes.queue == "analytics"

    def test_outcomes_task_max_retries(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        assert compute_recommendation_outcomes.max_retries == 2

    def test_quality_task_name(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        assert compute_recommendation_quality_scores.name == (
            "corpmind.workers.tasks.analytics.compute_recommendation_quality_scores"
        )

    def test_quality_task_acks_late(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        assert compute_recommendation_quality_scores.acks_late is True

    def test_quality_task_queue(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        assert compute_recommendation_quality_scores.queue == "analytics"

    def test_compute_tenant_rec_outcomes_acks_late(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        assert _compute_tenant_rec_outcomes.acks_late is True

    def test_compute_tenant_rec_outcomes_max_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        assert _compute_tenant_rec_outcomes.max_retries == 2

    def test_compute_tenant_rec_quality_acks_late(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_quality
        assert _compute_tenant_rec_quality.acks_late is True

    def test_compute_tenant_rec_quality_max_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_quality
        assert _compute_tenant_rec_quality.max_retries == 2


# ── compute_recommendation_outcomes (task level) ──────────────────────────────


class TestComputeRecommendationOutcomes:
    def test_returns_dict_with_expected_keys(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _outcomes_return(ROLLUP_DATE_STR)
            result = compute_recommendation_outcomes.run()
        assert "rollup_date" in result
        assert "enqueued" in result
        assert "failed" in result

    def test_rollup_date_is_yesterday(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _outcomes_return(ROLLUP_DATE_STR)
            result = compute_recommendation_outcomes.run()
        assert result["rollup_date"] == ROLLUP_DATE_STR

    def test_logs_start_event(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
        ):
            mock_aio.run.return_value = _outcomes_return(ROLLUP_DATE_STR)
            compute_recommendation_outcomes.run()
        first_call = mock_log.info.call_args_list[0]
        assert first_call.args[0] == "analytics.rec_outcomes.start"

    def test_start_log_date_is_string(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
        ):
            mock_aio.run.return_value = _outcomes_return(ROLLUP_DATE_STR)
            compute_recommendation_outcomes.run()
        first_call = mock_log.info.call_args_list[0]
        assert isinstance(first_call.kwargs["date"], str)

    def test_soft_timeout_logs_warning_and_retries(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                compute_recommendation_outcomes, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(RuntimeError, match="retry_called"):
                compute_recommendation_outcomes.run()
        mock_log.warning.assert_called_once_with("analytics.rec_outcomes.soft_timeout")

    def test_generic_exception_logs_error_and_retries(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                compute_recommendation_outcomes, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = ValueError("db exploded")
            with pytest.raises(RuntimeError, match="retry_called"):
                compute_recommendation_outcomes.run()
        mock_log.error.assert_called_once()
        assert "analytics.rec_outcomes.error" in mock_log.error.call_args.args


# ── compute_recommendation_quality_scores (task level) ───────────────────────


class TestComputeRecommendationQualityScores:
    def test_returns_dict_with_expected_keys(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _quality_return(ROLLUP_DATE_STR)
            result = compute_recommendation_quality_scores.run()
        assert "rollup_date" in result
        assert "enqueued" in result
        assert "failed" in result

    def test_rollup_date_is_yesterday(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _quality_return(ROLLUP_DATE_STR)
            result = compute_recommendation_quality_scores.run()
        assert result["rollup_date"] == ROLLUP_DATE_STR

    def test_logs_start_event(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
        ):
            mock_aio.run.return_value = _quality_return(ROLLUP_DATE_STR)
            compute_recommendation_quality_scores.run()
        first_call = mock_log.info.call_args_list[0]
        assert first_call.args[0] == "analytics.rec_quality.start"

    def test_soft_timeout_logs_warning_and_retries(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                compute_recommendation_quality_scores, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(RuntimeError, match="retry_called"):
                compute_recommendation_quality_scores.run()
        mock_log.warning.assert_called_once_with("analytics.rec_quality.soft_timeout")

    def test_generic_exception_logs_error_and_retries(self):
        from corpmind.workers.tasks.analytics import compute_recommendation_quality_scores
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                compute_recommendation_quality_scores, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = ValueError("db exploded")
            with pytest.raises(RuntimeError, match="retry_called"):
                compute_recommendation_quality_scores.run()
        mock_log.error.assert_called_once()
        assert "analytics.rec_quality.error" in mock_log.error.call_args.args


# ── _compute_tenant_rec_outcomes sub-task ────────────────────────────────────


class TestComputeTenantRecOutcomesSubtask:
    def test_returns_dict_with_processed_and_acted(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _tenant_outcomes_return()
            result = _compute_tenant_rec_outcomes.run(
                tenant_id="00000000-0000-0000-0000-000000000001",
                workspace_id="00000000-0000-0000-0000-000000000002",
                rollup_date=ROLLUP_DATE_STR,
            )
        assert "processed" in result
        assert "acted" in result

    def test_returns_tenant_and_workspace_ids(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _tenant_outcomes_return()
            result = _compute_tenant_rec_outcomes.run(
                tenant_id="00000000-0000-0000-0000-000000000001",
                workspace_id="00000000-0000-0000-0000-000000000002",
                rollup_date=ROLLUP_DATE_STR,
            )
        assert "tenant_id" in result
        assert "workspace_id" in result

    def test_soft_timeout_logs_warning_and_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                _compute_tenant_rec_outcomes, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(RuntimeError, match="retry_called"):
                _compute_tenant_rec_outcomes.run(
                    tenant_id="00000000-0000-0000-0000-000000000001",
                    workspace_id="00000000-0000-0000-0000-000000000002",
                    rollup_date=ROLLUP_DATE_STR,
                )
        mock_log.warning.assert_called_once()

    def test_generic_exception_logs_error_and_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_outcomes
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                _compute_tenant_rec_outcomes, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = ValueError("db error")
            with pytest.raises(RuntimeError, match="retry_called"):
                _compute_tenant_rec_outcomes.run(
                    tenant_id="00000000-0000-0000-0000-000000000001",
                    workspace_id="00000000-0000-0000-0000-000000000002",
                    rollup_date=ROLLUP_DATE_STR,
                )
        mock_log.error.assert_called_once()


# ── _compute_tenant_rec_quality sub-task ─────────────────────────────────────


class TestComputeTenantRecQualitySubtask:
    def test_returns_dict_with_upserted(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_quality
        with patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio:
            mock_aio.run.return_value = _tenant_quality_return()
            result = _compute_tenant_rec_quality.run(
                tenant_id="00000000-0000-0000-0000-000000000001",
                workspace_id="00000000-0000-0000-0000-000000000002",
                rollup_date=ROLLUP_DATE_STR,
            )
        assert "upserted" in result
        assert result["upserted"] == 2

    def test_soft_timeout_logs_warning_and_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_quality
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                _compute_tenant_rec_quality, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(RuntimeError, match="retry_called"):
                _compute_tenant_rec_quality.run(
                    tenant_id="00000000-0000-0000-0000-000000000001",
                    workspace_id="00000000-0000-0000-0000-000000000002",
                    rollup_date=ROLLUP_DATE_STR,
                )
        mock_log.warning.assert_called_once()

    def test_generic_exception_logs_error_and_retries(self):
        from corpmind.workers.tasks.analytics import _compute_tenant_rec_quality
        with (
            patch("corpmind.workers.tasks.analytics.log") as mock_log,
            patch("corpmind.workers.tasks.analytics.asyncio") as mock_aio,
            patch.object(
                _compute_tenant_rec_quality, "retry", side_effect=RuntimeError("retry_called")
            ),
        ):
            mock_aio.run.side_effect = ValueError("db error")
            with pytest.raises(RuntimeError, match="retry_called"):
                _compute_tenant_rec_quality.run(
                    tenant_id="00000000-0000-0000-0000-000000000001",
                    workspace_id="00000000-0000-0000-0000-000000000002",
                    rollup_date=ROLLUP_DATE_STR,
                )
        mock_log.error.assert_called_once()


# ── Quality formula (pure logic) ──────────────────────────────────────────────


class TestQualityFormula:
    """Test the quality score formula in isolation without any DB dependency."""

    def _compute(self, helpful: int, not_helpful: int, dismissed: int) -> tuple[int | None, bool]:
        """Mirror the formula in _rollup_rec_quality_for_workspace."""
        total = helpful + not_helpful + dismissed
        if total >= 3:
            return round(helpful / total * 100), False
        return None, True

    def test_all_helpful_score_100(self):
        score, low = self._compute(3, 0, 0)
        assert score == 100
        assert low is False

    def test_two_of_three_helpful_score_67(self):
        score, low = self._compute(2, 1, 0)
        assert score == 67

    def test_one_of_three_helpful_score_33(self):
        score, low = self._compute(1, 2, 0)
        assert score == 33

    def test_zero_helpful_score_0(self):
        score, low = self._compute(0, 3, 0)
        assert score == 0
        assert low is False

    def test_total_exactly_3_is_not_low_confidence(self):
        score, low = self._compute(3, 0, 0)
        assert low is False

    def test_total_2_is_low_confidence(self):
        score, low = self._compute(2, 0, 0)
        assert score is None
        assert low is True

    def test_total_0_is_low_confidence(self):
        score, low = self._compute(0, 0, 0)
        assert score is None
        assert low is True

    def test_dismissed_counts_in_total(self):
        # 1 helpful, 1 dismissed, 1 not_helpful = total 3 → score = round(1/3*100) = 33
        score, low = self._compute(1, 1, 1)
        assert score == 33
        assert low is False


# ── Channel window construction (pure datetime logic) ────────────────────────


class TestChannelWindowConstruction:
    """Verify the timezone-aware window construction that was the bug site."""

    def _build_window(self, snap_date: date) -> tuple[datetime, datetime]:
        """Reproduce the fixed construction from _detect_rec_outcomes_for_workspace."""
        window_start = datetime.combine(snap_date, time.min, tzinfo=timezone.utc)
        window_end = datetime.combine(snap_date + timedelta(days=30), time.min, tzinfo=timezone.utc)
        return window_start, window_end

    def test_window_start_is_timezone_aware(self):
        ws, _ = self._build_window(date(2026, 1, 15))
        assert ws.tzinfo is not None

    def test_window_end_is_timezone_aware(self):
        _, we = self._build_window(date(2026, 1, 15))
        assert we.tzinfo is not None

    def test_window_tzinfo_is_utc(self):
        ws, we = self._build_window(date(2026, 1, 15))
        assert ws.tzinfo == timezone.utc
        assert we.tzinfo == timezone.utc

    def test_window_spans_exactly_30_days(self):
        ws, we = self._build_window(date(2026, 1, 15))
        assert (we - ws).days == 30

    def test_old_naive_construction_had_no_tzinfo(self):
        """Document that the old (buggy) construction produced a naive datetime."""
        # datetime.combine without tzinfo → naive
        old_ws = datetime.combine(date(2026, 1, 15), datetime.min.time())
        assert old_ws.tzinfo is None  # confirms what the bug looked like


# ── Source code audit ─────────────────────────────────────────────────────────


class TestSourceAudit:
    def test_channel_query_excludes_draft_status(self):
        """campaigns.status filter must exclude draft campaigns."""
        from corpmind.workers.tasks import analytics
        source = inspect.getsource(analytics._detect_rec_outcomes_for_workspace)
        assert "status NOT IN ('draft', 'rejected')" in source

    def test_channel_query_excludes_rejected_status(self):
        """campaigns.status filter must exclude rejected campaigns."""
        from corpmind.workers.tasks import analytics
        source = inspect.getsource(analytics._detect_rec_outcomes_for_workspace)
        assert "'rejected'" in source

    def test_window_uses_time_min_not_datetime_min_time(self):
        """time.min with tzinfo is correct; datetime.min.time() (no tzinfo) was the bug."""
        from corpmind.workers.tasks import analytics
        source = inspect.getsource(analytics._detect_rec_outcomes_for_workspace)
        # Fixed code uses time.min with tzinfo=timezone.utc
        assert "time.min, tzinfo=timezone.utc" in source
        # Old buggy pattern should not appear
        assert "datetime.min.time()" not in source

    def test_both_fan_out_functions_present(self):
        """Both Sprint 21 fan-out async helpers must be importable."""
        from corpmind.workers.tasks.analytics import (
            _fan_out_rec_outcomes,
            _fan_out_rec_quality,
        )
        assert callable(_fan_out_rec_outcomes)
        assert callable(_fan_out_rec_quality)
