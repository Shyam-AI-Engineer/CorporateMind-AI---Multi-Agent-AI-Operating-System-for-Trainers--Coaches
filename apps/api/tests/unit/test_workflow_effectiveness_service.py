"""Unit tests for WorkflowEffectivenessService — Sprint 38.

All tests are synchronous static-method tests or async cache-hit/miss tests.
No database, no real Redis.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.service import (
    WorkflowEffectivenessService,
    _eff_completion_key,
    _eff_duration_key,
    _eff_entities_key,
    _eff_summary_key,
    _eff_templates_key,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_ORG = uuid.uuid4()
_WS = uuid.uuid4()


def _make_ctx(role: str = "owner") -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = _ORG
    ctx.user_id = uuid.uuid4()
    ctx.role = role
    return ctx


def _make_redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> WorkflowEffectivenessService:
    svc = WorkflowEffectivenessService(MagicMock())
    svc._run_repo = MagicMock()
    svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])
    svc._template_repo = MagicMock()
    svc._template_repo.find_all_for_workspace = AsyncMock(return_value=[])
    return svc


def _make_step(
    *,
    status: str = "pending",
    required: bool = True,
    completed_at: datetime | None = None,
    step_order: int = 1,
    title: str = "Step",
) -> MagicMock:
    s = MagicMock()
    s.status = status
    s.required = required
    s.completed_at = completed_at
    s.step_order = step_order
    s.title = title
    return s


def _make_run(
    *,
    status: str = "active",
    days_ago: float = 10,
    completed_days_ago: float | None = None,
    cancelled_days_ago: float | None = None,
    workflow_template_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    steps: list | None = None,
    title: str = "Test Run",
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.title = title
    r.status = status
    r.workflow_template_id = workflow_template_id
    r.entity_type = entity_type
    r.started_at = _NOW - timedelta(days=days_ago)
    r.completed_at = (
        _NOW - timedelta(days=completed_days_ago)
        if completed_days_ago is not None
        else None
    )
    r.cancelled_at = (
        _NOW - timedelta(days=cancelled_days_ago)
        if cancelled_days_ago is not None
        else None
    )
    r.run_steps = steps if steps is not None else []
    return r


# ── Cache key tests ───────────────────────────────────────────────────────────


class TestEffectivenessCacheKeys:
    def test_summary_key_format(self) -> None:
        key = _eff_summary_key(_ORG, _WS)
        assert key.startswith(f"t:{_ORG}:{_WS}:")
        assert "workflow_effectiveness_summary" in key

    def test_templates_key_format(self) -> None:
        key = _eff_templates_key(_ORG, _WS)
        assert "workflow_effectiveness_templates" in key

    def test_entities_key_format(self) -> None:
        key = _eff_entities_key(_ORG, _WS)
        assert "workflow_effectiveness_entities" in key

    def test_duration_key_format(self) -> None:
        key = _eff_duration_key(_ORG, _WS)
        assert "workflow_effectiveness_duration" in key

    def test_completion_key_format(self) -> None:
        key = _eff_completion_key(_ORG, _WS)
        assert "workflow_effectiveness_completion" in key


# ── _compute_summary — empty / baseline ───────────────────────────────────────


class TestComputeSummaryEmpty:
    def test_no_runs_returns_zeros(self) -> None:
        result = WorkflowEffectivenessService._compute_summary([])
        assert result.total_completed == 0
        assert result.average_completion_days == 0.0
        assert result.overall_effectiveness_score == 0.0

    def test_all_cancelled_returns_zero_completed(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=5, cancelled_days_ago=1)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.total_completed == 0

    def test_all_active_returns_zero_completed(self) -> None:
        runs = [_make_run(status="active", days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.total_completed == 0

    def test_no_runs_no_integrity_warning(self) -> None:
        result = WorkflowEffectivenessService._compute_summary([])
        assert result.data_integrity_warning is False

    def test_no_runs_entity_coverage_zero(self) -> None:
        result = WorkflowEffectivenessService._compute_summary([])
        assert result.entity_coverage == 0.0


# ── _compute_summary — completed counts ───────────────────────────────────────


class TestComputeSummaryCompleted:
    def test_total_completed_counts_only_completed(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=20, completed_days_ago=5),
            _make_run(status="active", days_ago=10),
            _make_run(status="cancelled", days_ago=8, cancelled_days_ago=2),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.total_completed == 1

    def test_multiple_completed_counted(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=20, completed_days_ago=15),
            _make_run(status="completed", days_ago=10, completed_days_ago=5),
            _make_run(status="active", days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.total_completed == 2

    def test_average_completion_days_correct(self) -> None:
        # run completed in 5 days (started 10 ago, completed 5 ago)
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert abs(result.average_completion_days - 5.0) < 0.01

    def test_average_completion_days_multiple(self) -> None:
        # run1: 10d start - 6d complete = 4d; run2: 10d start - 4d complete = 6d → avg 5d
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=6),
            _make_run(status="completed", days_ago=10, completed_days_ago=4),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert abs(result.average_completion_days - 5.0) < 0.1

    def test_overall_effectiveness_score_all_completed(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.overall_effectiveness_score == 100.0


# ── _compute_summary — rates ───────────────────────────────────────────────────


class TestComputeSummaryRates:
    def test_fast_rate_run_under_7_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 5 days ≤ 7 → fast
        assert result.fast_completion_rate == 1.0

    def test_fast_rate_run_over_7_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=15, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 10 days > 7 → not fast
        assert result.fast_completion_rate == 0.0

    def test_slow_rate_run_over_30_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=40, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 35 days > 30 → slow
        assert result.slow_completion_rate == 1.0

    def test_slow_rate_run_under_30_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=20, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 15 days ≤ 30 → not slow
        assert result.slow_completion_rate == 0.0

    def test_mixed_fast_slow_rates(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5),   # 5d fast
            _make_run(status="completed", days_ago=40, completed_days_ago=5),   # 35d slow
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.fast_completion_rate == 0.5
        assert result.slow_completion_rate == 0.5

    def test_effectiveness_score_50_percent(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5),
            _make_run(status="active", days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.overall_effectiveness_score == 50.0


# ── _compute_summary — entity coverage ────────────────────────────────────────


class TestComputeSummaryEntityCoverage:
    def test_entity_coverage_all_have_entity(self) -> None:
        runs = [
            _make_run(entity_type="lead"),
            _make_run(entity_type="proposal"),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.entity_coverage == 1.0

    def test_entity_coverage_none_have_entity(self) -> None:
        runs = [_make_run(entity_type=None), _make_run(entity_type=None)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.entity_coverage == 0.0

    def test_entity_coverage_partial(self) -> None:
        runs = [_make_run(entity_type="lead"), _make_run(entity_type=None)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.entity_coverage == 0.5


# ── _compute_summary — integrity ──────────────────────────────────────────────


class TestComputeSummaryIntegrity:
    def test_no_integrity_warning_valid_timestamps(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.data_integrity_warning is False

    def test_integrity_warning_when_completed_before_started(self) -> None:
        # completed_at > started_at → bad: completed 15 days ago, started 10 days ago
        r = _make_run(status="completed", days_ago=10, completed_days_ago=15)
        result = WorkflowEffectivenessService._compute_summary([r])
        assert result.data_integrity_warning is True

    def test_bad_timestamp_excluded_from_duration_avg(self) -> None:
        bad = _make_run(status="completed", days_ago=10, completed_days_ago=15)
        good = _make_run(status="completed", days_ago=10, completed_days_ago=5)
        result = WorkflowEffectivenessService._compute_summary([bad, good])
        # only the good run's duration (5d) contributes
        assert abs(result.average_completion_days - 5.0) < 0.1


# ── _compute_summary — step durations ─────────────────────────────────────────


class TestComputeSummaryAvgSteps:
    def test_avg_step_zero_when_no_completed_steps(self) -> None:
        steps = [_make_step(status="pending")]
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5, steps=steps)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.average_step_completion_days == 0.0

    def test_avg_step_computed_from_completed_step(self) -> None:
        # run started 10 days ago, step completed 5 days ago → 5d from run start
        step = _make_step(
            status="completed",
            completed_at=_NOW - timedelta(days=5),
        )
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=2, steps=[step])]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert abs(result.average_step_completion_days - 5.0) < 0.1

    def test_avg_step_only_from_completed_runs(self) -> None:
        step = _make_step(status="completed", completed_at=_NOW - timedelta(days=3))
        active = _make_run(status="active", days_ago=10, steps=[step])
        result = WorkflowEffectivenessService._compute_summary([active])
        assert result.average_step_completion_days == 0.0

    def test_avg_step_skips_invalid_completed_at(self) -> None:
        # step completed_at before run started_at → invalid, excluded
        run = _make_run(status="completed", days_ago=5, completed_days_ago=1)
        step = _make_step(
            status="completed",
            completed_at=_NOW - timedelta(days=10),  # before run.started_at (5 days ago)
        )
        run.run_steps = [step]
        result = WorkflowEffectivenessService._compute_summary([run])
        assert result.average_step_completion_days == 0.0


# ── _compute_template_effectiveness ───────────────────────────────────────────


class TestComputeTemplateEmpty:
    def test_empty_runs_returns_empty_items(self) -> None:
        result = WorkflowEffectivenessService._compute_template_effectiveness([], {})
        assert result.items == []

    def test_no_template_names_returns_unknown(self) -> None:
        tid = uuid.uuid4()
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5,
                          workflow_template_id=tid)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, {})
        assert result.items[0].template_name == "Unknown"


class TestComputeTemplateData:
    def test_single_template_correct_counts(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "Sales Flow"}
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5,
                      workflow_template_id=tid),
            _make_run(status="active", days_ago=5, workflow_template_id=tid),
        ]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert len(result.items) == 1
        item = result.items[0]
        assert item.template_name == "Sales Flow"
        assert item.runs == 2
        assert item.completed == 1

    def test_template_completion_rate(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5,
                      workflow_template_id=tid),
            _make_run(status="completed", days_ago=10, completed_days_ago=4,
                      workflow_template_id=tid),
            _make_run(status="active", days_ago=5, workflow_template_id=tid),
        ]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        item = result.items[0]
        assert abs(item.completion_rate - (2 / 3)) < 0.001

    def test_template_effectiveness_score(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5,
                          workflow_template_id=tid)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert result.items[0].effectiveness_score == 100.0

    def test_no_template_group_labeled_correctly(self) -> None:
        runs = [_make_run(status="active", days_ago=5, workflow_template_id=None)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, {})
        assert result.items[0].template_name == "No Template"
        assert result.items[0].template_id is None

    def test_sorted_by_effectiveness_desc(self) -> None:
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        names = {str(t1): "Low", str(t2): "High"}
        runs = [
            # t1: 0% completion
            _make_run(status="active", days_ago=5, workflow_template_id=t1),
            # t2: 100% completion
            _make_run(status="completed", days_ago=10, completed_days_ago=5,
                      workflow_template_id=t2),
        ]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert result.items[0].template_name == "High"
        assert result.items[1].template_name == "Low"

    def test_average_duration_only_from_completed(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5,
                      workflow_template_id=tid),
            _make_run(status="active", days_ago=5, workflow_template_id=tid),
        ]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        # Only the completed run (5 days) contributes to average_duration
        assert abs(result.items[0].average_duration - 5.0) < 0.1

    def test_multiple_templates_separate_groups(self) -> None:
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        names = {str(t1): "A", str(t2): "B"}
        runs = [
            _make_run(status="active", days_ago=5, workflow_template_id=t1),
            _make_run(status="completed", days_ago=10, completed_days_ago=5,
                      workflow_template_id=t2),
        ]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert len(result.items) == 2

    def test_average_duration_zero_when_no_valid_timestamps(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        # completed_at before started_at → invalid
        runs = [_make_run(status="completed", days_ago=5, completed_days_ago=10,
                          workflow_template_id=tid)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert result.items[0].average_duration == 0.0


# ── _compute_entity_type_effectiveness ────────────────────────────────────────


class TestComputeEntityEmpty:
    def test_empty_runs_returns_empty_items(self) -> None:
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness([])
        assert result.items == []

    def test_no_entity_type_grouped_as_other(self) -> None:
        runs = [_make_run(entity_type=None, status="active", days_ago=5)]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert len(result.items) == 1
        assert result.items[0].entity_type == "other"


class TestComputeEntityData:
    def test_single_entity_type_correct_count(self) -> None:
        runs = [
            _make_run(entity_type="lead", status="completed", days_ago=10,
                      completed_days_ago=5),
            _make_run(entity_type="lead", status="active", days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert len(result.items) == 1
        assert result.items[0].entity_type == "lead"
        assert result.items[0].workflow_count == 2

    def test_entity_completion_rate(self) -> None:
        runs = [
            _make_run(entity_type="proposal", status="completed", days_ago=10,
                      completed_days_ago=5),
            _make_run(entity_type="proposal", status="active", days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert abs(result.items[0].completion_rate - 0.5) < 0.001

    def test_multiple_entity_types_separated(self) -> None:
        runs = [
            _make_run(entity_type="lead"),
            _make_run(entity_type="campaign"),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert len(result.items) == 2

    def test_sorted_by_effectiveness_desc(self) -> None:
        runs = [
            _make_run(entity_type="lead", status="active"),
            _make_run(entity_type="proposal", status="completed", days_ago=10,
                      completed_days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert result.items[0].entity_type == "proposal"

    def test_average_duration_only_completed_valid(self) -> None:
        runs = [
            _make_run(entity_type="lead", status="completed", days_ago=10,
                      completed_days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert abs(result.items[0].average_duration - 5.0) < 0.1

    def test_entity_no_completed_has_zero_duration(self) -> None:
        runs = [_make_run(entity_type="lead", status="active", days_ago=5)]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert result.items[0].average_duration == 0.0

    def test_effectiveness_score_equals_completion_rate_times_100(self) -> None:
        runs = [
            _make_run(entity_type="lead", status="completed", days_ago=10,
                      completed_days_ago=5),
            _make_run(entity_type="lead", status="active", days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        item = result.items[0]
        assert abs(item.effectiveness_score - item.completion_rate * 100) < 0.01


# ── _compute_duration_impact — bucket labels ──────────────────────────────────


class TestComputeDurationBucketLabels:
    def test_all_five_buckets_present(self) -> None:
        result = WorkflowEffectivenessService._compute_duration_impact([], _NOW)
        labels = [b.label for b in result.buckets]
        assert "0–3 days" in labels
        assert "4–7 days" in labels
        assert "8–14 days" in labels
        assert "15–30 days" in labels
        assert "30+ days" in labels

    def test_bucket_order_preserved(self) -> None:
        result = WorkflowEffectivenessService._compute_duration_impact([], _NOW)
        expected = ["0–3 days", "4–7 days", "8–14 days", "15–30 days", "30+ days"]
        assert [b.label for b in result.buckets] == expected

    def test_bucket_label_for_2_days(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(2.0)
        assert label == "0–3 days"

    def test_bucket_label_for_5_days(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(5.0)
        assert label == "4–7 days"

    def test_bucket_label_for_40_days(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(40.0)
        assert label == "30+ days"


# ── _compute_duration_impact — data ───────────────────────────────────────────


class TestComputeDurationData:
    def test_completed_run_2_days_in_first_bucket(self) -> None:
        runs = [_make_run(status="completed", days_ago=5, completed_days_ago=3)]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "0–3 days")
        assert bucket.completed == 1

    def test_active_run_bucketed_by_days_open(self) -> None:
        # active run started 10 days ago → 8–14 days bucket
        runs = [_make_run(status="active", days_ago=10)]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "8–14 days")
        # It's in the bucket but not completed
        assert bucket.completed == 0
        assert sum(b.completed for b in result.buckets) == 0

    def test_cancelled_run_with_cancelled_at_bucketed(self) -> None:
        # cancelled 2 days after start → 0–3 days bucket
        runs = [_make_run(status="cancelled", days_ago=10, cancelled_days_ago=8)]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "0–3 days")
        # cancelled run is in the bucket but not completed
        assert bucket.completed == 0

    def test_completion_rate_in_bucket(self) -> None:
        # 1 completed + 1 active both in 4–7 day bucket
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5),  # 5d
            _make_run(status="active", days_ago=6),  # 6d open
        ]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "4–7 days")
        assert abs(bucket.completion_rate - 0.5) < 0.001

    def test_average_steps_in_bucket(self) -> None:
        step1 = _make_step(status="completed")
        step2 = _make_step(status="pending")
        run = _make_run(status="completed", days_ago=5, completed_days_ago=3,
                        steps=[step1, step2])
        result = WorkflowEffectivenessService._compute_duration_impact([run], _NOW)
        bucket = next(b for b in result.buckets if b.label == "0–3 days")
        assert abs(bucket.average_steps - 2.0) < 0.01

    def test_empty_bucket_zero_values(self) -> None:
        result = WorkflowEffectivenessService._compute_duration_impact([], _NOW)
        for b in result.buckets:
            assert b.completed == 0
            assert b.completion_rate == 0.0
            assert b.average_steps == 0.0

    def test_effectiveness_score_equals_completion_rate_times_100(self) -> None:
        runs = [_make_run(status="completed", days_ago=5, completed_days_ago=3)]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "0–3 days")
        assert abs(bucket.effectiveness_score - bucket.completion_rate * 100) < 0.01

    def test_run_in_30plus_bucket(self) -> None:
        runs = [_make_run(status="completed", days_ago=40, completed_days_ago=2)]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        bucket = next(b for b in result.buckets if b.label == "30+ days")
        assert bucket.completed == 1

    def test_multiple_runs_in_different_buckets(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=5, completed_days_ago=3),  # 0-3
            _make_run(status="completed", days_ago=10, completed_days_ago=5),  # 4-7
            _make_run(status="completed", days_ago=20, completed_days_ago=5),  # 15-30
        ]
        result = WorkflowEffectivenessService._compute_duration_impact(runs, _NOW)
        total_completed = sum(b.completed for b in result.buckets)
        assert total_completed == 3


# ── _compute_completion_impact — empty ────────────────────────────────────────


class TestComputeCompletionEmpty:
    def test_empty_runs_returns_three_items(self) -> None:
        result = WorkflowEffectivenessService._compute_completion_impact([], _NOW)
        assert len(result.items) == 3

    def test_empty_runs_all_counts_zero(self) -> None:
        result = WorkflowEffectivenessService._compute_completion_impact([], _NOW)
        for item in result.items:
            assert item.count == 0

    def test_empty_statuses_present(self) -> None:
        result = WorkflowEffectivenessService._compute_completion_impact([], _NOW)
        statuses = {item.status for item in result.items}
        assert statuses == {"completed", "cancelled", "active"}


# ── _compute_completion_impact — data ─────────────────────────────────────────


class TestComputeCompletionData:
    def test_completed_count(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=10, completed_days_ago=5),
            _make_run(status="completed", days_ago=8, completed_days_ago=3),
        ]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "completed")
        assert item.count == 2

    def test_cancelled_count(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=5, cancelled_days_ago=1)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "cancelled")
        assert item.count == 1

    def test_active_count_includes_pending(self) -> None:
        runs = [
            _make_run(status="active", days_ago=5),
            _make_run(status="pending", days_ago=3),
        ]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "active")
        assert item.count == 2

    def test_completed_effectiveness_score_100(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "completed")
        assert item.effectiveness_score == 100.0

    def test_cancelled_effectiveness_score_0(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=5, cancelled_days_ago=1)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "cancelled")
        assert item.effectiveness_score == 0.0

    def test_active_effectiveness_score_50(self) -> None:
        runs = [_make_run(status="active", days_ago=5)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "active")
        assert item.effectiveness_score == 50.0

    def test_cancelled_avg_duration_zero(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=5, cancelled_days_ago=1)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "cancelled")
        assert item.average_duration == 0.0

    def test_completed_avg_duration_correct(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=5)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "completed")
        assert abs(item.average_duration - 5.0) < 0.1

    def test_active_avg_duration_uses_now(self) -> None:
        runs = [_make_run(status="active", days_ago=10)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        item = next(i for i in result.items if i.status == "active")
        assert abs(item.average_duration - 10.0) < 0.1


# ── Async cache — get_summary ─────────────────────────────────────────────────


class TestGetSummaryCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self) -> None:
        svc = _make_svc()
        cached_json = (
            '{"total_completed":5,"average_completion_days":4.0,'
            '"average_step_completion_days":2.0,"entity_coverage":0.8,'
            '"fast_completion_rate":0.5,"slow_completion_rate":0.1,'
            '"overall_effectiveness_score":62.5,"data_integrity_warning":false}'
        )
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(cached_json),
            ),
        ):
            result = await svc.get_summary(_WS)
        assert result.total_completed == 5
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(None),
            ),
        ):
            result = await svc.get_summary(_WS)
        assert result.total_completed == 0
        svc._run_repo.find_all_for_workspace.assert_called_once_with(_WS)

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_db(self) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        redis.set = AsyncMock(side_effect=Exception("Redis down"))
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=redis,
            ),
        ):
            result = await svc.get_summary(_WS)
        assert result.total_completed == 0


# ── Async cache — get_template_effectiveness ──────────────────────────────────


class TestGetTemplatesCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self) -> None:
        svc = _make_svc()
        cached_json = '{"items":[]}'
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(cached_json),
            ),
        ):
            result = await svc.get_template_effectiveness(_WS)
        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_both_repos(self) -> None:
        svc = _make_svc()
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(None),
            ),
        ):
            await svc.get_template_effectiveness(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()
        svc._template_repo.find_all_for_workspace.assert_called_once()


# ── Async cache — get_entity_type_effectiveness ───────────────────────────────


class TestGetEntitiesCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached_json = '{"items":[]}'
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(cached_json),
            ),
        ):
            result = await svc.get_entity_type_effectiveness(_WS)
        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(None),
            ),
        ):
            await svc.get_entity_type_effectiveness(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()


# ── Async cache — get_duration_impact ─────────────────────────────────────────


class TestGetDurationCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached_json = (
            '{"buckets":[{"label":"0–3 days","completed":0,"completion_rate":0.0,'
            '"average_steps":0.0,"effectiveness_score":0.0},'
            '{"label":"4–7 days","completed":0,"completion_rate":0.0,'
            '"average_steps":0.0,"effectiveness_score":0.0},'
            '{"label":"8–14 days","completed":0,"completion_rate":0.0,'
            '"average_steps":0.0,"effectiveness_score":0.0},'
            '{"label":"15–30 days","completed":0,"completion_rate":0.0,'
            '"average_steps":0.0,"effectiveness_score":0.0},'
            '{"label":"30+ days","completed":0,"completion_rate":0.0,'
            '"average_steps":0.0,"effectiveness_score":0.0}]}'
        )
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(cached_json),
            ),
        ):
            result = await svc.get_duration_impact(_WS)
        assert len(result.buckets) == 5
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(None),
            ),
        ):
            result = await svc.get_duration_impact(_WS)
        assert len(result.buckets) == 5
        svc._run_repo.find_all_for_workspace.assert_called_once()


# ── Async cache — get_completion_impact ───────────────────────────────────────


class TestGetCompletionCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached_json = (
            '{"items":['
            '{"status":"completed","count":0,"average_duration":0.0,"effectiveness_score":100.0},'
            '{"status":"cancelled","count":0,"average_duration":0.0,"effectiveness_score":0.0},'
            '{"status":"active","count":0,"average_duration":0.0,"effectiveness_score":50.0}]}'
        )
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(cached_json),
            ),
        ):
            result = await svc.get_completion_impact(_WS)
        assert len(result.items) == 3
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        with (
            patch(
                "corpmind.modules.workflows.service.get_tenant_context",
                return_value=_make_ctx(),
            ),
            patch(
                "corpmind.modules.workflows.service.get_redis",
                return_value=_make_redis(None),
            ),
        ):
            result = await svc.get_completion_impact(_WS)
        assert len(result.items) == 3


# ── Tenant isolation ──────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_summary_key_differs_by_org(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        assert _eff_summary_key(org_a, _WS) != _eff_summary_key(org_b, _WS)

    def test_summary_key_differs_by_workspace(self) -> None:
        ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
        assert _eff_summary_key(_ORG, ws_a) != _eff_summary_key(_ORG, ws_b)

    def test_templates_key_differs_by_org(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        assert _eff_templates_key(org_a, _WS) != _eff_templates_key(org_b, _WS)

    def test_entities_key_differs_by_workspace(self) -> None:
        ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
        assert _eff_entities_key(_ORG, ws_a) != _eff_entities_key(_ORG, ws_b)

    def test_duration_key_differs_by_org(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        assert _eff_duration_key(org_a, _WS) != _eff_duration_key(org_b, _WS)


# ── Edge cases — summary ──────────────────────────────────────────────────────


class TestEdgeCasesSummary:
    def test_completed_without_completed_at_excluded(self) -> None:
        r = _make_run(status="completed", days_ago=10)
        r.completed_at = None  # no completed_at despite status=completed
        result = WorkflowEffectivenessService._compute_summary([r])
        assert result.total_completed == 0

    def test_fast_rate_exact_boundary_7_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=10, completed_days_ago=3)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 7.0 exactly → ≤7 → fast
        assert result.fast_completion_rate == 1.0

    def test_slow_rate_exact_boundary_30_days(self) -> None:
        runs = [_make_run(status="completed", days_ago=31, completed_days_ago=1)]
        result = WorkflowEffectivenessService._compute_summary(runs)
        # duration = 30.0 exactly → NOT > 30 → not slow
        assert result.slow_completion_rate == 0.0

    def test_all_runs_have_entity(self) -> None:
        runs = [
            _make_run(entity_type="lead"),
            _make_run(entity_type="proposal"),
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.entity_coverage == 1.0

    def test_fast_and_slow_rates_sum_leq_1(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=5, completed_days_ago=2),   # fast
            _make_run(status="completed", days_ago=35, completed_days_ago=2),  # slow
            _make_run(status="completed", days_ago=20, completed_days_ago=5),  # neither
        ]
        result = WorkflowEffectivenessService._compute_summary(runs)
        assert result.fast_completion_rate + result.slow_completion_rate <= 1.0


# ── Edge cases — template ─────────────────────────────────────────────────────


class TestEdgeCasesTemplate:
    def test_template_with_all_active_runs_zero_score(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        runs = [_make_run(status="active", days_ago=5, workflow_template_id=tid)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert result.items[0].effectiveness_score == 0.0

    def test_template_id_preserved_in_output(self) -> None:
        tid = uuid.uuid4()
        names = {str(tid): "T1"}
        runs = [_make_run(status="active", days_ago=5, workflow_template_id=tid)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, names)
        assert result.items[0].template_id == str(tid)

    def test_null_template_id_in_output(self) -> None:
        runs = [_make_run(status="active", days_ago=5, workflow_template_id=None)]
        result = WorkflowEffectivenessService._compute_template_effectiveness(runs, {})
        assert result.items[0].template_id is None


# ── Edge cases — entity ───────────────────────────────────────────────────────


class TestEdgeCasesEntity:
    def test_mixed_none_and_typed_entity(self) -> None:
        runs = [
            _make_run(entity_type="lead"),
            _make_run(entity_type=None),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        types = {i.entity_type for i in result.items}
        assert "lead" in types
        assert "other" in types

    def test_entity_workflow_count(self) -> None:
        runs = [
            _make_run(entity_type="campaign"),
            _make_run(entity_type="campaign"),
            _make_run(entity_type="campaign"),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        item = result.items[0]
        assert item.workflow_count == 3

    def test_entity_all_completed_score_100(self) -> None:
        runs = [
            _make_run(entity_type="training", status="completed", days_ago=10,
                      completed_days_ago=5),
        ]
        result = WorkflowEffectivenessService._compute_entity_type_effectiveness(runs)
        assert result.items[0].effectiveness_score == 100.0


# ── Edge cases — completion ───────────────────────────────────────────────────


class TestEdgeCasesCompletion:
    def test_invalid_completed_at_excluded_from_avg(self) -> None:
        # completed_at < started_at → excluded from avg
        run = _make_run(status="completed", days_ago=5, completed_days_ago=10)
        result = WorkflowEffectivenessService._compute_completion_impact([run], _NOW)
        item = next(i for i in result.items if i.status == "completed")
        assert item.average_duration == 0.0

    def test_completed_at_none_excluded_from_avg(self) -> None:
        run = _make_run(status="completed", days_ago=10)
        run.completed_at = None
        result = WorkflowEffectivenessService._compute_completion_impact([run], _NOW)
        item = next(i for i in result.items if i.status == "completed")
        # run is still counted in the group; only duration is excluded
        assert item.average_duration == 0.0
        assert item.count == 1

    def test_pending_status_grouped_as_active(self) -> None:
        runs = [_make_run(status="pending", days_ago=5)]
        result = WorkflowEffectivenessService._compute_completion_impact(runs, _NOW)
        active_item = next(i for i in result.items if i.status == "active")
        assert active_item.count == 1


# ── Boundary conditions — duration buckets ────────────────────────────────────


class TestBoundaryDurationBuckets:
    def test_exactly_3_days_in_first_bucket(self) -> None:
        # 3.0 < 4 → "0–3 days"
        label = WorkflowEffectivenessService._bucket_label(3.0)
        assert label == "0–3 days"

    def test_exactly_4_days_in_second_bucket(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(4.0)
        assert label == "4–7 days"

    def test_exactly_14_days_in_third_bucket(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(14.0)
        assert label == "8–14 days"

    def test_exactly_31_days_in_last_bucket(self) -> None:
        label = WorkflowEffectivenessService._bucket_label(31.0)
        assert label == "30+ days"
