"""Unit tests for WorkflowSLAService — Sprint 37.

All tests are synchronous static-method tests or async cache-hit/miss tests.
No database, no real Redis.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.modules.workflows.service import (
    WorkflowSLAService,
    _sla_overdue_key,
    _sla_owner_key,
    _sla_summary_key,
    _sla_templates_key,
    _sla_trend_key,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
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


def _make_svc() -> WorkflowSLAService:
    svc = WorkflowSLAService(MagicMock())
    svc._run_repo = MagicMock()
    svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])
    svc._template_repo = MagicMock()
    svc._template_repo.find_all_for_workspace = AsyncMock(return_value=[])
    return svc


def _make_step(
    *,
    status: str = "pending",
    owner_role: str = "member",
    required: bool = True,
    completed_at: datetime | None = None,
    step_order: int = 1,
    title: str = "Step",
) -> MagicMock:
    s = MagicMock()
    s.status = status
    s.owner_role = owner_role
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
    entity_title: str | None = None,
    steps: list | None = None,
    title: str = "Test Run",
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.title = title
    r.status = status
    r.workflow_template_id = workflow_template_id
    r.entity_type = entity_type
    r.entity_title = entity_title
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


class TestSLACacheKeys:
    def test_summary_key_format(self) -> None:
        key = _sla_summary_key(_ORG, _WS)
        assert key.startswith(f"t:{_ORG}:{_WS}:")
        assert "workflow_sla_summary" in key

    def test_overdue_key_format(self) -> None:
        key = _sla_overdue_key(_ORG, _WS)
        assert "workflow_sla_overdue" in key

    def test_templates_key_format(self) -> None:
        key = _sla_templates_key(_ORG, _WS)
        assert "workflow_sla_templates" in key

    def test_owner_key_format(self) -> None:
        key = _sla_owner_key(_ORG, _WS)
        assert "workflow_sla_owner" in key

    def test_trend_key_includes_period(self) -> None:
        key30 = _sla_trend_key(_ORG, _WS, 30)
        key7 = _sla_trend_key(_ORG, _WS, 7)
        assert "30" in key30
        assert "7" in key7
        assert key30 != key7

    def test_keys_are_tenant_scoped(self) -> None:
        org2 = uuid.uuid4()
        k1 = _sla_summary_key(_ORG, _WS)
        k2 = _sla_summary_key(org2, _WS)
        assert k1 != k2


# ── _compute_summary tests ────────────────────────────────────────────────────


class TestComputeSummaryEmpty:
    def test_empty_returns_zeros(self) -> None:
        result = WorkflowSLAService._compute_summary([], _NOW)
        assert result.active_runs == 0
        assert result.overdue_runs == 0
        assert result.healthy_runs == 0
        assert result.warning_overdue == 0
        assert result.critical_overdue == 0
        assert result.sla_compliance_rate == 1.0
        assert result.average_days_open == 0.0
        assert result.average_days_overdue == 0.0
        assert result.data_integrity_warning is False

    def test_only_cancelled_runs_gives_no_active(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=40)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.active_runs == 0
        assert result.overdue_runs == 0

    def test_only_completed_runs_gives_no_active(self) -> None:
        runs = [_make_run(status="completed", days_ago=50, completed_days_ago=5)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.active_runs == 0


class TestComputeSummaryHealthy:
    def test_run_within_sla_is_healthy(self) -> None:
        runs = [_make_run(status="active", days_ago=10)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.healthy_runs == 1
        assert result.overdue_runs == 0
        assert result.sla_compliance_rate == 1.0

    def test_run_at_exactly_sla_boundary_is_healthy(self) -> None:
        runs = [_make_run(status="active", days_ago=30)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.healthy_runs == 1
        assert result.overdue_runs == 0

    def test_pending_run_within_sla_counts_as_active(self) -> None:
        runs = [_make_run(status="pending", days_ago=5)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.active_runs == 1
        assert result.healthy_runs == 1


class TestComputeSummaryOverdue:
    def test_warning_overdue_31_days(self) -> None:
        runs = [_make_run(status="active", days_ago=31)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.warning_overdue == 1
        assert result.critical_overdue == 0
        assert result.overdue_runs == 1

    def test_critical_overdue_61_days(self) -> None:
        runs = [_make_run(status="active", days_ago=61)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.critical_overdue == 1
        assert result.warning_overdue == 0

    def test_boundary_60_days_is_warning(self) -> None:
        runs = [_make_run(status="active", days_ago=60)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.warning_overdue == 1
        assert result.critical_overdue == 0

    def test_compliance_rate_with_mixed_runs(self) -> None:
        runs = [
            _make_run(status="active", days_ago=10),  # healthy
            _make_run(status="active", days_ago=10),  # healthy
            _make_run(status="active", days_ago=40),  # warning
        ]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.active_runs == 3
        assert result.healthy_runs == 2
        assert result.overdue_runs == 1
        assert round(result.sla_compliance_rate, 4) == round(2 / 3, 4)

    def test_average_days_open_computed(self) -> None:
        runs = [
            _make_run(status="active", days_ago=10),
            _make_run(status="active", days_ago=20),
        ]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert abs(result.average_days_open - 15.0) < 0.1

    def test_average_days_overdue_only_for_overdue(self) -> None:
        runs = [
            _make_run(status="active", days_ago=10),   # healthy — not in overdue avg
            _make_run(status="active", days_ago=40),   # overdue by 10 days
        ]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert abs(result.average_days_overdue - 10.0) < 0.1


class TestComputeSummaryIntegrity:
    def test_negative_duration_triggers_warning(self) -> None:
        r = _make_run(status="completed", days_ago=5, completed_days_ago=10)
        result = WorkflowSLAService._compute_summary([r], _NOW)
        assert result.data_integrity_warning is True

    def test_positive_duration_no_warning(self) -> None:
        r = _make_run(status="completed", days_ago=10, completed_days_ago=2)
        result = WorkflowSLAService._compute_summary([r], _NOW)
        assert result.data_integrity_warning is False

    def test_active_run_no_integrity_warning(self) -> None:
        r = _make_run(status="active", days_ago=5)
        result = WorkflowSLAService._compute_summary([r], _NOW)
        assert result.data_integrity_warning is False


# ── _compute_overdue tests ────────────────────────────────────────────────────


class TestComputeOverdueEmpty:
    def test_empty_runs_returns_empty_list(self) -> None:
        result = WorkflowSLAService._compute_overdue([], _NOW, {})
        assert result.items == []

    def test_all_healthy_runs_returns_empty_list(self) -> None:
        runs = [_make_run(status="active", days_ago=10)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items == []

    def test_cancelled_runs_excluded(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=50)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items == []

    def test_completed_runs_excluded(self) -> None:
        runs = [_make_run(status="completed", days_ago=50, completed_days_ago=5)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items == []


class TestComputeOverdueData:
    def test_overdue_run_appears_in_list(self) -> None:
        runs = [_make_run(status="active", days_ago=40, title="Late Run")]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert len(result.items) == 1
        assert result.items[0].title == "Late Run"
        assert result.items[0].days_overdue > 0

    def test_sorted_most_overdue_first(self) -> None:
        runs = [
            _make_run(status="active", days_ago=35, title="Mild"),
            _make_run(status="active", days_ago=70, title="Critical"),
            _make_run(status="active", days_ago=45, title="Warning"),
        ]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert len(result.items) == 3
        assert result.items[0].title == "Critical"
        assert result.items[-1].title == "Mild"

    def test_template_name_resolved(self) -> None:
        tmpl_id = uuid.uuid4()
        runs = [_make_run(status="active", days_ago=40, workflow_template_id=tmpl_id)]
        template_names = {str(tmpl_id): "Sales Process"}
        result = WorkflowSLAService._compute_overdue(runs, _NOW, template_names)
        assert result.items[0].template_name == "Sales Process"

    def test_no_template_gives_none(self) -> None:
        runs = [_make_run(status="active", days_ago=40, workflow_template_id=None)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items[0].template_name is None

    def test_entity_info_propagated(self) -> None:
        runs = [
            _make_run(
                status="active",
                days_ago=40,
                entity_type="lead",
                entity_title="ACME Corp",
            )
        ]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items[0].entity_type == "lead"
        assert result.items[0].entity_title == "ACME Corp"

    def test_current_step_is_first_non_completed(self) -> None:
        steps = [
            _make_step(status="completed", step_order=1),
            _make_step(status="pending", step_order=2, owner_role="admin"),
            _make_step(status="pending", step_order=3),
        ]
        runs = [_make_run(status="active", days_ago=40, steps=steps)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items[0].owner_role == "admin"

    def test_current_step_skips_skipped_steps(self) -> None:
        steps = [
            _make_step(status="skipped", step_order=1),
            _make_step(status="blocked", step_order=2, owner_role="owner"),
        ]
        runs = [_make_run(status="active", days_ago=40, steps=steps)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items[0].owner_role == "owner"

    def test_all_steps_completed_gives_none_current(self) -> None:
        steps = [_make_step(status="completed", step_order=1)]
        runs = [_make_run(status="active", days_ago=40, steps=steps)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert result.items[0].current_step is None

    def test_days_overdue_calculated_correctly(self) -> None:
        runs = [_make_run(status="active", days_ago=40)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert abs(result.items[0].days_overdue - 10.0) < 0.1

    def test_run_id_is_string(self) -> None:
        runs = [_make_run(status="active", days_ago=40)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert isinstance(result.items[0].run_id, str)


# ── _compute_template_sla tests ───────────────────────────────────────────────


class TestComputeTemplateSLAEmpty:
    def test_empty_runs_returns_empty_list(self) -> None:
        result = WorkflowSLAService._compute_template_sla([], _NOW, {})
        assert result.items == []

    def test_only_cancelled_runs_excluded(self) -> None:
        runs = [_make_run(status="cancelled", days_ago=40)]
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, {})
        assert result.items == []


class TestComputeTemplateSLAData:
    def test_groups_by_template(self) -> None:
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        runs = [
            _make_run(status="active", days_ago=10, workflow_template_id=t1),
            _make_run(status="active", days_ago=10, workflow_template_id=t1),
            _make_run(status="active", days_ago=10, workflow_template_id=t2),
        ]
        names = {str(t1): "T1", str(t2): "T2"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        counts = {item.template_name: item.runs for item in result.items}
        assert counts["T1"] == 2
        assert counts["T2"] == 1

    def test_standalone_runs_grouped(self) -> None:
        runs = [_make_run(status="active", days_ago=10, workflow_template_id=None)]
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, {})
        assert len(result.items) == 1
        assert result.items[0].template_name == "Standalone (no template)"

    def test_overdue_count_correct(self) -> None:
        t1 = uuid.uuid4()
        runs = [
            _make_run(status="active", days_ago=10, workflow_template_id=t1),
            _make_run(status="active", days_ago=40, workflow_template_id=t1),
        ]
        names = {str(t1): "T1"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        assert result.items[0].overdue == 1

    def test_compliance_rate_for_all_healthy(self) -> None:
        t1 = uuid.uuid4()
        runs = [
            _make_run(status="active", days_ago=10, workflow_template_id=t1),
            _make_run(status="active", days_ago=20, workflow_template_id=t1),
        ]
        names = {str(t1): "T1"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        assert result.items[0].compliance_rate == 1.0

    def test_compliance_rate_with_overdue(self) -> None:
        t1 = uuid.uuid4()
        runs = [
            _make_run(status="active", days_ago=10, workflow_template_id=t1),
            _make_run(status="active", days_ago=40, workflow_template_id=t1),
        ]
        names = {str(t1): "T1"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        assert abs(result.items[0].compliance_rate - 0.5) < 0.001

    def test_sorted_most_overdue_first(self) -> None:
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        runs = [
            _make_run(status="active", days_ago=40, workflow_template_id=t1),
            _make_run(status="active", days_ago=40, workflow_template_id=t1),
            _make_run(status="active", days_ago=10, workflow_template_id=t2),
        ]
        names = {str(t1): "T1", str(t2): "T2"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        assert result.items[0].template_name == "T1"

    def test_completed_run_duration_included_in_average(self) -> None:
        t1 = uuid.uuid4()
        runs = [
            _make_run(
                status="completed",
                days_ago=20,
                completed_days_ago=5,
                workflow_template_id=t1,
            )
        ]
        names = {str(t1): "T1"}
        result = WorkflowSLAService._compute_template_sla(runs, _NOW, names)
        assert result.items[0].runs == 1
        assert result.items[0].average_duration_days > 0


# ── _compute_owner_sla tests ──────────────────────────────────────────────────


class TestComputeOwnerSLAEmpty:
    def test_empty_runs_returns_empty_list(self) -> None:
        result = WorkflowSLAService._compute_owner_sla([], _NOW)
        assert result.items == []

    def test_cancelled_runs_excluded(self) -> None:
        steps = [_make_step(status="pending", owner_role="member", required=True)]
        runs = [_make_run(status="cancelled", days_ago=40, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        assert result.items == []


class TestComputeOwnerSLAData:
    def test_optional_steps_excluded(self) -> None:
        steps = [_make_step(status="pending", owner_role="viewer", required=False)]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        assert result.items == []

    def test_skipped_steps_excluded(self) -> None:
        steps = [_make_step(status="skipped", owner_role="member", required=True)]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        assert result.items == []

    def test_completed_step_counts_assigned_and_completed(self) -> None:
        completed_at = _NOW - timedelta(days=5)
        steps = [
            _make_step(
                status="completed",
                owner_role="member",
                required=True,
                completed_at=completed_at,
            )
        ]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next(i for i in result.items if i.owner_role == "member")
        assert member.assigned_steps == 1
        assert member.completed_steps == 1

    def test_pending_step_within_sla_not_overdue(self) -> None:
        steps = [_make_step(status="pending", owner_role="member", required=True)]
        runs = [_make_run(status="active", days_ago=5, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next(i for i in result.items if i.owner_role == "member")
        assert member.overdue_steps == 0

    def test_pending_step_overdue_when_run_exceeds_step_sla(self) -> None:
        steps = [_make_step(status="pending", owner_role="member", required=True)]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next(i for i in result.items if i.owner_role == "member")
        assert member.overdue_steps == 1

    def test_groups_by_role(self) -> None:
        steps = [
            _make_step(status="pending", owner_role="owner", required=True),
            _make_step(status="pending", owner_role="member", required=True),
        ]
        runs = [_make_run(status="active", days_ago=5, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        roles = {i.owner_role for i in result.items}
        assert "owner" in roles
        assert "member" in roles

    def test_compliance_rate_all_healthy(self) -> None:
        steps = [_make_step(status="pending", owner_role="admin", required=True)]
        runs = [_make_run(status="active", days_ago=3, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        admin = next(i for i in result.items if i.owner_role == "admin")
        assert admin.compliance_rate == 1.0

    def test_compliance_rate_all_overdue(self) -> None:
        steps = [_make_step(status="pending", owner_role="admin", required=True)]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        admin = next(i for i in result.items if i.owner_role == "admin")
        assert admin.compliance_rate == 0.0

    def test_avg_completion_days_calculated(self) -> None:
        completed_at = _NOW - timedelta(days=3)
        steps = [
            _make_step(
                status="completed",
                owner_role="member",
                required=True,
                completed_at=completed_at,
            )
        ]
        runs = [_make_run(status="active", days_ago=8, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next(i for i in result.items if i.owner_role == "member")
        assert member.average_completion_days > 0


# ── _compute_sla_trend tests ──────────────────────────────────────────────────


class TestComputeSLATrendEmpty:
    def test_empty_returns_period_buckets(self) -> None:
        result = WorkflowSLAService._compute_sla_trend([], _NOW, 7)
        assert result.period == 7
        assert len(result.buckets) == 7

    def test_30_day_period_has_30_buckets(self) -> None:
        result = WorkflowSLAService._compute_sla_trend([], _NOW, 30)
        assert len(result.buckets) == 30

    def test_buckets_sorted_ascending(self) -> None:
        result = WorkflowSLAService._compute_sla_trend([], _NOW, 7)
        dates = [b.date for b in result.buckets]
        assert dates == sorted(dates)

    def test_empty_buckets_have_zero_counts(self) -> None:
        result = WorkflowSLAService._compute_sla_trend([], _NOW, 7)
        for b in result.buckets:
            assert b.healthy == 0
            assert b.warning == 0
            assert b.critical == 0
            assert b.completed == 0


class TestComputeSLATrendData:
    def test_completed_run_counted_in_completed_bucket(self) -> None:
        completed_at = _NOW - timedelta(days=2)
        r = _make_run(
            status="completed",
            days_ago=15,
            completed_days_ago=2,
        )
        r.completed_at = completed_at
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 30)
        completed_date = completed_at.date().isoformat()
        bucket = next(b for b in result.buckets if b.date == completed_date)
        assert bucket.completed == 1

    def test_active_healthy_run_counted_in_healthy_bucket(self) -> None:
        started = _NOW - timedelta(days=5)
        r = _make_run(status="active", days_ago=5)
        r.started_at = started
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 30)
        started_date = started.date().isoformat()
        bucket = next((b for b in result.buckets if b.date == started_date), None)
        assert bucket is not None
        assert bucket.healthy == 1

    def test_warning_run_counted_in_warning_bucket(self) -> None:
        # Run started 35 days ago (within 90-day window) and is 35 days old → warning
        r = _make_run(status="active", days_ago=35)
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 90)
        started_date = r.started_at.date().isoformat()
        bucket = next((b for b in result.buckets if b.date == started_date), None)
        assert bucket is not None
        assert bucket.warning == 1

    def test_run_outside_period_not_counted(self) -> None:
        r = _make_run(status="active", days_ago=200)
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 7)
        total_healthy = sum(b.healthy for b in result.buckets)
        total_warning = sum(b.warning for b in result.buckets)
        total_critical = sum(b.critical for b in result.buckets)
        assert total_healthy + total_warning + total_critical == 0

    def test_cancelled_run_not_counted_in_active_buckets(self) -> None:
        r = _make_run(status="cancelled", days_ago=5)
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 30)
        total_active = sum(b.healthy + b.warning + b.critical for b in result.buckets)
        assert total_active == 0


# ── Async cache hit/miss tests ────────────────────────────────────────────────


class TestGetSummaryCache:
    @pytest.mark.anyio
    async def test_cache_hit_returns_without_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        from corpmind.modules.workflows.schemas import SLASummaryOut

        cached_obj = SLASummaryOut(
            active_runs=5,
            overdue_runs=1,
            sla_compliance_rate=0.8,
            average_days_open=20.0,
            average_days_overdue=5.0,
            critical_overdue=0,
            warning_overdue=1,
            healthy_runs=4,
            data_integrity_warning=False,
        )
        redis = _make_redis(cached=cached_obj.model_dump_json())
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_summary(_WS)
        assert result.active_runs == 5
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.anyio
    async def test_cache_miss_calls_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_summary(_WS)
        assert result.active_runs == 0
        svc._run_repo.find_all_for_workspace.assert_called_once_with(_WS)

    @pytest.mark.anyio
    async def test_redis_failure_falls_back_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("Redis down"))
        redis.set = AsyncMock(side_effect=Exception("Redis down"))
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_summary(_WS)
        assert result.active_runs == 0  # computed from empty repo


class TestGetOverdueCache:
    @pytest.mark.anyio
    async def test_cache_miss_calls_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_overdue(_WS)
        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.anyio
    async def test_redis_failure_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("timeout"))
        redis.set = AsyncMock(side_effect=Exception("timeout"))
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_overdue(_WS)
        assert result.items == []


class TestGetTemplateSLACache:
    @pytest.mark.anyio
    async def test_cache_miss_calls_both_repos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        await svc.get_template_sla(_WS)
        svc._run_repo.find_all_for_workspace.assert_called_once()
        svc._template_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.anyio
    async def test_redis_failure_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("down"))
        redis.set = AsyncMock(side_effect=Exception("down"))
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_template_sla(_WS)
        assert result.items == []


class TestGetOwnerSLACache:
    @pytest.mark.anyio
    async def test_cache_miss_calls_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_owner_sla(_WS)
        assert result.items == []

    @pytest.mark.anyio
    async def test_redis_failure_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("down"))
        redis.set = AsyncMock(side_effect=Exception("down"))
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_owner_sla(_WS)
        assert result.items == []


class TestGetTrendCache:
    @pytest.mark.anyio
    async def test_cache_miss_returns_correct_period(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_trend(_WS, 7)
        assert result.period == 7
        assert len(result.buckets) == 7

    @pytest.mark.anyio
    async def test_redis_failure_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = _make_svc()
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=Exception("down"))
        redis.set = AsyncMock(side_effect=Exception("down"))
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_redis", lambda: redis
        )
        monkeypatch.setattr(
            "corpmind.modules.workflows.service.get_tenant_context", _make_ctx
        )
        result = await svc.get_trend(_WS, 30)
        assert result.period == 30


# ── Tenant isolation tests ────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_summary_key_differs_per_tenant(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _sla_summary_key(org_a, ws) != _sla_summary_key(org_b, ws)

    def test_overdue_key_differs_per_tenant(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _sla_overdue_key(org_a, ws) != _sla_overdue_key(org_b, ws)

    def test_templates_key_differs_per_tenant(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _sla_templates_key(org_a, ws) != _sla_templates_key(org_b, ws)

    def test_owner_key_differs_per_tenant(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _sla_owner_key(org_a, ws) != _sla_owner_key(org_b, ws)

    def test_trend_key_differs_per_tenant(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _sla_trend_key(org_a, ws, 30) != _sla_trend_key(org_b, ws, 30)


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCasesSummary:
    def test_zero_active_compliance_rate_is_one(self) -> None:
        result = WorkflowSLAService._compute_summary([], _NOW)
        assert result.sla_compliance_rate == 1.0

    def test_all_overdue_compliance_zero(self) -> None:
        runs = [
            _make_run(status="active", days_ago=40),
            _make_run(status="active", days_ago=70),
        ]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.sla_compliance_rate == 0.0

    def test_pending_status_treated_as_active(self) -> None:
        runs = [_make_run(status="pending", days_ago=35)]
        result = WorkflowSLAService._compute_summary(runs, _NOW)
        assert result.active_runs == 1
        assert result.overdue_runs == 1

    def test_multiple_integrity_errors_detected(self) -> None:
        r1 = _make_run(status="completed", days_ago=5, completed_days_ago=10)
        r2 = _make_run(status="completed", days_ago=3, completed_days_ago=8)
        result = WorkflowSLAService._compute_summary([r1, r2], _NOW)
        assert result.data_integrity_warning is True


class TestEdgeCasesOverdue:
    def test_run_started_exactly_at_sla_not_overdue(self) -> None:
        runs = [_make_run(status="active", days_ago=30)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        assert len(result.items) == 0

    def test_started_at_isoformat(self) -> None:
        runs = [_make_run(status="active", days_ago=40)]
        result = WorkflowSLAService._compute_overdue(runs, _NOW, {})
        # Should be a valid ISO string
        from datetime import datetime
        datetime.fromisoformat(result.items[0].started_at)


class TestEdgeCasesOwner:
    def test_blocked_step_counts_as_overdue_if_run_past_step_sla(self) -> None:
        steps = [_make_step(status="blocked", owner_role="member", required=True)]
        runs = [_make_run(status="active", days_ago=10, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next((i for i in result.items if i.owner_role == "member"), None)
        assert member is not None
        assert member.overdue_steps == 1

    def test_compliance_never_negative(self) -> None:
        steps = [
            _make_step(status="pending", owner_role="member", required=True),
            _make_step(status="pending", owner_role="member", required=True),
        ]
        runs = [_make_run(status="active", days_ago=15, steps=steps)]
        result = WorkflowSLAService._compute_owner_sla(runs, _NOW)
        member = next(i for i in result.items if i.owner_role == "member")
        assert member.compliance_rate >= 0.0


class TestEdgeCasesTrend:
    def test_90_day_trend_has_90_buckets(self) -> None:
        result = WorkflowSLAService._compute_sla_trend([], _NOW, 90)
        assert len(result.buckets) == 90

    def test_critical_run_in_bucket(self) -> None:
        # Run started 65 days ago (within 90-day window) and is 65 days old → critical
        r = _make_run(status="active", days_ago=65)
        result = WorkflowSLAService._compute_sla_trend([r], _NOW, 90)
        started_date = r.started_at.date().isoformat()
        bucket = next((b for b in result.buckets if b.date == started_date), None)
        assert bucket is not None
        assert bucket.critical == 1
