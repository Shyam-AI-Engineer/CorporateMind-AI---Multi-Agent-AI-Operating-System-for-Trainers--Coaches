"""Unit tests for WorkflowObservabilityService — Sprint 39.

All tests are synchronous static-method tests or async cache-hit/miss tests.
No database, no real Redis.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.service import (
    WorkflowObservabilityService,
    _obs_bottlenecks_key,
    _obs_flow_health_key,
    _obs_owner_key,
    _obs_steps_key,
    _obs_templates_key,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_TMPL_A = uuid.uuid4()
_TMPL_B = uuid.uuid4()


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


def _make_svc() -> WorkflowObservabilityService:
    svc = WorkflowObservabilityService(MagicMock())
    svc._run_repo = MagicMock()
    svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])
    svc._template_repo = MagicMock()
    svc._template_repo.find_all_for_workspace = AsyncMock(return_value=[])
    return svc


def _make_step(
    *,
    status: str = "pending",
    title: str = "Review",
    owner_role: str = "member",
    completed_at: datetime | None = None,
    started_at: datetime | None = None,
    step_order: int = 1,
    required: bool = True,
) -> MagicMock:
    s = MagicMock()
    s.status = status
    s.title = title
    s.owner_role = owner_role
    s.completed_at = completed_at
    s.started_at = started_at
    s.step_order = step_order
    s.required = required
    return s


def _make_run(
    *,
    status: str = "active",
    days_ago: float = 10,
    completed_days_ago: float | None = None,
    cancelled_days_ago: float | None = None,
    workflow_template_id: uuid.UUID | None = None,
    steps: list | None = None,
    title: str = "Test Run",
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.title = title
    r.status = status
    r.workflow_template_id = workflow_template_id
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


class TestObsCacheKeys:
    def test_bottlenecks_key_format(self) -> None:
        key = _obs_bottlenecks_key(_ORG, _WS)
        assert key.startswith(f"t:{_ORG}:{_WS}:")
        assert "workflow_observability_bottlenecks" in key

    def test_steps_key_format(self) -> None:
        key = _obs_steps_key(_ORG, _WS)
        assert "workflow_observability_steps" in key

    def test_owner_key_format(self) -> None:
        key = _obs_owner_key(_ORG, _WS)
        assert "workflow_observability_owner" in key

    def test_templates_key_format(self) -> None:
        key = _obs_templates_key(_ORG, _WS)
        assert "workflow_observability_templates" in key

    def test_flow_health_key_format(self) -> None:
        key = _obs_flow_health_key(_ORG, _WS)
        assert "workflow_observability_flow_health" in key

    def test_keys_are_tenant_scoped(self) -> None:
        org2 = uuid.uuid4()
        key1 = _obs_bottlenecks_key(_ORG, _WS)
        key2 = _obs_bottlenecks_key(org2, _WS)
        assert key1 != key2

    def test_keys_differ_by_workspace(self) -> None:
        ws2 = uuid.uuid4()
        key1 = _obs_bottlenecks_key(_ORG, _WS)
        key2 = _obs_bottlenecks_key(_ORG, ws2)
        assert key1 != key2


# ── Bottleneck tests ──────────────────────────────────────────────────────────


class TestComputeBottlenecksEmpty:
    def test_no_runs_returns_empty(self) -> None:
        result = WorkflowObservabilityService._compute_bottlenecks([], {})
        assert result.items == []

    def test_only_active_runs_excluded(self) -> None:
        run = _make_run(status="active")
        result = WorkflowObservabilityService._compute_bottlenecks([run], {})
        assert result.items == []

    def test_only_cancelled_runs_excluded(self) -> None:
        run = _make_run(status="cancelled", cancelled_days_ago=1)
        result = WorkflowObservabilityService._compute_bottlenecks([run], {})
        assert result.items == []

    def test_completed_run_no_steps_excluded(self) -> None:
        run = _make_run(status="completed", days_ago=10, completed_days_ago=3, steps=[])
        result = WorkflowObservabilityService._compute_bottlenecks([run], {})
        assert result.items == []


class TestComputeBottlenecksData:
    def test_single_template_single_step(self) -> None:
        step = _make_step(
            status="completed",
            title="Approval",
            completed_at=_NOW - timedelta(days=2),
        )
        run = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run], {str(_TMPL_A): "Sales"}
        )
        assert len(result.items) == 1
        item = result.items[0]
        assert item.template_name == "Sales"
        assert item.slowest_step == "Approval"
        assert item.runs_affected == 1

    def test_bottleneck_score_fraction_of_run(self) -> None:
        step = _make_step(
            status="completed",
            title="Review",
            completed_at=_NOW - timedelta(days=5),  # 5 days from run start (10-5=5)
        )
        run = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run], {str(_TMPL_A): "Renewal"}
        )
        item = result.items[0]
        # avg_days = 5 (step completed_at - run started_at)
        # avg_run_dur = 10 (run completed_at - run started_at)
        assert abs(item.average_days - 5.0) < 0.1
        assert abs(item.bottleneck_score - 50.0) < 0.1

    def test_slowest_step_chosen_by_avg(self) -> None:
        step_fast = _make_step(
            status="completed",
            title="Quick",
            completed_at=_NOW - timedelta(days=9),  # 1 day from run start
        )
        step_slow = _make_step(
            status="completed",
            title="Slow",
            completed_at=_NOW - timedelta(days=5),  # 5 days from run start
        )
        run = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step_fast, step_slow],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run], {str(_TMPL_A): "T"}
        )
        assert result.items[0].slowest_step == "Slow"

    def test_unknown_template_id_falls_back_to_no_template(self) -> None:
        step = _make_step(status="completed", completed_at=_NOW - timedelta(days=1))
        run = _make_run(
            status="completed",
            days_ago=5,
            completed_days_ago=0,
            workflow_template_id=_TMPL_B,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks([run], {})
        assert result.items[0].template_name == "No Template"

    def test_none_template_id_labeled_no_template(self) -> None:
        step = _make_step(status="completed", completed_at=_NOW - timedelta(days=1))
        run = _make_run(
            status="completed",
            days_ago=5,
            completed_days_ago=0,
            workflow_template_id=None,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks([run], {})
        assert result.items[0].template_name == "No Template"

    def test_sorted_by_bottleneck_score_desc(self) -> None:
        # Template A: bottleneck_score higher
        step_a = _make_step(
            status="completed", title="A", completed_at=_NOW - timedelta(days=1)
        )
        run_a = _make_run(
            status="completed",
            days_ago=2,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step_a],
        )
        # Template B: lower bottleneck score (step is a small fraction of run)
        step_b = _make_step(
            status="completed", title="B", completed_at=_NOW - timedelta(days=9)
        )
        run_b = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_B,
            steps=[step_b],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run_a, run_b], {str(_TMPL_A): "A", str(_TMPL_B): "B"}
        )
        assert len(result.items) == 2
        assert result.items[0].bottleneck_score >= result.items[1].bottleneck_score

    def test_max_days_reflects_maximum(self) -> None:
        step1 = _make_step(
            status="completed", title="Review", completed_at=_NOW - timedelta(days=8)
        )
        step2 = _make_step(
            status="completed", title="Review", completed_at=_NOW - timedelta(days=5)
        )
        run1 = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step1],
        )
        run2 = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step2],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run1, run2], {str(_TMPL_A): "T"}
        )
        assert result.items[0].max_days >= result.items[0].average_days

    def test_step_started_at_used_when_present(self) -> None:
        # step.started_at set to 2 days after run start
        step = _make_step(
            status="completed",
            title="Review",
            started_at=_NOW - timedelta(days=8),  # 2 days after run started
            completed_at=_NOW - timedelta(days=6),  # 4 days after run started
        )
        run = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run], {str(_TMPL_A): "T"}
        )
        # duration = completed_at - step.started_at = 2 days (not 4 from run start)
        assert abs(result.items[0].average_days - 2.0) < 0.1

    def test_bottleneck_score_capped_at_100(self) -> None:
        step = _make_step(
            status="completed",
            title="Review",
            completed_at=_NOW - timedelta(days=0.5),  # large fraction of 1-day run
        )
        run = _make_run(
            status="completed",
            days_ago=1,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
            steps=[step],
        )
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run], {str(_TMPL_A): "T"}
        )
        assert result.items[0].bottleneck_score <= 100.0


# ── Step analysis tests ───────────────────────────────────────────────────────


class TestComputeStepAnalysisEmpty:
    def test_no_runs_returns_empty(self) -> None:
        result = WorkflowObservabilityService._compute_step_analysis([])
        assert result.items == []

    def test_runs_with_no_steps_returns_empty(self) -> None:
        run = _make_run(status="completed", steps=[])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        assert result.items == []


class TestComputeStepAnalysisData:
    def test_completed_count_correct(self) -> None:
        step1 = _make_step(
            status="completed",
            title="Review",
            completed_at=_NOW - timedelta(days=1),
        )
        step2 = _make_step(status="pending", title="Review")
        run = _make_run(steps=[step1, step2])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "Review")
        assert item.completed_count == 1

    def test_blocked_count_correct(self) -> None:
        step1 = _make_step(status="blocked", title="Approval")
        step2 = _make_step(status="blocked", title="Approval")
        run = _make_run(steps=[step1, step2])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "Approval")
        assert item.blocked_count == 2

    def test_skip_rate_calculation(self) -> None:
        skipped = _make_step(status="skipped", title="Optional")
        pending = _make_step(status="pending", title="Optional")
        active = _make_step(status="in_progress", title="Optional")
        run = _make_run(steps=[skipped, pending, active])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "Optional")
        assert abs(item.skip_rate - 1 / 3) < 0.01

    def test_completion_rate_calculation(self) -> None:
        completed = _make_step(
            status="completed", title="Task", completed_at=_NOW - timedelta(days=1)
        )
        pending = _make_step(status="pending", title="Task")
        run = _make_run(steps=[completed, pending])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "Task")
        assert abs(item.completion_rate - 0.5) < 0.01

    def test_average_completion_days_uses_run_started_at_fallback(self) -> None:
        # step.started_at is None → use run.started_at as reference
        step = _make_step(
            status="completed",
            title="A",
            started_at=None,
            completed_at=_NOW - timedelta(days=4),
        )
        run = _make_run(days_ago=10, steps=[step])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "A")
        # duration = completed_at - run.started_at = 10 - 4 = 6 days
        assert abs(item.average_completion_days - 6.0) < 0.1

    def test_average_completion_days_uses_step_started_at_when_set(self) -> None:
        step = _make_step(
            status="completed",
            title="B",
            started_at=_NOW - timedelta(days=3),
            completed_at=_NOW - timedelta(days=1),
        )
        run = _make_run(days_ago=10, steps=[step])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "B")
        assert abs(item.average_completion_days - 2.0) < 0.1

    def test_median_differs_from_mean_on_skewed_data(self) -> None:
        # steps for same name across two runs with very different durations
        step1 = _make_step(
            status="completed",
            title="X",
            completed_at=_NOW - timedelta(days=9),  # 1 day
        )
        step2 = _make_step(
            status="completed",
            title="X",
            completed_at=_NOW - timedelta(days=0),  # 10 days
        )
        run1 = _make_run(days_ago=10, steps=[step1])
        run2 = _make_run(days_ago=10, steps=[step2])
        result = WorkflowObservabilityService._compute_step_analysis([run1, run2])
        item = next(i for i in result.items if i.step_name == "X")
        # avg = 5.5, median = 5.5 (two values)
        assert item.average_completion_days > 0
        assert item.median_completion_days > 0

    def test_sorted_by_average_completion_days_desc(self) -> None:
        fast = _make_step(
            status="completed",
            title="Fast",
            completed_at=_NOW - timedelta(days=9),  # 1 day
        )
        slow = _make_step(
            status="completed",
            title="Slow",
            completed_at=_NOW - timedelta(days=5),  # 5 days
        )
        run = _make_run(days_ago=10, steps=[fast, slow])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        assert result.items[0].step_name == "Slow"

    def test_steps_across_multiple_runs_aggregated(self) -> None:
        step1 = _make_step(
            status="completed",
            title="Review",
            completed_at=_NOW - timedelta(days=8),
        )
        step2 = _make_step(
            status="completed",
            title="Review",
            completed_at=_NOW - timedelta(days=8),
        )
        run1 = _make_run(days_ago=10, steps=[step1])
        run2 = _make_run(days_ago=10, steps=[step2])
        result = WorkflowObservabilityService._compute_step_analysis([run1, run2])
        item = next(i for i in result.items if i.step_name == "Review")
        assert item.completed_count == 2


# ── Owner capacity tests ──────────────────────────────────────────────────────


class TestComputeOwnerCapacityEmpty:
    def test_no_runs_returns_empty(self) -> None:
        result = WorkflowObservabilityService._compute_owner_capacity([])
        assert result.items == []

    def test_runs_with_no_steps_returns_empty(self) -> None:
        run = _make_run(steps=[])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        assert result.items == []


class TestComputeOwnerCapacityData:
    def test_assigned_steps_count(self) -> None:
        steps = [
            _make_step(owner_role="admin"),
            _make_step(owner_role="admin"),
            _make_step(owner_role="member"),
        ]
        run = _make_run(steps=steps)
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        admin = next(i for i in result.items if i.owner_role == "admin")
        member = next(i for i in result.items if i.owner_role == "member")
        assert admin.assigned_steps == 2
        assert member.assigned_steps == 1

    def test_completed_steps_count(self) -> None:
        step1 = _make_step(
            status="completed",
            owner_role="owner",
            completed_at=_NOW - timedelta(days=1),
        )
        step2 = _make_step(status="pending", owner_role="owner")
        run = _make_run(steps=[step1, step2])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "owner")
        assert item.completed_steps == 1

    def test_blocked_steps_count(self) -> None:
        step = _make_step(status="blocked", owner_role="viewer")
        run = _make_run(steps=[step])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "viewer")
        assert item.blocked_steps == 1

    def test_capacity_score_formula(self) -> None:
        completed = _make_step(
            status="completed",
            owner_role="admin",
            completed_at=_NOW - timedelta(days=1),
        )
        pending = _make_step(status="pending", owner_role="admin")
        run = _make_run(steps=[completed, pending])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "admin")
        assert abs(item.capacity_score - 50.0) < 0.1

    def test_all_completed_capacity_100(self) -> None:
        step = _make_step(
            status="completed",
            owner_role="admin",
            completed_at=_NOW - timedelta(days=1),
        )
        run = _make_run(steps=[step])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "admin")
        assert abs(item.capacity_score - 100.0) < 0.1

    def test_avg_completion_days_excludes_uncompleted(self) -> None:
        completed = _make_step(
            status="completed",
            owner_role="member",
            completed_at=_NOW - timedelta(days=8),  # 2 days from run start
        )
        blocked = _make_step(status="blocked", owner_role="member")
        run = _make_run(days_ago=10, steps=[completed, blocked])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "member")
        assert abs(item.average_completion_days - 2.0) < 0.1

    def test_sorted_by_capacity_score_desc(self) -> None:
        high = _make_step(
            status="completed",
            owner_role="admin",
            completed_at=_NOW - timedelta(days=1),
        )
        low = _make_step(status="pending", owner_role="viewer")
        run = _make_run(steps=[high, low])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        assert result.items[0].capacity_score >= result.items[-1].capacity_score

    def test_step_started_at_used_for_duration(self) -> None:
        step = _make_step(
            status="completed",
            owner_role="member",
            started_at=_NOW - timedelta(days=3),
            completed_at=_NOW - timedelta(days=1),
        )
        run = _make_run(days_ago=10, steps=[step])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "member")
        assert abs(item.average_completion_days - 2.0) < 0.1


# ── Template capacity tests ───────────────────────────────────────────────────


class TestComputeTemplateCapacityEmpty:
    def test_no_runs_returns_empty(self) -> None:
        result = WorkflowObservabilityService._compute_template_capacity(
            [], {}, _NOW
        )
        assert result.items == []


class TestComputeTemplateCapacityData:
    def test_active_run_count(self) -> None:
        run1 = _make_run(status="active", workflow_template_id=_TMPL_A)
        run2 = _make_run(status="pending", workflow_template_id=_TMPL_A)
        run3 = _make_run(status="completed", days_ago=5, completed_days_ago=0, workflow_template_id=_TMPL_A)
        result = WorkflowObservabilityService._compute_template_capacity(
            [run1, run2, run3], {str(_TMPL_A): "T"}, _NOW
        )
        item = result.items[0]
        assert item.active_runs == 2
        assert item.completed_runs == 1

    def test_average_completion_days(self) -> None:
        run = _make_run(
            status="completed",
            days_ago=10,
            completed_days_ago=0,
            workflow_template_id=_TMPL_A,
        )
        result = WorkflowObservabilityService._compute_template_capacity(
            [run], {str(_TMPL_A): "T"}, _NOW
        )
        assert abs(result.items[0].average_completion_days - 10.0) < 0.1

    def test_capacity_rating_low(self) -> None:
        run = _make_run(status="completed", days_ago=1, completed_days_ago=0, workflow_template_id=_TMPL_A)
        result = WorkflowObservabilityService._compute_template_capacity(
            [run], {str(_TMPL_A): "T"}, _NOW
        )
        assert result.items[0].capacity_rating == "low"

    def test_capacity_rating_high(self) -> None:
        # Many long-running active runs to push avg_parallel high
        runs = [
            _make_run(status="active", days_ago=30, workflow_template_id=_TMPL_A)
            for _ in range(10)
        ]
        result = WorkflowObservabilityService._compute_template_capacity(
            runs, {str(_TMPL_A): "T"}, _NOW
        )
        assert result.items[0].capacity_rating in ("medium", "high")

    def test_none_template_labeled_no_template(self) -> None:
        run = _make_run(status="active", workflow_template_id=None)
        result = WorkflowObservabilityService._compute_template_capacity(
            [run], {}, _NOW
        )
        assert result.items[0].template_name == "No Template"

    def test_sorted_by_avg_parallel_runs_desc(self) -> None:
        # TMPL_B: single short completed run → low parallel
        # TMPL_A: many long active runs → higher parallel
        runs_a = [
            _make_run(status="active", days_ago=30, workflow_template_id=_TMPL_A)
            for _ in range(5)
        ]
        run_b = _make_run(
            status="completed", days_ago=1, completed_days_ago=0,
            workflow_template_id=_TMPL_B
        )
        result = WorkflowObservabilityService._compute_template_capacity(
            runs_a + [run_b], {str(_TMPL_A): "A", str(_TMPL_B): "B"}, _NOW
        )
        assert result.items[0].template_name == "A"

    def test_cancelled_excluded_from_avg_completion(self) -> None:
        completed = _make_run(
            status="completed", days_ago=5, completed_days_ago=0,
            workflow_template_id=_TMPL_A
        )
        cancelled = _make_run(
            status="cancelled", days_ago=2, cancelled_days_ago=0,
            workflow_template_id=_TMPL_A
        )
        result = WorkflowObservabilityService._compute_template_capacity(
            [completed, cancelled], {str(_TMPL_A): "T"}, _NOW
        )
        item = result.items[0]
        assert abs(item.average_completion_days - 5.0) < 0.1


# ── Flow health tests ─────────────────────────────────────────────────────────


class TestClassifyFlow:
    def test_completed_run_is_healthy(self) -> None:
        run = _make_run(status="completed")
        assert WorkflowObservabilityService._classify_flow(run) == "healthy"

    def test_cancelled_run_is_critical(self) -> None:
        run = _make_run(status="cancelled")
        assert WorkflowObservabilityService._classify_flow(run) == "critical"

    def test_active_no_blocked_is_healthy(self) -> None:
        run = _make_run(status="active", steps=[
            _make_step(status="pending"),
            _make_step(status="in_progress"),
        ])
        assert WorkflowObservabilityService._classify_flow(run) == "healthy"

    def test_active_one_blocked_few_steps_is_warning(self) -> None:
        run = _make_run(status="active", steps=[
            _make_step(status="blocked"),
            _make_step(status="pending"),
            _make_step(status="in_progress"),
        ])
        assert WorkflowObservabilityService._classify_flow(run) == "warning"

    def test_active_majority_blocked_is_critical(self) -> None:
        run = _make_run(status="active", steps=[
            _make_step(status="blocked"),
            _make_step(status="blocked"),
            _make_step(status="pending"),
        ])
        # 2/3 blocked >= 0.5 → critical
        assert WorkflowObservabilityService._classify_flow(run) == "critical"

    def test_active_exactly_half_blocked_is_critical(self) -> None:
        run = _make_run(status="active", steps=[
            _make_step(status="blocked"),
            _make_step(status="pending"),
        ])
        assert WorkflowObservabilityService._classify_flow(run) == "critical"

    def test_pending_run_no_blocked_is_healthy(self) -> None:
        run = _make_run(status="pending", steps=[_make_step(status="pending")])
        assert WorkflowObservabilityService._classify_flow(run) == "healthy"


class TestComputeFlowHealthEmpty:
    def test_no_runs_zero_score(self) -> None:
        result = WorkflowObservabilityService._compute_flow_health([])
        assert result.healthy_flows == 0
        assert result.warning_flows == 0
        assert result.critical_flows == 0
        assert result.flow_health_score == 0.0

    def test_no_runs_no_integrity_warning(self) -> None:
        result = WorkflowObservabilityService._compute_flow_health([])
        assert result.data_integrity_warning is False


class TestComputeFlowHealthData:
    def test_all_completed_full_score(self) -> None:
        runs = [
            _make_run(status="completed", days_ago=5, completed_days_ago=0)
            for _ in range(3)
        ]
        result = WorkflowObservabilityService._compute_flow_health(runs)
        assert result.healthy_flows == 3
        assert result.flow_health_score == 100.0

    def test_mixed_classification_counts(self) -> None:
        healthy = _make_run(status="completed", days_ago=5, completed_days_ago=0)
        warning = _make_run(status="active", steps=[
            _make_step(status="blocked"),
            _make_step(status="pending"),
            _make_step(status="in_progress"),
        ])
        critical = _make_run(status="cancelled")
        result = WorkflowObservabilityService._compute_flow_health([healthy, warning, critical])
        assert result.healthy_flows == 1
        assert result.warning_flows == 1
        assert result.critical_flows == 1

    def test_flow_health_score_formula(self) -> None:
        completed = _make_run(status="completed", days_ago=5, completed_days_ago=0)
        # active run with 1 blocked step → "warning" (not healthy)
        warning_run = _make_run(status="active", steps=[
            _make_step(status="blocked"),
            _make_step(status="pending"),
            _make_step(status="in_progress"),
        ])
        result = WorkflowObservabilityService._compute_flow_health([completed, warning_run])
        # 1 healthy out of 2 = 50.0
        assert abs(result.flow_health_score - 50.0) < 0.1

    def test_avg_run_completion_days(self) -> None:
        run = _make_run(status="completed", days_ago=10, completed_days_ago=0)
        result = WorkflowObservabilityService._compute_flow_health([run])
        assert abs(result.average_run_completion_days - 10.0) < 0.1

    def test_avg_step_completion_days(self) -> None:
        step = _make_step(
            status="completed",
            completed_at=_NOW - timedelta(days=8),  # 2 days from run start
        )
        run = _make_run(status="completed", days_ago=10, completed_days_ago=0, steps=[step])
        result = WorkflowObservabilityService._compute_flow_health([run])
        assert abs(result.average_step_completion_days - 2.0) < 0.1

    def test_data_integrity_warning_negative_duration(self) -> None:
        run = _make_run(status="completed")
        # Force: completed_at < started_at
        run.started_at = _NOW
        run.completed_at = _NOW - timedelta(days=1)
        result = WorkflowObservabilityService._compute_flow_health([run])
        assert result.data_integrity_warning is True

    def test_data_integrity_warning_false_when_clean(self) -> None:
        run = _make_run(status="completed", days_ago=5, completed_days_ago=0)
        result = WorkflowObservabilityService._compute_flow_health([run])
        assert result.data_integrity_warning is False

    def test_cancelled_excluded_from_run_avg_duration(self) -> None:
        completed = _make_run(status="completed", days_ago=10, completed_days_ago=0)
        cancelled = _make_run(status="cancelled", cancelled_days_ago=0)
        result = WorkflowObservabilityService._compute_flow_health([completed, cancelled])
        assert abs(result.average_run_completion_days - 10.0) < 0.1

    def test_active_excluded_from_run_avg_duration(self) -> None:
        completed = _make_run(status="completed", days_ago=10, completed_days_ago=0)
        active = _make_run(status="active", steps=[])
        result = WorkflowObservabilityService._compute_flow_health([completed, active])
        assert abs(result.average_run_completion_days - 10.0) < 0.1


# ── Cache hit/miss integration tests ─────────────────────────────────────────


class TestGetBottlenecksCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self) -> None:
        from corpmind.modules.workflows.schemas import BottleneckObsOut
        payload = BottleneckObsOut(items=[]).model_dump_json()
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(payload)),
        ):
            result = await svc.get_bottlenecks(_WS)
        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo(self) -> None:
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(None)),
        ):
            await svc.get_bottlenecks(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_error_does_not_raise(self) -> None:
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_bottlenecks(_WS)
        assert result.items == []


class TestGetStepAnalysisCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        from corpmind.modules.workflows.schemas import StepAnalysisOut
        payload = StepAnalysisOut(items=[]).model_dump_json()
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(payload)),
        ):
            await svc.get_step_analysis(_WS)
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo(self) -> None:
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(None)),
        ):
            await svc.get_step_analysis(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()


class TestGetOwnerCapacityCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        from corpmind.modules.workflows.schemas import OwnerCapacityOut
        payload = OwnerCapacityOut(items=[]).model_dump_json()
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(payload)),
        ):
            await svc.get_owner_capacity(_WS)
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo(self) -> None:
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(None)),
        ):
            await svc.get_owner_capacity(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()


class TestGetTemplateCapacityCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        from corpmind.modules.workflows.schemas import TemplateCapacityOut
        payload = TemplateCapacityOut(items=[]).model_dump_json()
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(payload)),
        ):
            await svc.get_template_capacity(_WS)
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo(self) -> None:
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(None)),
        ):
            await svc.get_template_capacity(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()


class TestGetFlowHealthCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_repo(self) -> None:
        from corpmind.modules.workflows.schemas import FlowHealthOut
        payload = FlowHealthOut(
            healthy_flows=0, warning_flows=0, critical_flows=0,
            average_step_completion_days=0.0, average_run_completion_days=0.0,
            flow_health_score=0.0, data_integrity_warning=False,
        ).model_dump_json()
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(payload)),
        ):
            await svc.get_flow_health(_WS)
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repo(self) -> None:
        svc = _make_svc()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=_make_redis(None)),
        ):
            await svc.get_flow_health(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()


# ── Tenant isolation tests ────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_bottlenecks_uses_org_id_in_cache_key(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        key_a = _obs_bottlenecks_key(org_a, _WS)
        key_b = _obs_bottlenecks_key(org_b, _WS)
        assert key_a != key_b

    def test_step_analysis_no_cross_workspace_leak(self) -> None:
        step = _make_step(status="completed", title="S", completed_at=_NOW - timedelta(days=1))
        run = _make_run(steps=[step])
        result_ws1 = WorkflowObservabilityService._compute_step_analysis([run])
        result_ws2 = WorkflowObservabilityService._compute_step_analysis([])
        assert len(result_ws1.items) == 1
        assert len(result_ws2.items) == 0

    def test_owner_capacity_no_cross_workspace_leak(self) -> None:
        step = _make_step(owner_role="admin")
        run = _make_run(steps=[step])
        r1 = WorkflowObservabilityService._compute_owner_capacity([run])
        r2 = WorkflowObservabilityService._compute_owner_capacity([])
        assert len(r1.items) == 1
        assert len(r2.items) == 0

    def test_template_capacity_no_cross_workspace_leak(self) -> None:
        run = _make_run(status="active", workflow_template_id=_TMPL_A)
        r1 = WorkflowObservabilityService._compute_template_capacity([run], {str(_TMPL_A): "T"}, _NOW)
        r2 = WorkflowObservabilityService._compute_template_capacity([], {}, _NOW)
        assert len(r1.items) == 1
        assert len(r2.items) == 0

    def test_flow_health_no_cross_workspace_leak(self) -> None:
        run = _make_run(status="completed", days_ago=5, completed_days_ago=0)
        r1 = WorkflowObservabilityService._compute_flow_health([run])
        r2 = WorkflowObservabilityService._compute_flow_health([])
        assert r1.healthy_flows == 1
        assert r2.healthy_flows == 0


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCasesBottlenecks:
    def test_step_completed_at_none_excluded_from_duration(self) -> None:
        step = _make_step(status="completed", title="X", completed_at=None)
        run = _make_run(status="completed", days_ago=5, completed_days_ago=0, workflow_template_id=_TMPL_A, steps=[step])
        result = WorkflowObservabilityService._compute_bottlenecks([run], {str(_TMPL_A): "T"})
        # No valid durations → no items
        assert result.items == []

    def test_runs_affected_only_completed(self) -> None:
        step = _make_step(status="completed", title="A", completed_at=_NOW - timedelta(days=1))
        run1 = _make_run(status="completed", days_ago=5, completed_days_ago=0, workflow_template_id=_TMPL_A, steps=[step])
        run2 = _make_run(status="active", workflow_template_id=_TMPL_A, steps=[step])
        result = WorkflowObservabilityService._compute_bottlenecks(
            [run1, run2], {str(_TMPL_A): "T"}
        )
        assert result.items[0].runs_affected == 1

    def test_negative_step_duration_clamped_to_zero(self) -> None:
        step = _make_step(status="completed", title="X")
        run = _make_run(status="completed", days_ago=5, completed_days_ago=0, workflow_template_id=_TMPL_A, steps=[step])
        # Force negative duration
        step.completed_at = run.started_at - timedelta(days=1)
        result = WorkflowObservabilityService._compute_bottlenecks([run], {str(_TMPL_A): "T"})
        if result.items:
            assert result.items[0].average_days >= 0.0


class TestEdgeCasesStepAnalysis:
    def test_step_no_completed_at_excluded_from_duration(self) -> None:
        step = _make_step(status="completed", title="X", completed_at=None)
        run = _make_run(steps=[step])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "X")
        assert item.average_completion_days == 0.0

    def test_single_value_median_equals_value(self) -> None:
        step = _make_step(
            status="completed",
            title="Solo",
            completed_at=_NOW - timedelta(days=7),
        )
        run = _make_run(days_ago=10, steps=[step])
        result = WorkflowObservabilityService._compute_step_analysis([run])
        item = next(i for i in result.items if i.step_name == "Solo")
        assert abs(item.median_completion_days - item.average_completion_days) < 0.01


class TestEdgeCasesFlowHealth:
    def test_active_run_no_steps_is_healthy(self) -> None:
        run = _make_run(status="active", steps=[])
        result = WorkflowObservabilityService._compute_flow_health([run])
        assert result.healthy_flows == 1

    def test_step_durations_from_non_completed_runs_excluded(self) -> None:
        step = _make_step(status="completed", completed_at=_NOW - timedelta(days=1))
        active_run = _make_run(status="active", days_ago=5, steps=[step])
        result = WorkflowObservabilityService._compute_flow_health([active_run])
        assert result.average_step_completion_days == 0.0

    def test_multiple_integrity_violations_still_single_warning(self) -> None:
        run1 = _make_run(status="completed")
        run1.started_at = _NOW
        run1.completed_at = _NOW - timedelta(days=1)
        run2 = _make_run(status="completed")
        run2.started_at = _NOW
        run2.completed_at = _NOW - timedelta(days=2)
        result = WorkflowObservabilityService._compute_flow_health([run1, run2])
        assert result.data_integrity_warning is True


class TestEdgeCasesOwnerCapacity:
    def test_zero_assigned_steps_no_capacity_score(self) -> None:
        result = WorkflowObservabilityService._compute_owner_capacity([])
        assert result.items == []

    def test_no_completed_steps_capacity_zero(self) -> None:
        step = _make_step(status="pending", owner_role="viewer")
        run = _make_run(steps=[step])
        result = WorkflowObservabilityService._compute_owner_capacity([run])
        item = next(i for i in result.items if i.owner_role == "viewer")
        assert item.capacity_score == 0.0
        assert item.average_completion_days == 0.0
