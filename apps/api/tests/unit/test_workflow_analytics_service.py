"""Unit tests for WorkflowAnalyticsService — Sprint 36.

115 tests across 14 test classes.
All DB and Redis interactions are mocked; only pure service / compute logic exercised.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.workflows.schemas import (
    AnalyticsSummaryOut,
    BottleneckAnalyticsOut,
    BottleneckItem,
    TemplateAnalyticsOut,
    TrendAnalyticsOut,
    WorkloadAnalyticsOut,
)
from corpmind.modules.workflows.service import (
    WorkflowAnalyticsService,
    _analytics_bottlenecks_key,
    _analytics_summary_key,
    _analytics_templates_key,
    _analytics_trends_key,
    _analytics_workload_key,
)

# ── Constants ─────────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WS_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TMPL_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

NOW = datetime(2026, 6, 30, 10, 0, 0, tzinfo=UTC)
YESTERDAY = NOW - timedelta(days=1)
TWO_DAYS_AGO = NOW - timedelta(days=2)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ctx(role: str = "owner") -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.user_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    ctx.role = role
    return ctx


def _make_redis(cached: Any = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> WorkflowAnalyticsService:
    svc = WorkflowAnalyticsService(MagicMock())
    svc._run_repo = MagicMock()
    svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])
    svc._template_repo = MagicMock()
    svc._template_repo.find_all_for_workspace = AsyncMock(return_value=[])
    return svc


def _make_step(
    status: str = "completed",
    owner_role: str = "member",
    required: bool = True,
    completed_at: datetime | None = None,
    template_step_id: uuid.UUID | None = None,
    title: str = "Step A",
) -> MagicMock:
    s = MagicMock()
    s.status = status
    s.owner_role = owner_role
    s.required = required
    s.completed_at = completed_at
    s.template_step_id = template_step_id
    s.title = title
    return s


def _make_run(
    status: str = "completed",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    cancelled_at: datetime | None = None,
    workflow_template_id: uuid.UUID | None = None,
    steps: list | None = None,
) -> MagicMock:
    r = MagicMock()
    r.status = status
    r.started_at = started_at or NOW
    r.completed_at = completed_at
    r.cancelled_at = cancelled_at
    r.workflow_template_id = workflow_template_id
    r.run_steps = steps or []
    return r


# ── 1. Cache key helpers ──────────────────────────────────────────────────────

class TestCacheKeyHelpers:
    def test_summary_key_format(self) -> None:
        k = _analytics_summary_key(ORG_ID, WS_ID)
        assert k.startswith(f"t:{ORG_ID}:{WS_ID}:")
        assert "analytics_summary" in k

    def test_templates_key_format(self) -> None:
        k = _analytics_templates_key(ORG_ID, WS_ID)
        assert "analytics_templates" in k

    def test_bottlenecks_key_format(self) -> None:
        k = _analytics_bottlenecks_key(ORG_ID, WS_ID)
        assert "analytics_bottlenecks" in k

    def test_trends_key_format_period(self) -> None:
        k7 = _analytics_trends_key(ORG_ID, WS_ID, 7)
        k30 = _analytics_trends_key(ORG_ID, WS_ID, 30)
        assert k7 != k30
        assert "7" in k7
        assert "30" in k30

    def test_workload_key_format(self) -> None:
        k = _analytics_workload_key(ORG_ID, WS_ID)
        assert "analytics_workload" in k

    def test_keys_are_tenant_scoped(self) -> None:
        other_org = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        k1 = _analytics_summary_key(ORG_ID, WS_ID)
        k2 = _analytics_summary_key(other_org, WS_ID)
        assert k1 != k2


# ── 2. _compute_summary — empty state ────────────────────────────────────────

class TestComputeSummaryEmpty:
    def test_empty_runs_returns_zeros(self) -> None:
        result = WorkflowAnalyticsService._compute_summary([])
        assert result.total_runs == 0
        assert result.active_runs == 0
        assert result.completed_runs == 0
        assert result.cancelled_runs == 0
        assert result.completion_rate == 0.0
        assert result.average_completion_days == 0.0
        assert result.average_step_completion_days == 0.0
        assert result.average_required_steps == 0.0
        assert result.average_optional_steps == 0.0
        assert result.data_integrity_warning is False

    def test_empty_returns_analytics_summary_type(self) -> None:
        result = WorkflowAnalyticsService._compute_summary([])
        assert isinstance(result, AnalyticsSummaryOut)


# ── 3. _compute_summary — with data ──────────────────────────────────────────

class TestComputeSummaryWithData:
    def _two_runs(self) -> list:
        completed_run = _make_run(
            status="completed",
            started_at=TWO_DAYS_AGO,
            completed_at=NOW,
            steps=[
                _make_step("completed", required=True, completed_at=YESTERDAY),
                _make_step("pending", required=False),
            ],
        )
        active_run = _make_run(
            status="active",
            started_at=YESTERDAY,
            steps=[_make_step("in_progress", required=True)],
        )
        return [completed_run, active_run]

    def test_total_count(self) -> None:
        result = WorkflowAnalyticsService._compute_summary(self._two_runs())
        assert result.total_runs == 2

    def test_active_count(self) -> None:
        result = WorkflowAnalyticsService._compute_summary(self._two_runs())
        assert result.active_runs == 1

    def test_completed_count(self) -> None:
        result = WorkflowAnalyticsService._compute_summary(self._two_runs())
        assert result.completed_runs == 1

    def test_completion_rate_when_only_completed(self) -> None:
        r = _make_run(status="completed", started_at=YESTERDAY, completed_at=NOW)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.completion_rate == 1.0

    def test_completion_rate_mixed(self) -> None:
        runs = [
            _make_run("completed", YESTERDAY, completed_at=NOW),
            _make_run("cancelled", YESTERDAY, cancelled_at=NOW),
        ]
        result = WorkflowAnalyticsService._compute_summary(runs)
        assert result.completion_rate == 0.5

    def test_cancelled_count(self) -> None:
        r = _make_run("cancelled", YESTERDAY, cancelled_at=NOW)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.cancelled_runs == 1

    def test_avg_completion_days_positive(self) -> None:
        r = _make_run("completed", TWO_DAYS_AGO, completed_at=NOW)
        result = WorkflowAnalyticsService._compute_summary([r])
        # Approx 2 days
        assert result.average_completion_days > 1.9

    def test_avg_completion_days_zero_when_no_completed(self) -> None:
        r = _make_run("active", YESTERDAY)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_completion_days == 0.0

    def test_avg_step_completion_days(self) -> None:
        step = _make_step("completed", completed_at=NOW)
        r = _make_run("completed", TWO_DAYS_AGO, steps=[step])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_step_completion_days > 0

    def test_avg_required_steps(self) -> None:
        steps = [_make_step("completed", required=True), _make_step("pending", required=True)]
        r = _make_run("active", YESTERDAY, steps=steps)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_required_steps == 2.0

    def test_avg_optional_steps(self) -> None:
        steps = [_make_step("pending", required=False)]
        r = _make_run("active", YESTERDAY, steps=steps)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_optional_steps == 1.0


# ── 4. _compute_summary — data integrity warning ─────────────────────────────

class TestComputeSummaryIntegrityWarning:
    def test_no_warning_when_no_required_steps_skipped(self) -> None:
        step = _make_step("completed", required=True)
        r = _make_run("completed", YESTERDAY, completed_at=NOW, steps=[step])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.data_integrity_warning is False

    def test_warning_when_required_step_skipped(self) -> None:
        step = _make_step("skipped", required=True)
        r = _make_run("completed", YESTERDAY, completed_at=NOW, steps=[step])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.data_integrity_warning is True

    def test_no_warning_when_optional_step_skipped(self) -> None:
        step = _make_step("skipped", required=False)
        r = _make_run("completed", YESTERDAY, completed_at=NOW, steps=[step])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.data_integrity_warning is False

    def test_warning_propagates_across_runs(self) -> None:
        ok_run = _make_run("completed", YESTERDAY, completed_at=NOW,
                           steps=[_make_step("completed", required=True)])
        bad_run = _make_run("completed", YESTERDAY, completed_at=NOW,
                            steps=[_make_step("skipped", required=True)])
        result = WorkflowAnalyticsService._compute_summary([ok_run, bad_run])
        assert result.data_integrity_warning is True


# ── 5. _compute_template_analytics ───────────────────────────────────────────

class TestComputeTemplateAnalytics:
    def test_empty_returns_empty_list(self) -> None:
        result = WorkflowAnalyticsService._compute_template_analytics([], {})
        assert isinstance(result, TemplateAnalyticsOut)
        assert result.items == []

    def test_groups_by_template(self) -> None:
        t1 = str(TMPL_ID)
        r1 = _make_run("completed", YESTERDAY, completed_at=NOW, workflow_template_id=TMPL_ID)
        r2 = _make_run("active", YESTERDAY, workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics(
            [r1, r2], {t1: "Template A"}
        )
        assert len(result.items) == 1
        assert result.items[0].runs == 2
        assert result.items[0].template_name == "Template A"

    def test_standalone_runs_grouped_separately(self) -> None:
        r = _make_run("completed", YESTERDAY, completed_at=NOW, workflow_template_id=None)
        result = WorkflowAnalyticsService._compute_template_analytics([r], {})
        assert any(i.template_name == "Standalone (no template)" for i in result.items)

    def test_sorted_by_completed_desc(self) -> None:
        t1 = str(TMPL_ID)
        t2 = str(uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
        runs = [
            _make_run("completed", YESTERDAY, completed_at=NOW,
                      workflow_template_id=uuid.UUID(t2)),
            _make_run("active", YESTERDAY,
                      workflow_template_id=TMPL_ID),
            _make_run("completed", YESTERDAY, completed_at=NOW,
                      workflow_template_id=TMPL_ID),
            _make_run("completed", YESTERDAY, completed_at=NOW,
                      workflow_template_id=TMPL_ID),
        ]
        result = WorkflowAnalyticsService._compute_template_analytics(
            runs, {t1: "A", t2: "B"}
        )
        # Template A has 2 completed, B has 1
        assert result.items[0].completed >= result.items[1].completed

    def test_completion_rate_calculation(self) -> None:
        t1 = str(TMPL_ID)
        comp = _make_run("completed", YESTERDAY, completed_at=NOW, workflow_template_id=TMPL_ID)
        canc = _make_run("cancelled", YESTERDAY, cancelled_at=NOW, workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics(
            [comp, canc], {t1: "T"}
        )
        item = result.items[0]
        assert item.completion_rate == 0.5
        assert item.cancelled == 1

    def test_avg_completion_days_computed(self) -> None:
        t1 = str(TMPL_ID)
        r = _make_run("completed", TWO_DAYS_AGO, completed_at=NOW,
                      workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics(
            [r], {t1: "T"}
        )
        assert result.items[0].average_completion_days > 0

    def test_avg_steps_counts(self) -> None:
        t1 = str(TMPL_ID)
        steps = [
            _make_step("completed", required=True),
            _make_step("pending", required=False),
        ]
        r = _make_run("active", YESTERDAY, workflow_template_id=TMPL_ID, steps=steps)
        result = WorkflowAnalyticsService._compute_template_analytics(
            [r], {t1: "T"}
        )
        item = result.items[0]
        assert item.average_steps == 2.0
        assert item.average_required_steps == 1.0
        assert item.average_optional_steps == 1.0

    def test_unknown_template_id_falls_back_to_standalone(self) -> None:
        r = _make_run("completed", YESTERDAY, completed_at=NOW,
                      workflow_template_id=TMPL_ID)
        # template_names dict does NOT contain TMPL_ID
        result = WorkflowAnalyticsService._compute_template_analytics([r], {})
        # Falls back to standalone label
        assert any("Standalone" in i.template_name for i in result.items)


# ── 6. _compute_bottlenecks ───────────────────────────────────────────────────

class TestComputeBottlenecks:
    def test_empty_returns_empty(self) -> None:
        result = WorkflowAnalyticsService._compute_bottlenecks([], {})
        assert isinstance(result, BottleneckAnalyticsOut)
        assert result.items == []

    def test_groups_steps_by_title_and_template(self) -> None:
        step_id = uuid.uuid4()
        s1 = _make_step("completed", title="Review", template_step_id=step_id,
                        completed_at=NOW)
        s2 = _make_step("completed", title="Review", template_step_id=step_id,
                        completed_at=NOW)
        r1 = _make_run("completed", YESTERDAY, completed_at=NOW,
                       workflow_template_id=TMPL_ID, steps=[s1])
        r2 = _make_run("completed", YESTERDAY, completed_at=NOW,
                       workflow_template_id=TMPL_ID, steps=[s2])
        t1 = str(TMPL_ID)
        result = WorkflowAnalyticsService._compute_bottlenecks([r1, r2], {t1: "T"})
        assert len(result.items) == 1
        assert result.items[0].times_executed == 2
        assert result.items[0].step_name == "Review"

    def test_sorted_by_average_days_desc(self) -> None:
        fast_step = _make_step("completed", title="Fast",
                               completed_at=NOW - timedelta(seconds=100))
        slow_step = _make_step("completed", title="Slow", completed_at=NOW)
        r_fast = _make_run("completed", NOW - timedelta(seconds=110), completed_at=NOW,
                           steps=[fast_step])
        r_slow = _make_run("completed", TWO_DAYS_AGO, completed_at=NOW, steps=[slow_step])
        result = WorkflowAnalyticsService._compute_bottlenecks([r_fast, r_slow], {})
        # slow_step should come first (higher avg_days)
        assert result.items[0].step_name == "Slow"

    def test_blocked_count(self) -> None:
        s = _make_step("blocked", title="Gate")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        assert result.items[0].blocked_count == 1

    def test_skip_count(self) -> None:
        s = _make_step("skipped", title="Optional")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        assert result.items[0].skip_count == 1

    def test_standalone_template_label(self) -> None:
        s = _make_step("pending", title="Step X")
        r = _make_run("active", YESTERDAY, workflow_template_id=None, steps=[s])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        assert result.items[0].template_name == "Standalone"

    def test_completion_rate_computed(self) -> None:
        s_comp = _make_step("completed", title="Step", completed_at=NOW)
        s_pend = _make_step("pending", title="Step")
        r = _make_run("active", YESTERDAY, steps=[s_comp, s_pend])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        # One "Step" group with 1 completed / 2 total
        item = next(i for i in result.items if i.step_name == "Step")
        assert item.completion_rate == 0.5

    def test_avg_days_zero_when_no_completed_steps(self) -> None:
        s = _make_step("pending", title="Wait")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        assert result.items[0].average_days == 0.0


# ── 7. _compute_trends ────────────────────────────────────────────────────────

class TestComputeTrends:
    def test_bucket_count_equals_period(self) -> None:
        for period in (7, 30, 90):
            result = WorkflowAnalyticsService._compute_trends([], period)
            assert len(result.buckets) == period
            assert result.period == period

    def test_empty_runs_all_zeros(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 7)
        for b in result.buckets:
            assert b.runs_started == 0
            assert b.runs_completed == 0
            assert b.runs_cancelled == 0

    def test_run_started_counted_in_bucket(self) -> None:
        today = datetime.now(UTC).date()
        r = _make_run("active", started_at=datetime(today.year, today.month, today.day, tzinfo=UTC))
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        last_bucket = result.buckets[-1]
        assert last_bucket.runs_started == 1

    def test_completed_run_counted_by_completed_at(self) -> None:
        today = datetime.now(UTC).date()
        completed_today = datetime(today.year, today.month, today.day, tzinfo=UTC)
        r = _make_run("completed", started_at=completed_today - timedelta(days=1),
                      completed_at=completed_today)
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        last_bucket = result.buckets[-1]
        assert last_bucket.runs_completed == 1

    def test_cancelled_run_counted_by_cancelled_at(self) -> None:
        today = datetime.now(UTC).date()
        cancelled_today = datetime(today.year, today.month, today.day, tzinfo=UTC)
        r = _make_run("cancelled", started_at=cancelled_today - timedelta(days=1),
                      cancelled_at=cancelled_today)
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        last_bucket = result.buckets[-1]
        assert last_bucket.runs_cancelled == 1

    def test_run_outside_period_not_counted(self) -> None:
        old = datetime.now(UTC) - timedelta(days=200)
        r = _make_run("completed", started_at=old, completed_at=old)
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        total_started = sum(b.runs_started for b in result.buckets)
        total_completed = sum(b.runs_completed for b in result.buckets)
        assert total_started == 0
        assert total_completed == 0

    def test_completion_rate_in_bucket(self) -> None:
        today = datetime.now(UTC).date()
        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        comp = _make_run("completed", today_dt - timedelta(days=1), completed_at=today_dt)
        canc = _make_run("cancelled", today_dt - timedelta(days=1), cancelled_at=today_dt)
        result = WorkflowAnalyticsService._compute_trends([comp, canc], 7)
        last_bucket = result.buckets[-1]
        assert last_bucket.completion_rate == 0.5

    def test_buckets_ordered_chronologically(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 30)
        dates = [b.date for b in result.buckets]
        assert dates == sorted(dates)

    def test_period_7_buckets_isoformat_dates(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 7)
        for b in result.buckets:
            # Must be valid ISO date
            from datetime import date
            assert date.fromisoformat(b.date)


# ── 8. _compute_workload ──────────────────────────────────────────────────────

class TestComputeWorkload:
    def test_empty_runs_empty_items(self) -> None:
        result = WorkflowAnalyticsService._compute_workload([])
        assert isinstance(result, WorkloadAnalyticsOut)
        assert result.items == []

    def test_groups_by_owner_role(self) -> None:
        s_admin = _make_step("pending", owner_role="admin")
        s_member = _make_step("pending", owner_role="member")
        r = _make_run("active", YESTERDAY, steps=[s_admin, s_member])
        result = WorkflowAnalyticsService._compute_workload([r])
        roles = {i.owner for i in result.items}
        assert "admin" in roles
        assert "member" in roles

    def test_pending_steps_counted(self) -> None:
        s = _make_step("pending", owner_role="owner")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "owner")
        assert item.pending_steps == 1

    def test_in_progress_counted_as_pending(self) -> None:
        s = _make_step("in_progress", owner_role="owner")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "owner")
        assert item.pending_steps == 1

    def test_completed_steps_counted(self) -> None:
        s = _make_step("completed", owner_role="admin", completed_at=NOW)
        r = _make_run("completed", YESTERDAY, completed_at=NOW, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "admin")
        assert item.completed_steps == 1

    def test_blocked_steps_counted(self) -> None:
        s = _make_step("blocked", owner_role="member")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "member")
        assert item.blocked_steps == 1

    def test_completion_rate(self) -> None:
        c = _make_step("completed", owner_role="owner", completed_at=NOW)
        p = _make_step("pending", owner_role="owner")
        r = _make_run("active", YESTERDAY, steps=[c, p])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "owner")
        assert item.completion_rate == 0.5

    def test_avg_completion_days(self) -> None:
        s = _make_step("completed", owner_role="owner", completed_at=NOW)
        r = _make_run("completed", TWO_DAYS_AGO, completed_at=NOW, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "owner")
        assert item.average_completion_days > 0

    def test_sorted_alphabetically_by_role(self) -> None:
        s_owner = _make_step("pending", owner_role="owner")
        s_admin = _make_step("pending", owner_role="admin")
        r = _make_run("active", YESTERDAY, steps=[s_owner, s_admin])
        result = WorkflowAnalyticsService._compute_workload([r])
        owners = [i.owner for i in result.items]
        assert owners == sorted(owners)

    def test_skipped_steps_not_counted(self) -> None:
        s = _make_step("skipped", owner_role="viewer")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        # skipped steps are not counted in any bucket; viewer may not appear
        if any(i.owner == "viewer" for i in result.items):
            item = next(i for i in result.items if i.owner == "viewer")
            assert item.pending_steps + item.completed_steps + item.blocked_steps == 0


# ── 9. Async get_summary — cache hit ─────────────────────────────────────────

class TestGetSummaryCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self) -> None:
        svc = _make_svc()
        cached_result = AnalyticsSummaryOut(
            total_runs=5, active_runs=1, completed_runs=3, cancelled_runs=1,
            completion_rate=0.75, average_completion_days=2.0,
            average_step_completion_days=1.0, average_required_steps=3.0,
            average_optional_steps=1.0, data_integrity_warning=False,
        )
        redis = _make_redis(cached=cached_result.model_dump_json())

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_summary(WS_ID)

        assert result.total_runs == 5
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db_and_caches(self) -> None:
        svc = _make_svc()
        svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_summary(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once_with(WS_ID)
        redis.set.assert_called_once()
        assert result.total_runs == 0

    @pytest.mark.asyncio
    async def test_redis_failure_graceful_fallback(self) -> None:
        svc = _make_svc()
        svc._run_repo.find_all_for_workspace = AsyncMock(return_value=[])

        broken_redis = MagicMock()
        broken_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        broken_redis.set = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=broken_redis),
        ):
            result = await svc.get_summary(WS_ID)

        # Should still return computed result from DB
        assert isinstance(result, AnalyticsSummaryOut)


# ── 10. Async get_template_analytics — cache ──────────────────────────────────

class TestGetTemplateAnalyticsCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached_result = TemplateAnalyticsOut(items=[])
        redis = _make_redis(cached=cached_result.model_dump_json())

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_template_analytics(WS_ID)

        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_runs_and_templates(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_template_analytics(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once()
        svc._template_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self) -> None:
        svc = _make_svc()
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=Exception("down"))
        broken.set = AsyncMock(side_effect=Exception("down"))

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=broken),
        ):
            result = await svc.get_template_analytics(WS_ID)

        assert isinstance(result, TemplateAnalyticsOut)


# ── 11. Async get_bottlenecks — cache ────────────────────────────────────────

class TestGetBottlenecksCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached = BottleneckAnalyticsOut(items=[])
        redis = _make_redis(cached=cached.model_dump_json())

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_bottlenecks(WS_ID)

        assert result.items == []
        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_bottlenecks(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self) -> None:
        svc = _make_svc()
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=Exception("down"))
        broken.set = AsyncMock(side_effect=Exception("down"))

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=broken),
        ):
            result = await svc.get_bottlenecks(WS_ID)

        assert isinstance(result, BottleneckAnalyticsOut)


# ── 12. Async get_trends — cache ─────────────────────────────────────────────

class TestGetTrendsCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached = TrendAnalyticsOut(period=7, buckets=[])
        redis = _make_redis(cached=cached.model_dump_json())

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_trends(WS_ID, 7)

        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_trends(WS_ID, 30)

        svc._run_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_periods_use_different_cache_keys(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)
        set_calls: list[str] = []
        redis.set = AsyncMock(side_effect=lambda *a, **kw: set_calls.append(a[0]))

        ctx = _make_ctx()
        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_trends(WS_ID, 7)
            await svc.get_trends(WS_ID, 30)

        assert len(set_calls) == 2
        assert set_calls[0] != set_calls[1]

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self) -> None:
        svc = _make_svc()
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=Exception("down"))
        broken.set = AsyncMock(side_effect=Exception("down"))

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=broken),
        ):
            result = await svc.get_trends(WS_ID, 90)

        assert isinstance(result, TrendAnalyticsOut)
        assert result.period == 90
        assert len(result.buckets) == 90


# ── 13. Async get_workload — cache ────────────────────────────────────────────

class TestGetWorkloadCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        svc = _make_svc()
        cached = WorkloadAnalyticsOut(items=[])
        redis = _make_redis(cached=cached.model_dump_json())

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            result = await svc.get_workload(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_workload(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self) -> None:
        svc = _make_svc()
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=Exception("down"))
        broken.set = AsyncMock(side_effect=Exception("down"))

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=broken),
        ):
            result = await svc.get_workload(WS_ID)

        assert isinstance(result, WorkloadAnalyticsOut)


# ── 14. Tenant isolation ──────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_summary_uses_tenant_context_in_cache_key(self) -> None:
        org_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        org_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        key_a = _analytics_summary_key(org_a, WS_ID)
        key_b = _analytics_summary_key(org_b, WS_ID)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_get_summary_passes_workspace_to_repo(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_summary(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once_with(WS_ID)

    @pytest.mark.asyncio
    async def test_get_templates_passes_workspace_to_both_repos(self) -> None:
        svc = _make_svc()
        redis = _make_redis(cached=None)

        with (
            patch("corpmind.modules.workflows.service.get_tenant_context", return_value=_make_ctx()),
            patch("corpmind.modules.workflows.service.get_redis", return_value=redis),
        ):
            await svc.get_template_analytics(WS_ID)

        svc._run_repo.find_all_for_workspace.assert_called_once_with(WS_ID)
        svc._template_repo.find_all_for_workspace.assert_called_once_with(WS_ID)

    @pytest.mark.asyncio
    async def test_different_workspaces_use_different_cache_keys(self) -> None:
        ws1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
        ws2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
        k1 = _analytics_summary_key(ORG_ID, ws1)
        k2 = _analytics_summary_key(ORG_ID, ws2)
        assert k1 != k2


# ── 15. _compute_summary — edge cases ────────────────────────────────────────

class TestComputeSummaryEdgeCases:
    def test_pending_status_counted_as_active(self) -> None:
        r = _make_run(status="pending", started_at=YESTERDAY)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.active_runs == 1

    def test_both_pending_and_active_counted(self) -> None:
        runs = [
            _make_run("pending", YESTERDAY),
            _make_run("active", YESTERDAY),
        ]
        result = WorkflowAnalyticsService._compute_summary(runs)
        assert result.active_runs == 2

    def test_completed_run_with_null_completed_at_excluded_from_avg(self) -> None:
        r = _make_run("completed", YESTERDAY, completed_at=None)
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_completion_days == 0.0

    def test_step_with_null_completed_at_excluded_from_avg(self) -> None:
        step = _make_step("completed", completed_at=None)
        r = _make_run("active", YESTERDAY, steps=[step])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_step_completion_days == 0.0

    def test_run_with_no_steps_contributes_zero_counts(self) -> None:
        r = _make_run("active", YESTERDAY, steps=[])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_required_steps == 0.0
        assert result.average_optional_steps == 0.0

    def test_completion_rate_zero_when_all_active(self) -> None:
        runs = [_make_run("active", YESTERDAY), _make_run("active", YESTERDAY)]
        result = WorkflowAnalyticsService._compute_summary(runs)
        assert result.completion_rate == 0.0

    def test_mixed_step_completion_contributes_to_avg(self) -> None:
        step1 = _make_step("completed", completed_at=NOW)
        step2 = _make_step("completed", completed_at=NOW + timedelta(days=1))
        r = _make_run("active", TWO_DAYS_AGO, steps=[step1, step2])
        result = WorkflowAnalyticsService._compute_summary([r])
        assert result.average_step_completion_days > 0


# ── 16. _compute_template_analytics — edge cases ──────────────────────────────

class TestComputeTemplateAnalyticsEdgeCases:
    def test_all_cancelled_completion_rate_zero(self) -> None:
        t1 = str(TMPL_ID)
        r = _make_run("cancelled", YESTERDAY, cancelled_at=NOW,
                      workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics([r], {t1: "T"})
        assert result.items[0].completion_rate == 0.0

    def test_active_only_run_completion_rate_zero(self) -> None:
        t1 = str(TMPL_ID)
        r = _make_run("active", YESTERDAY, workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics([r], {t1: "T"})
        assert result.items[0].completion_rate == 0.0

    def test_completed_without_timestamps_avg_zero(self) -> None:
        t1 = str(TMPL_ID)
        r = _make_run("completed", started_at=None, completed_at=None,
                      workflow_template_id=TMPL_ID)
        r.started_at = None
        r.completed_at = None
        result = WorkflowAnalyticsService._compute_template_analytics([r], {t1: "T"})
        assert result.items[0].average_completion_days == 0.0

    def test_multiple_templates_returned(self) -> None:
        t1 = str(TMPL_ID)
        t2 = str(uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
        r1 = _make_run("active", YESTERDAY, workflow_template_id=TMPL_ID)
        r2 = _make_run("active", YESTERDAY,
                       workflow_template_id=uuid.UUID(t2))
        result = WorkflowAnalyticsService._compute_template_analytics(
            [r1, r2], {t1: "A", t2: "B"}
        )
        assert len(result.items) == 2

    def test_template_id_field_populated(self) -> None:
        t1 = str(TMPL_ID)
        r = _make_run("active", YESTERDAY, workflow_template_id=TMPL_ID)
        result = WorkflowAnalyticsService._compute_template_analytics([r], {t1: "T"})
        assert result.items[0].template_id == t1


# ── 17. _compute_bottlenecks — edge cases ────────────────────────────────────

class TestComputeBottlenecksEdgeCases:
    def test_steps_from_different_runs_grouped_together(self) -> None:
        step_id = uuid.uuid4()
        s1 = _make_step("completed", title="Gate", template_step_id=step_id, completed_at=NOW)
        s2 = _make_step("completed", title="Gate", template_step_id=step_id, completed_at=NOW)
        r1 = _make_run("completed", YESTERDAY, completed_at=NOW,
                       workflow_template_id=TMPL_ID, steps=[s1])
        r2 = _make_run("completed", YESTERDAY, completed_at=NOW,
                       workflow_template_id=TMPL_ID, steps=[s2])
        t1 = str(TMPL_ID)
        result = WorkflowAnalyticsService._compute_bottlenecks([r1, r2], {t1: "T"})
        assert result.items[0].times_executed == 2

    def test_steps_with_no_template_step_id_grouped_by_title(self) -> None:
        s1 = _make_step("pending", title="Unique", template_step_id=None)
        s2 = _make_step("pending", title="Unique", template_step_id=None)
        r1 = _make_run("active", YESTERDAY, steps=[s1])
        r2 = _make_run("active", YESTERDAY, steps=[s2])
        result = WorkflowAnalyticsService._compute_bottlenecks([r1, r2], {})
        unique_items = [i for i in result.items if i.step_name == "Unique"]
        assert len(unique_items) == 1
        assert unique_items[0].times_executed == 2

    def test_multiple_step_types_in_one_run(self) -> None:
        s1 = _make_step("completed", title="Review", completed_at=NOW)
        s2 = _make_step("blocked", title="Approval")
        r = _make_run("active", YESTERDAY, steps=[s1, s2])
        result = WorkflowAnalyticsService._compute_bottlenecks([r], {})
        step_names = {i.step_name for i in result.items}
        assert "Review" in step_names
        assert "Approval" in step_names


# ── 18. _compute_trends — edge cases ─────────────────────────────────────────

class TestComputeTrendsEdgeCases:
    def test_period_7_exactly_7_buckets(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 7)
        assert len(result.buckets) == 7

    def test_period_90_exactly_90_buckets(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 90)
        assert len(result.buckets) == 90

    def test_multiple_runs_on_same_day_aggregated(self) -> None:
        today = datetime.now(UTC).date()
        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        runs = [
            _make_run("active", started_at=today_dt),
            _make_run("active", started_at=today_dt),
            _make_run("active", started_at=today_dt),
        ]
        result = WorkflowAnalyticsService._compute_trends(runs, 7)
        assert result.buckets[-1].runs_started == 3

    def test_completion_rate_zero_when_no_finished_runs(self) -> None:
        today = datetime.now(UTC).date()
        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        r = _make_run("active", started_at=today_dt)
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        assert result.buckets[-1].completion_rate == 0.0

    def test_bucket_date_string_format(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 7)
        for b in result.buckets:
            parts = b.date.split("-")
            assert len(parts) == 3

    def test_return_type(self) -> None:
        result = WorkflowAnalyticsService._compute_trends([], 30)
        assert isinstance(result, TrendAnalyticsOut)
        assert result.period == 30

    def test_run_without_started_at_not_counted(self) -> None:
        r = _make_run("active", started_at=None)
        r.started_at = None
        result = WorkflowAnalyticsService._compute_trends([r], 7)
        total = sum(b.runs_started for b in result.buckets)
        assert total == 0


# ── 19. _compute_workload — edge cases ────────────────────────────────────────

class TestComputeWorkloadEdgeCases:
    def test_step_with_no_run_steps_not_in_workload(self) -> None:
        r = _make_run("active", YESTERDAY, steps=[])
        result = WorkflowAnalyticsService._compute_workload([r])
        assert result.items == []

    def test_only_skipped_steps_not_counted(self) -> None:
        s = _make_step("skipped", owner_role="owner")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        # skipped not in pending/completed/blocked — owner may not appear
        if result.items:
            item = result.items[0]
            assert item.pending_steps == 0
            assert item.completed_steps == 0
            assert item.blocked_steps == 0

    def test_avg_days_zero_when_no_completed_steps(self) -> None:
        s = _make_step("pending", owner_role="member")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "member")
        assert item.average_completion_days == 0.0

    def test_completion_rate_zero_when_only_pending(self) -> None:
        s = _make_step("pending", owner_role="admin")
        r = _make_run("active", YESTERDAY, steps=[s])
        result = WorkflowAnalyticsService._compute_workload([r])
        item = next(i for i in result.items if i.owner == "admin")
        assert item.completion_rate == 0.0

    def test_all_roles_from_multiple_runs(self) -> None:
        r1 = _make_run("active", YESTERDAY, steps=[_make_step("pending", owner_role="owner")])
        r2 = _make_run("active", YESTERDAY, steps=[_make_step("pending", owner_role="viewer")])
        result = WorkflowAnalyticsService._compute_workload([r1, r2])
        owners = {i.owner for i in result.items}
        assert "owner" in owners
        assert "viewer" in owners
