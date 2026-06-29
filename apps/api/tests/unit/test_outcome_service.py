"""Unit tests for RecommendationOutcomeService (Sprint 26B).

All metrics are derived deterministically from execution timestamps.
No database required — repo methods are patched with in-memory fixtures.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    ExecutionSummaryOut,
    OutcomeTypeItemOut,
    RecommendationOutcomesOut,
)
from corpmind.modules.analytics.service import (
    RecommendationOutcomeService,
    _OVERDUE_THRESHOLD_DAYS,
    _mean,
)

# ── helpers ───────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WS_ID = uuid.uuid4()

NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
D1 = NOW - timedelta(days=1)
D3 = NOW - timedelta(days=3)
D7 = NOW - timedelta(days=7)
D14 = NOW - timedelta(days=14)
D15 = NOW - timedelta(days=15)
D20 = NOW - timedelta(days=20)


def _make_action(
    execution_status: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    blocked_at: datetime | None = None,
    cancelled_at: datetime | None = None,
    blocked_reason: str | None = None,
    completion_notes: str | None = None,
    created_at: datetime | None = None,
    action_type: str = "accepted",
    rec_type: str = "pricing",
) -> MagicMock:
    row = MagicMock()
    row.recommendation_id = uuid.uuid4()
    row.action_type = action_type
    row.execution_status = execution_status
    row.started_at = started_at
    row.completed_at = completed_at
    row.blocked_at = blocked_at
    row.cancelled_at = cancelled_at
    row.blocked_reason = blocked_reason
    row.completion_notes = completion_notes
    row.created_at = created_at or D7
    row.updated_at = NOW
    row._rec_type = rec_type  # used by snap mock
    return row


class _PatchSet:
    """Async context manager that wires standard patches for outcome service tests."""

    def __init__(self, rows: list, snaps: dict[uuid.UUID, str] | None = None) -> None:
        self._rows = rows
        self._snaps = snaps or {}
        self.redis = MagicMock()
        self.redis.get = AsyncMock(return_value=None)
        self.redis.set = AsyncMock()
        self.redis.delete = AsyncMock()

    @asynccontextmanager
    async def __call__(self):
        ctx = MagicMock()
        ctx.org_id = TENANT_ID

        def _snap_side_effect(*, workspace_id: uuid.UUID, recommendation_id: uuid.UUID):  # noqa: ARG001
            rec_type = self._snaps.get(recommendation_id)
            if rec_type is None:
                return None
            snap = MagicMock()
            snap.rec_type = rec_type
            return snap

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=ctx,
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=self.redis,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new=AsyncMock(return_value=self._rows),
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new=AsyncMock(side_effect=_snap_side_effect),
            ),
        ):
            yield self


def _svc() -> RecommendationOutcomeService:
    return RecommendationOutcomeService(MagicMock())


# ── _mean helper ──────────────────────────────────────────────────────────────


class TestMeanHelper:
    def test_empty_returns_zero(self):
        assert _mean([]) == 0.0

    def test_single(self):
        assert _mean([4.0]) == 4.0

    def test_multiple(self):
        assert _mean([1.0, 3.0]) == 2.0

    def test_fractional(self):
        result = _mean([1.0, 2.0, 3.0])
        assert abs(result - 2.0) < 1e-9


# ── ExecutionSummaryOut — counts ──────────────────────────────────────────────


class TestExecutionSummaryCounts:
    @pytest.mark.asyncio
    async def test_empty_workspace(self):
        ps = _PatchSet([])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.accepted == 0
        assert result.started == 0
        assert result.completed == 0
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_counts_only_accepted_rows(self):
        dismissed = _make_action(action_type="dismissed")
        accepted = _make_action(execution_status=None)
        ps = _PatchSet([dismissed, accepted])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.accepted == 1

    @pytest.mark.asyncio
    async def test_five_rows_sufficient_data(self):
        rows = [_make_action() for _ in range(5)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.insufficient_data is False

    @pytest.mark.asyncio
    async def test_four_rows_insufficient(self):
        rows = [_make_action() for _ in range(4)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_started_count(self):
        rows = [
            _make_action(started_at=D3),
            _make_action(started_at=None),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.started == 1

    @pytest.mark.asyncio
    async def test_wip_count(self):
        rows = [
            _make_action(execution_status="in_progress", started_at=D1),
            _make_action(execution_status="in_progress", started_at=D3),
            _make_action(execution_status="completed", started_at=D7, completed_at=D1),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.work_in_progress == 2
        assert result.completed == 1


# ── ExecutionSummaryOut — rates ───────────────────────────────────────────────


class TestExecutionSummaryRates:
    @pytest.mark.asyncio
    async def test_completion_rate_zero_when_none_completed(self):
        rows = [_make_action(execution_status=None) for _ in range(3)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.completion_rate == 0.0

    @pytest.mark.asyncio
    async def test_completion_rate_full(self):
        rows = [
            _make_action(execution_status="completed", started_at=D7, completed_at=D3)
            for _ in range(4)
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.completion_rate == 1.0

    @pytest.mark.asyncio
    async def test_completion_rate_partial(self):
        rows = [
            _make_action(execution_status="completed", started_at=D7, completed_at=D3),
            _make_action(execution_status=None),
            _make_action(execution_status=None),
            _make_action(execution_status=None),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.completion_rate - 0.25) < 1e-4

    @pytest.mark.asyncio
    async def test_block_rate(self):
        rows = [
            _make_action(execution_status="blocked", blocked_at=D3),
            _make_action(execution_status=None),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.block_rate - 0.5) < 1e-4

    @pytest.mark.asyncio
    async def test_cancellation_rate(self):
        rows = [
            _make_action(execution_status="cancelled", cancelled_at=D3),
            _make_action(execution_status="cancelled", cancelled_at=D1),
            _make_action(execution_status=None),
            _make_action(execution_status=None),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.cancellation_rate - 0.5) < 1e-4

    @pytest.mark.asyncio
    async def test_rates_zero_when_no_accepted(self):
        ps = _PatchSet([])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.completion_rate == 0.0
        assert result.block_rate == 0.0
        assert result.cancellation_rate == 0.0


# ── ExecutionSummaryOut — averages ────────────────────────────────────────────


class TestExecutionSummaryAverages:
    @pytest.mark.asyncio
    async def test_avg_days_to_start(self):
        # created_at = D7, started_at = D3 → 4 days; created_at = D7, started_at = D1 → 6 days
        rows = [
            _make_action(started_at=D3, created_at=D7),
            _make_action(started_at=D1, created_at=D7),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        # (4 + 6) / 2 = 5
        assert abs(result.avg_days_to_start - 5.0) < 0.1

    @pytest.mark.asyncio
    async def test_avg_days_to_start_zero_when_none_started(self):
        rows = [_make_action(started_at=None)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.avg_days_to_start == 0.0

    @pytest.mark.asyncio
    async def test_avg_days_to_complete(self):
        # started D7, completed D3 → 4 days
        rows = [
            _make_action(
                execution_status="completed",
                started_at=D7,
                completed_at=D3,
                created_at=D20,
            )
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_to_complete - 4.0) < 0.1

    @pytest.mark.asyncio
    async def test_avg_days_to_complete_zero_when_none(self):
        rows = [_make_action(execution_status="in_progress", started_at=D3)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.avg_days_to_complete == 0.0

    @pytest.mark.asyncio
    async def test_avg_days_blocked_currently_blocked(self):
        # blocked 3 days ago, still blocked
        rows = [
            _make_action(execution_status="blocked", blocked_at=D3),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_blocked - 3.0) < 0.1

    @pytest.mark.asyncio
    async def test_avg_days_blocked_completed_after_block(self):
        # blocked D7, completed D3 → blocked for 4 days
        rows = [
            _make_action(
                execution_status="completed",
                blocked_at=D7,
                completed_at=D3,
                started_at=D14,
            )
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_blocked - 4.0) < 0.1

    @pytest.mark.asyncio
    async def test_avg_days_blocked_zero_when_no_blocked(self):
        rows = [_make_action(execution_status="completed", started_at=D7, completed_at=D3)]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.avg_days_blocked == 0.0

    @pytest.mark.asyncio
    async def test_avg_days_cancelled(self):
        # created D14, cancelled D7 → 7 days
        rows = [
            _make_action(
                execution_status="cancelled",
                cancelled_at=D7,
                created_at=D14,
            )
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_cancelled - 7.0) < 0.1


# ── Overdue detection ─────────────────────────────────────────────────────────


class TestOverdueDetection:
    @pytest.mark.asyncio
    async def test_overdue_threshold_exact(self):
        # started exactly _OVERDUE_THRESHOLD_DAYS ago → overdue
        overdue_start = NOW - timedelta(days=_OVERDUE_THRESHOLD_DAYS)
        rows = [
            _make_action(execution_status="in_progress", started_at=overdue_start),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.overdue == 1

    @pytest.mark.asyncio
    async def test_not_overdue_before_threshold(self):
        # started 13 days ago → not overdue
        start = NOW - timedelta(days=_OVERDUE_THRESHOLD_DAYS - 1)
        rows = [
            _make_action(execution_status="in_progress", started_at=start),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.overdue == 0

    @pytest.mark.asyncio
    async def test_completed_not_counted_as_overdue(self):
        rows = [
            _make_action(
                execution_status="completed",
                started_at=D20,
                completed_at=D7,
            )
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.overdue == 0

    @pytest.mark.asyncio
    async def test_multiple_overdue(self):
        start = NOW - timedelta(days=20)
        rows = [
            _make_action(execution_status="in_progress", started_at=start),
            _make_action(execution_status="in_progress", started_at=start),
            _make_action(execution_status="in_progress", started_at=D1),  # not overdue
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.overdue == 2


# ── Redis cache ───────────────────────────────────────────────────────────────


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_summary_cache_hit_skips_db(self):
        cached = ExecutionSummaryOut(
            accepted=3,
            started=2,
            completed=1,
            blocked=0,
            cancelled=0,
            completion_rate=0.333,
            cancellation_rate=0.0,
            block_rate=0.0,
            avg_days_to_start=1.5,
            avg_days_to_complete=3.0,
            avg_days_blocked=0.0,
            avg_days_cancelled=0.0,
            work_in_progress=1,
            overdue=0,
            insufficient_data=True,
        )
        ps = _PatchSet([])
        ps.redis.get = AsyncMock(return_value=cached.model_dump_json())
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.accepted == 3

    @pytest.mark.asyncio
    async def test_outcomes_cache_hit(self):
        cached = RecommendationOutcomesOut(
            completed=2,
            blocked=0,
            cancelled=1,
            in_progress=0,
            ready=0,
            by_rec_type=[],
            insufficient_data=True,
        )
        ps = _PatchSet([])
        ps.redis.get = AsyncMock(return_value=cached.model_dump_json())
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.completed == 2

    @pytest.mark.asyncio
    async def test_redis_failure_graceful_fallback(self):
        rows = [_make_action(execution_status="completed", started_at=D7, completed_at=D3)]
        ps = _PatchSet(rows)
        ps.redis.get = AsyncMock(side_effect=Exception("redis down"))
        ps.redis.set = AsyncMock(side_effect=Exception("redis down"))
        snaps = {rows[0].recommendation_id: "pricing"}
        ps._snaps = snaps
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.completed == 1


# ── Outcomes — per-type grouping ──────────────────────────────────────────────


class TestOutcomesPerType:
    def _make_rows_with_types(self) -> tuple[list, dict]:
        r1 = _make_action(execution_status="completed", started_at=D7, completed_at=D3, rec_type="pricing")
        r2 = _make_action(execution_status=None, rec_type="pricing")
        r3 = _make_action(execution_status="in_progress", started_at=D3, rec_type="segment")
        r4 = _make_action(execution_status="cancelled", cancelled_at=D1, rec_type="segment")
        rows = [r1, r2, r3, r4]
        snaps = {
            r.recommendation_id: r._rec_type for r in rows
        }
        return rows, snaps

    @pytest.mark.asyncio
    async def test_grouped_by_type(self):
        rows, snaps = self._make_rows_with_types()
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        types = {t.rec_type for t in result.by_rec_type}
        assert types == {"pricing", "segment"}

    @pytest.mark.asyncio
    async def test_per_type_counts(self):
        rows, snaps = self._make_rows_with_types()
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        pricing = next(t for t in result.by_rec_type if t.rec_type == "pricing")
        segment = next(t for t in result.by_rec_type if t.rec_type == "segment")
        assert pricing.accepted == 2
        assert pricing.completed == 1
        assert segment.accepted == 2
        assert segment.cancelled == 1

    @pytest.mark.asyncio
    async def test_per_type_completion_rate(self):
        rows, snaps = self._make_rows_with_types()
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        pricing = next(t for t in result.by_rec_type if t.rec_type == "pricing")
        # 1 completed out of 2 accepted
        assert abs(pricing.completion_rate - 0.5) < 1e-4

    @pytest.mark.asyncio
    async def test_per_type_avg_days_to_complete(self):
        # completed: started D7, completed D3 → 4 days
        rows, snaps = self._make_rows_with_types()
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        pricing = next(t for t in result.by_rec_type if t.rec_type == "pricing")
        assert abs(pricing.avg_days_to_complete - 4.0) < 0.1

    @pytest.mark.asyncio
    async def test_unknown_type_when_snap_missing(self):
        r = _make_action(execution_status=None)
        ps = _PatchSet([r], {})  # no snap → rec_type defaults to "unknown"
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        types = {t.rec_type for t in result.by_rec_type}
        assert "unknown" in types

    @pytest.mark.asyncio
    async def test_status_bucket_counts(self):
        rows, snaps = self._make_rows_with_types()
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.completed == 1
        assert result.cancelled == 1
        assert result.in_progress == 1
        assert result.ready == 1

    @pytest.mark.asyncio
    async def test_insufficient_data_under_five(self):
        rows = [_make_action() for _ in range(3)]
        snaps = {r.recommendation_id: "pricing" for r in rows}
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_types_sorted_alphabetically(self):
        r_z = _make_action(rec_type="z_type")
        r_a = _make_action(rec_type="a_type")
        snaps = {r_z.recommendation_id: "z_type", r_a.recommendation_id: "a_type"}
        ps = _PatchSet([r_z, r_a], snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.by_rec_type[0].rec_type == "a_type"
        assert result.by_rec_type[1].rec_type == "z_type"

    @pytest.mark.asyncio
    async def test_empty_outcomes(self):
        ps = _PatchSet([])
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.by_rec_type == []
        assert result.completed == 0
        assert result.ready == 0


# ── Tenant isolation ──────────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_summary_uses_tenant_context(self):
        ps = _PatchSet([])
        tenant_b = uuid.uuid4()
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        # Verifying the cache key used tenant A's org_id (not tenant B)
        call_args = ps.redis.set.call_args
        if call_args:
            key = call_args[0][0]
            assert str(TENANT_ID) in key
            assert str(tenant_b) not in key

    @pytest.mark.asyncio
    async def test_outcomes_uses_tenant_context(self):
        ps = _PatchSet([])
        tenant_b = uuid.uuid4()
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        call_args = ps.redis.set.call_args
        if call_args:
            key = call_args[0][0]
            assert str(TENANT_ID) in key
            assert str(tenant_b) not in key

    @pytest.mark.asyncio
    async def test_no_automatic_actions_triggered(self):
        rows = [_make_action(execution_status="completed", started_at=D7, completed_at=D3)]
        snaps = {rows[0].recommendation_id: "pricing"}
        ps = _PatchSet(rows, snaps)
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context") as mock_ctx,
            patch("corpmind.modules.analytics.service.get_redis", return_value=ps.redis),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new=AsyncMock(return_value=rows),
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new=AsyncMock(side_effect=lambda **kw: (lambda s: s)(MagicMock(rec_type="pricing"))),
            ),
        ):
            mock_ctx.return_value.org_id = TENANT_ID
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        # Read-only: only set (cache write) and get (cache read), no transitions
        assert result.completed == 1


# ── Schema validation ─────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_execution_summary_schema(self):
        s = ExecutionSummaryOut(
            accepted=10,
            started=8,
            completed=5,
            blocked=1,
            cancelled=2,
            completion_rate=0.5,
            cancellation_rate=0.2,
            block_rate=0.1,
            avg_days_to_start=1.5,
            avg_days_to_complete=4.0,
            avg_days_blocked=2.0,
            avg_days_cancelled=5.0,
            work_in_progress=2,
            overdue=1,
            insufficient_data=False,
        )
        assert s.accepted == 10
        assert s.insufficient_data is False

    def test_outcome_type_item_schema(self):
        item = OutcomeTypeItemOut(
            rec_type="pricing",
            accepted=5,
            completed=3,
            cancelled=1,
            blocked=1,
            completion_rate=0.6,
            avg_days_to_complete=3.5,
            avg_days_to_start=1.2,
        )
        assert item.rec_type == "pricing"
        assert item.completion_rate == 0.6

    def test_outcomes_schema(self):
        out = RecommendationOutcomesOut(
            completed=3,
            blocked=1,
            cancelled=2,
            in_progress=1,
            ready=3,
            by_rec_type=[],
            insufficient_data=False,
        )
        assert out.by_rec_type == []
        assert out.insufficient_data is False


# ── Avg blocked — mixed active and completed-after-block ─────────────────────


class TestAvgBlockedMixed:
    @pytest.mark.asyncio
    async def test_avg_blocked_includes_both_active_and_historical(self):
        # active blocked 3 days → 3d; completed after 7d blocked → 7d; mean = 5d
        r_active = _make_action(execution_status="blocked", blocked_at=D3)
        r_hist = _make_action(
            execution_status="completed",
            blocked_at=D7,
            completed_at=NOW,
            started_at=D14,
        )
        ps = _PatchSet([r_active, r_hist])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        # (3 + 7) / 2 = 5
        assert abs(result.avg_days_blocked - 5.0) < 0.1

    @pytest.mark.asyncio
    async def test_in_progress_without_blocked_at_excluded(self):
        # in_progress but no blocked_at → not counted in avg_days_blocked
        row = _make_action(execution_status="in_progress", started_at=D3, blocked_at=None)
        ps = _PatchSet([row])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.avg_days_blocked == 0.0


# ── Cache keys ────────────────────────────────────────────────────────────────


class TestCacheKeys:
    @pytest.mark.asyncio
    async def test_summary_cache_key_contains_tenant_and_workspace(self):
        ps = _PatchSet([])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                await _svc().get_execution_summary(WS_ID)
        set_args = ps.redis.set.call_args
        assert set_args is not None
        key = set_args[0][0]
        assert str(TENANT_ID) in key
        assert str(WS_ID) in key
        assert "execution_summary" in key

    @pytest.mark.asyncio
    async def test_outcomes_cache_key_contains_tenant_and_workspace(self):
        ps = _PatchSet([])
        async with ps():
            await _svc().get_outcomes(WS_ID)
        set_args = ps.redis.set.call_args
        assert set_args is not None
        key = set_args[0][0]
        assert str(TENANT_ID) in key
        assert str(WS_ID) in key
        assert "recommendation_outcomes" in key

    @pytest.mark.asyncio
    async def test_summary_cache_ttl_is_set(self):
        ps = _PatchSet([])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                await _svc().get_execution_summary(WS_ID)
        set_args = ps.redis.set.call_args
        assert set_args is not None
        assert set_args[1].get("ex") == 300

    @pytest.mark.asyncio
    async def test_outcomes_cache_ttl_is_set(self):
        ps = _PatchSet([])
        async with ps():
            await _svc().get_outcomes(WS_ID)
        set_args = ps.redis.set.call_args
        assert set_args is not None
        assert set_args[1].get("ex") == 300


# ── Read-only contract ────────────────────────────────────────────────────────


class TestReadOnlyContract:
    @pytest.mark.asyncio
    async def test_get_execution_summary_never_calls_update_execution(self):
        rows = [_make_action(execution_status="in_progress", started_at=D3)]
        ps = _PatchSet(rows)
        update_mock = AsyncMock()
        with patch(
            "corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
            new=update_mock,
        ):
            async with ps():
                with patch(
                    "corpmind.modules.analytics.service.datetime"
                ) as mock_dt:
                    mock_dt.now.return_value = NOW
                    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                    await _svc().get_execution_summary(WS_ID)
        update_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_outcomes_never_calls_update_execution(self):
        rows = [_make_action(execution_status="completed", started_at=D7, completed_at=D3)]
        snaps = {rows[0].recommendation_id: "pricing"}
        ps = _PatchSet(rows, snaps)
        update_mock = AsyncMock()
        with patch(
            "corpmind.modules.analytics.repo.RecommendationActionRepo.update_execution",
            new=update_mock,
        ):
            async with ps():
                await _svc().get_outcomes(WS_ID)
        update_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_not_counting_non_accepted(self):
        # dismissed and snoozed rows must NOT appear in summary counts
        dismissed = _make_action(action_type="dismissed")
        snoozed = _make_action(action_type="snoozed")
        accepted = _make_action(execution_status="completed", started_at=D7, completed_at=D3)
        ps = _PatchSet([dismissed, snoozed, accepted])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.accepted == 1
        assert result.completed == 1


# ── Single-item averages ──────────────────────────────────────────────────────


class TestSingleItemAverages:
    @pytest.mark.asyncio
    async def test_single_completed_row_avg_complete(self):
        # started D7 → completed D3: exactly 4 days
        row = _make_action(
            execution_status="completed",
            started_at=D7,
            completed_at=D3,
            created_at=D20,
        )
        ps = _PatchSet([row])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_to_complete - 4.0) < 0.01

    @pytest.mark.asyncio
    async def test_single_started_avg_start(self):
        # created D14, started D7: 7 days
        row = _make_action(started_at=D7, created_at=D14)
        ps = _PatchSet([row])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_to_start - 7.0) < 0.01

    @pytest.mark.asyncio
    async def test_single_cancelled_avg_days_cancelled(self):
        # created D14, cancelled D7: 7 days
        row = _make_action(
            execution_status="cancelled",
            cancelled_at=D7,
            created_at=D14,
        )
        ps = _PatchSet([row])
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert abs(result.avg_days_cancelled - 7.0) < 0.01


# ── Full workflow scenario ────────────────────────────────────────────────────


class TestFullWorkflowScenario:
    @pytest.mark.asyncio
    async def test_mixed_statuses_all_counts_correct(self):
        rows = [
            _make_action(execution_status="completed", started_at=D7, completed_at=D3),
            _make_action(execution_status="completed", started_at=D14, completed_at=D7),
            _make_action(execution_status="in_progress", started_at=D1),
            _make_action(execution_status="blocked", blocked_at=D3),
            _make_action(execution_status="cancelled", cancelled_at=D1),
            _make_action(execution_status=None),
        ]
        ps = _PatchSet(rows)
        async with ps():
            with patch(
                "corpmind.modules.analytics.service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = NOW
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                result = await _svc().get_execution_summary(WS_ID)
        assert result.accepted == 6
        assert result.completed == 2
        assert result.work_in_progress == 1
        assert result.blocked == 1
        assert result.cancelled == 1
        assert result.started == 3  # only completed×2 and in_progress have started_at
        assert abs(result.completion_rate - (2 / 6)) < 1e-4
        assert abs(result.block_rate - (1 / 6)) < 1e-4
        assert abs(result.cancellation_rate - (1 / 6)) < 1e-4

    @pytest.mark.asyncio
    async def test_outcomes_full_scenario_status_buckets(self):
        rows = [
            _make_action(execution_status="completed", started_at=D7, completed_at=D3),
            _make_action(execution_status="in_progress", started_at=D1),
            _make_action(execution_status="blocked", blocked_at=D3),
            _make_action(execution_status="cancelled", cancelled_at=D1),
            _make_action(execution_status=None),
        ]
        snaps = {r.recommendation_id: "pricing" for r in rows}
        ps = _PatchSet(rows, snaps)
        async with ps():
            result = await _svc().get_outcomes(WS_ID)
        assert result.completed == 1
        assert result.in_progress == 1
        assert result.blocked == 1
        assert result.cancelled == 1
        assert result.ready == 1
