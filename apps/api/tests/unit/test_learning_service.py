"""Unit tests for RecommendationLearningService (Sprint 27).

Tests cover:
- _compute_delta static helper
- _adoption_rate / _success_rate / _execution_rate helpers
- _compare_versions static method
- _build_summary deterministic template
- get_learning: cache hit / miss / Redis failure / insufficient data / happy path
- get_version_history: cache hit / miss / Redis failure / insufficient data / happy path
- Version ordering (newest first)
- Quality score window fallback
- Tenant isolation
- Schema validation
"""

from __future__ import annotations

import json
import uuid
from contextlib import ExitStack
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.schemas import (
    LearningComparisonOut,
    LearningOut,
    LearningVersionOut,
    LearningSummaryOut,
    VersionHistoryOut,
)
from corpmind.modules.analytics.service import RecommendationLearningService


# ── fixtures ──────────────────────────────────────────────────────────────────

WS = uuid.uuid4()
ORG = uuid.uuid4()

DATE_NEW = date(2026, 6, 20)
DATE_OLD = date(2026, 6, 13)
DATE_OLDER = date(2026, 6, 6)


def _make_version(
    snap_date: date,
    generated: int = 5,
    avg_conf: float = 70.0,
    acted: int = 3,
    successful: int = 2,
    quality: float | None = 80.0,
) -> LearningVersionOut:
    return LearningVersionOut(
        version=snap_date.isoformat(),
        first_seen=snap_date,
        last_seen=snap_date,
        recommendations_generated=generated,
        acted=acted,
        completed=successful,
        successful=successful,
        avg_confidence=avg_conf,
        quality_score=quality,
    )


class _PatchSet:
    """Context manager that patches all external calls for RecommendationLearningService."""

    def __init__(
        self,
        versions_raw: list[tuple[date, int, float]] | None = None,
        outcome_map: dict[date, tuple[int, int]] | None = None,
        quality_map: dict[date, float] | None = None,
        redis_cached: str | None = None,
        redis_raises: bool = False,
    ) -> None:
        self.versions_raw = versions_raw or []
        self.outcome_map = outcome_map or {}
        self.quality_map = quality_map or {}
        self.redis_cached = redis_cached
        self.redis_raises = redis_raises
        self._stack = ExitStack()
        self.redis = MagicMock()

    def __enter__(self) -> "_PatchSet":
        mock_ctx = MagicMock()
        mock_ctx.org_id = ORG
        self._stack.enter_context(
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=mock_ctx,
            )
        )

        if self.redis_raises:
            self.redis.get = AsyncMock(side_effect=Exception("redis down"))
            self.redis.set = AsyncMock(side_effect=Exception("redis down"))
        else:
            self.redis.get = AsyncMock(return_value=self.redis_cached)
            self.redis.set = AsyncMock()
        self._stack.enter_context(
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=self.redis,
            )
        )
        self._stack.enter_context(
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.list_versions",
                new=AsyncMock(return_value=self.versions_raw),
            )
        )
        self._stack.enter_context(
            patch(
                "corpmind.modules.analytics.repo.RecommendationOutcomeRepo.aggregate_by_version",
                new=AsyncMock(return_value=self.outcome_map),
            )
        )
        self._stack.enter_context(
            patch(
                "corpmind.modules.analytics.repo.RecommendationQualityScoreRepo.aggregate_by_version",
                new=AsyncMock(return_value=self.quality_map),
            )
        )
        return self

    def __exit__(self, *args: object) -> None:
        self._stack.close()


def _svc() -> RecommendationLearningService:
    return RecommendationLearningService(session=MagicMock())


# ── TestComputeDelta ──────────────────────────────────────────────────────────


class TestComputeDelta:
    def test_positive_delta(self) -> None:
        assert RecommendationLearningService._compute_delta(80.0, 70.0) == pytest.approx(10.0)

    def test_negative_delta(self) -> None:
        assert RecommendationLearningService._compute_delta(60.0, 75.0) == pytest.approx(-15.0)

    def test_zero_delta(self) -> None:
        assert RecommendationLearningService._compute_delta(50.0, 50.0) == pytest.approx(0.0)

    def test_none_current_returns_none(self) -> None:
        assert RecommendationLearningService._compute_delta(None, 50.0) is None

    def test_none_previous_returns_none(self) -> None:
        assert RecommendationLearningService._compute_delta(50.0, None) is None

    def test_both_none_returns_none(self) -> None:
        assert RecommendationLearningService._compute_delta(None, None) is None

    def test_result_is_rounded_to_2dp(self) -> None:
        result = RecommendationLearningService._compute_delta(10.333, 0.0)
        assert result == pytest.approx(10.33)


# ── TestRateHelpers ───────────────────────────────────────────────────────────


class TestRateHelpers:
    def test_adoption_rate_normal(self) -> None:
        assert RecommendationLearningService._adoption_rate(4, 10) == pytest.approx(40.0)

    def test_adoption_rate_zero_generated_returns_none(self) -> None:
        assert RecommendationLearningService._adoption_rate(0, 0) is None

    def test_success_rate_normal(self) -> None:
        assert RecommendationLearningService._success_rate(3, 6) == pytest.approx(50.0)

    def test_success_rate_zero_acted_returns_none(self) -> None:
        assert RecommendationLearningService._success_rate(0, 0) is None

    def test_execution_rate_normal(self) -> None:
        assert RecommendationLearningService._execution_rate(2, 10) == pytest.approx(20.0)

    def test_execution_rate_zero_generated_returns_none(self) -> None:
        assert RecommendationLearningService._execution_rate(0, 0) is None


# ── TestCompareVersions ───────────────────────────────────────────────────────


class TestCompareVersions:
    def test_quality_delta_positive(self) -> None:
        curr = _make_version(DATE_NEW, quality=85.0)
        prev = _make_version(DATE_OLD, quality=75.0)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.quality_delta == pytest.approx(10.0)

    def test_quality_delta_negative(self) -> None:
        curr = _make_version(DATE_NEW, quality=60.0)
        prev = _make_version(DATE_OLD, quality=80.0)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.quality_delta == pytest.approx(-20.0)

    def test_quality_delta_none_when_current_quality_none(self) -> None:
        curr = _make_version(DATE_NEW, quality=None)
        prev = _make_version(DATE_OLD, quality=80.0)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.quality_delta is None

    def test_confidence_delta(self) -> None:
        curr = _make_version(DATE_NEW, avg_conf=75.0)
        prev = _make_version(DATE_OLD, avg_conf=65.0)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.confidence_delta == pytest.approx(10.0)

    def test_adoption_delta(self) -> None:
        curr = _make_version(DATE_NEW, generated=10, acted=6)   # 60%
        prev = _make_version(DATE_OLD, generated=10, acted=4)   # 40%
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.adoption_delta == pytest.approx(20.0)

    def test_success_delta(self) -> None:
        curr = _make_version(DATE_NEW, acted=4, successful=3)   # 75%
        prev = _make_version(DATE_OLD, acted=4, successful=2)   # 50%
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.success_delta == pytest.approx(25.0)

    def test_execution_delta(self) -> None:
        curr = _make_version(DATE_NEW, generated=10, successful=4)   # 40%
        prev = _make_version(DATE_OLD, generated=10, successful=2)   # 20%
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.execution_delta == pytest.approx(20.0)

    def test_returns_learning_comparison_out(self) -> None:
        curr = _make_version(DATE_NEW)
        prev = _make_version(DATE_OLD)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert isinstance(result, LearningComparisonOut)

    def test_adoption_none_when_no_generated(self) -> None:
        curr = _make_version(DATE_NEW, generated=0, acted=0)
        prev = _make_version(DATE_OLD, generated=0, acted=0)
        result = RecommendationLearningService._compare_versions(curr, prev)
        assert result.adoption_delta is None


# ── TestBuildSummary ──────────────────────────────────────────────────────────


class TestBuildSummary:
    def _comparison(self, **kwargs: Any) -> LearningComparisonOut:
        defaults = {
            "quality_delta": None,
            "success_delta": None,
            "confidence_delta": None,
            "adoption_delta": None,
            "execution_delta": None,
        }
        defaults.update(kwargs)
        return LearningComparisonOut(**defaults)

    def test_none_comparison_returns_insufficient_data_line(self) -> None:
        result = RecommendationLearningService._build_summary(None)
        assert "Insufficient data" in result.lines[0]

    def test_quality_improved(self) -> None:
        c = self._comparison(quality_delta=10.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Quality improved" in l for l in result.lines)

    def test_quality_declined(self) -> None:
        c = self._comparison(quality_delta=-8.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Quality declined" in l for l in result.lines)

    def test_quality_unchanged_when_small_delta(self) -> None:
        c = self._comparison(quality_delta=2.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("unchanged" in l for l in result.lines)

    def test_adoption_increased(self) -> None:
        c = self._comparison(adoption_delta=10.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Adoption increased" in l for l in result.lines)

    def test_adoption_decreased(self) -> None:
        c = self._comparison(adoption_delta=-7.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Adoption decreased" in l for l in result.lines)

    def test_success_rate_improved(self) -> None:
        c = self._comparison(success_delta=12.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Success rate improved" in l for l in result.lines)

    def test_success_rate_declined(self) -> None:
        c = self._comparison(success_delta=-9.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Success rate declined" in l for l in result.lines)

    def test_confidence_increased(self) -> None:
        c = self._comparison(confidence_delta=5.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Confidence increased" in l for l in result.lines)

    def test_confidence_decreased(self) -> None:
        c = self._comparison(confidence_delta=-4.0)
        result = RecommendationLearningService._build_summary(c)
        assert any("Confidence decreased" in l for l in result.lines)

    def test_all_none_deltas_returns_stable_message(self) -> None:
        c = self._comparison()
        result = RecommendationLearningService._build_summary(c)
        assert any("stable" in l.lower() for l in result.lines)

    def test_returns_learning_summary_out(self) -> None:
        c = self._comparison(quality_delta=5.0)
        result = RecommendationLearningService._build_summary(c)
        assert isinstance(result, LearningSummaryOut)

    def test_multiple_lines_emitted_when_multiple_signals(self) -> None:
        c = self._comparison(quality_delta=10.0, adoption_delta=6.0)
        result = RecommendationLearningService._build_summary(c)
        assert len(result.lines) >= 2


# ── TestGetLearningCacheHit ───────────────────────────────────────────────────


class TestGetLearningCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_response_without_db(self) -> None:
        expected = LearningOut(
            generated_at=datetime.now(timezone.utc),
            current_version="2026-06-20",
            previous_version="2026-06-13",
            comparison=None,
            summary=LearningSummaryOut(lines=["Quality unchanged."]),
            insufficient_data=False,
        )
        with _PatchSet(redis_cached=expected.model_dump_json()):
            result = await _svc().get_learning(WS)
        assert result.current_version == "2026-06-20"

    @pytest.mark.asyncio
    async def test_cache_miss_calls_repos(self) -> None:
        versions_raw = [
            (DATE_NEW, 5, 70.0),
            (DATE_OLD, 5, 65.0),
        ]
        outcome_map = {DATE_NEW: (3, 2), DATE_OLD: (2, 1)}
        quality_map = {DATE_NEW: 80.0, DATE_OLD: 72.0}
        with _PatchSet(
            versions_raw=versions_raw,
            outcome_map=outcome_map,
            quality_map=quality_map,
        ):
            result = await _svc().get_learning(WS)
        assert result.current_version == DATE_NEW.isoformat()

    @pytest.mark.asyncio
    async def test_redis_failure_gracefully_falls_back(self) -> None:
        versions_raw = [(DATE_NEW, 3, 60.0), (DATE_OLD, 3, 55.0)]
        with _PatchSet(versions_raw=versions_raw, redis_raises=True):
            result = await _svc().get_learning(WS)
        assert isinstance(result, LearningOut)


# ── TestGetLearningInsufficientData ──────────────────────────────────────────


class TestGetLearningInsufficientData:
    @pytest.mark.asyncio
    async def test_zero_versions_returns_insufficient(self) -> None:
        with _PatchSet():
            result = await _svc().get_learning(WS)
        assert result.insufficient_data is True
        assert result.current_version is None
        assert result.comparison is None

    @pytest.mark.asyncio
    async def test_one_version_returns_insufficient(self) -> None:
        with _PatchSet(versions_raw=[(DATE_NEW, 5, 70.0)]):
            result = await _svc().get_learning(WS)
        assert result.insufficient_data is True
        assert result.previous_version is None

    @pytest.mark.asyncio
    async def test_two_versions_not_insufficient(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_learning(WS)
        assert result.insufficient_data is False


# ── TestGetLearningHappyPath ──────────────────────────────────────────────────


class TestGetLearningHappyPath:
    @pytest.mark.asyncio
    async def test_current_and_previous_version_set(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        outcome_map = {DATE_NEW: (4, 3), DATE_OLD: (2, 1)}
        quality_map = {DATE_NEW: 85.0, DATE_OLD: 75.0}
        with _PatchSet(versions_raw=versions_raw, outcome_map=outcome_map, quality_map=quality_map):
            result = await _svc().get_learning(WS)
        assert result.current_version == DATE_NEW.isoformat()
        assert result.previous_version == DATE_OLD.isoformat()

    @pytest.mark.asyncio
    async def test_comparison_is_set_when_two_versions(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_learning(WS)
        assert result.comparison is not None

    @pytest.mark.asyncio
    async def test_summary_lines_non_empty(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        quality_map = {DATE_NEW: 80.0, DATE_OLD: 70.0}
        with _PatchSet(versions_raw=versions_raw, quality_map=quality_map):
            result = await _svc().get_learning(WS)
        assert len(result.summary.lines) > 0

    @pytest.mark.asyncio
    async def test_result_is_learning_out(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_learning(WS)
        assert isinstance(result, LearningOut)

    @pytest.mark.asyncio
    async def test_cache_is_set_on_miss(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(WS)
        ps.redis.set.assert_called_once()


# ── TestVersionHistory ────────────────────────────────────────────────────────


class TestVersionHistory:
    @pytest.mark.asyncio
    async def test_empty_versions_returns_insufficient(self) -> None:
        with _PatchSet():
            result = await _svc().get_version_history(WS)
        assert result.insufficient_data is True
        assert result.total_versions == 0

    @pytest.mark.asyncio
    async def test_one_version_insufficient(self) -> None:
        with _PatchSet(versions_raw=[(DATE_NEW, 5, 70.0)]):
            result = await _svc().get_version_history(WS)
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_two_versions_not_insufficient(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert result.insufficient_data is False

    @pytest.mark.asyncio
    async def test_versions_newest_first(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0), (DATE_OLDER, 5, 60.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        dates = [v.version for v in result.versions]
        assert dates == sorted(dates, reverse=True)

    @pytest.mark.asyncio
    async def test_total_versions_count(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0), (DATE_OLDER, 5, 60.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert result.total_versions == 3

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        expected = VersionHistoryOut(
            versions=[],
            total_versions=0,
            insufficient_data=True,
        )
        with _PatchSet(redis_cached=expected.model_dump_json()):
            result = await _svc().get_version_history(WS)
        assert result.total_versions == 0

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw, redis_raises=True):
            result = await _svc().get_version_history(WS)
        assert isinstance(result, VersionHistoryOut)

    @pytest.mark.asyncio
    async def test_returns_version_history_out(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert isinstance(result, VersionHistoryOut)

    @pytest.mark.asyncio
    async def test_acted_count_populated_from_outcome_map(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        outcome_map = {DATE_NEW: (4, 3), DATE_OLD: (1, 0)}
        with _PatchSet(versions_raw=versions_raw, outcome_map=outcome_map):
            result = await _svc().get_version_history(WS)
        new_v = next(v for v in result.versions if v.version == DATE_NEW.isoformat())
        assert new_v.acted == 4
        assert new_v.successful == 3


# ── TestQualityWindowFallback ─────────────────────────────────────────────────


class TestQualityWindowFallback:
    @pytest.mark.asyncio
    async def test_uses_quality_from_same_date(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        quality_map = {DATE_NEW: 85.0}
        with _PatchSet(versions_raw=versions_raw, quality_map=quality_map):
            result = await _svc().get_version_history(WS)
        new_v = next(v for v in result.versions if v.version == DATE_NEW.isoformat())
        assert new_v.quality_score == pytest.approx(85.0)

    @pytest.mark.asyncio
    async def test_falls_back_to_quality_within_7_days(self) -> None:
        # DATE_NEW is 2026-06-20; quality score on 2026-06-18 (2 days prior)
        date_2_days_prior = date(2026, 6, 18)
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        quality_map = {date_2_days_prior: 78.0}
        with _PatchSet(versions_raw=versions_raw, quality_map=quality_map):
            result = await _svc().get_version_history(WS)
        new_v = next(v for v in result.versions if v.version == DATE_NEW.isoformat())
        assert new_v.quality_score == pytest.approx(78.0)

    @pytest.mark.asyncio
    async def test_quality_none_when_no_score_in_window(self) -> None:
        # Quality only available 30 days before — outside the 7-day window
        date_far_prior = date(2026, 5, 10)
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        quality_map = {date_far_prior: 60.0}
        with _PatchSet(versions_raw=versions_raw, quality_map=quality_map):
            result = await _svc().get_version_history(WS)
        new_v = next(v for v in result.versions if v.version == DATE_NEW.isoformat())
        assert new_v.quality_score is None


# ── TestVersionFields ─────────────────────────────────────────────────────────


class TestVersionFields:
    @pytest.mark.asyncio
    async def test_version_string_is_iso_date(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert result.versions[0].version == "2026-06-20"

    @pytest.mark.asyncio
    async def test_first_seen_equals_last_seen_equals_snapshot_date(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        v = result.versions[0]
        assert v.first_seen == v.last_seen == DATE_NEW

    @pytest.mark.asyncio
    async def test_avg_confidence_rounded(self) -> None:
        versions_raw = [(DATE_NEW, 5, 73.3333), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert result.versions[0].avg_confidence == pytest.approx(73.33, abs=0.01)

    @pytest.mark.asyncio
    async def test_recommendations_generated_correct(self) -> None:
        versions_raw = [(DATE_NEW, 7, 70.0), (DATE_OLD, 3, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        new_v = next(v for v in result.versions if v.version == DATE_NEW.isoformat())
        assert new_v.recommendations_generated == 7


# ── TestTenantIsolation ───────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_cache_key_scoped_to_tenant_and_workspace(self) -> None:
        ws_a = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(ws_a)
        key_used = ps.redis.set.call_args[0][0]
        assert str(ORG) in key_used
        assert str(ws_a) in key_used

    @pytest.mark.asyncio
    async def test_version_history_cache_key_scoped(self) -> None:
        ws_b = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_version_history(ws_b)
        key_used = ps.redis.set.call_args[0][0]
        assert str(ORG) in key_used
        assert str(ws_b) in key_used

    @pytest.mark.asyncio
    async def test_two_workspaces_use_different_keys(self) -> None:
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        keys: list[str] = []
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(ws_a)
            keys.append(ps.redis.set.call_args[0][0])
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(ws_b)
            keys.append(ps.redis.set.call_args[0][0])
        assert keys[0] != keys[1]


# ── TestSchemaValidation ──────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_learning_out_serialises_to_json(self) -> None:
        out = LearningOut(
            generated_at=datetime.now(timezone.utc),
            current_version="2026-06-20",
            previous_version="2026-06-13",
            comparison=LearningComparisonOut(
                quality_delta=5.0,
                success_delta=None,
                confidence_delta=2.0,
                adoption_delta=10.0,
                execution_delta=-3.0,
            ),
            summary=LearningSummaryOut(lines=["Quality improved by 5 points."]),
            insufficient_data=False,
        )
        raw = json.loads(out.model_dump_json())
        assert raw["current_version"] == "2026-06-20"
        assert raw["comparison"]["quality_delta"] == pytest.approx(5.0)

    def test_version_history_out_serialises(self) -> None:
        out = VersionHistoryOut(
            versions=[_make_version(DATE_NEW)],
            total_versions=1,
            insufficient_data=True,
        )
        raw = json.loads(out.model_dump_json())
        assert raw["total_versions"] == 1

    def test_learning_version_out_fields(self) -> None:
        v = _make_version(DATE_NEW, generated=8, acted=5, successful=3, quality=77.5)
        assert v.recommendations_generated == 8
        assert v.acted == 5
        assert v.successful == 3
        assert v.quality_score == pytest.approx(77.5)

    def test_insufficient_data_false_with_two_versions(self) -> None:
        out = VersionHistoryOut(
            versions=[_make_version(DATE_NEW), _make_version(DATE_OLD)],
            total_versions=2,
            insufficient_data=False,
        )
        assert out.insufficient_data is False

    @pytest.mark.asyncio
    async def test_learning_out_roundtrip_via_model_validate_json(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            result = await _svc().get_learning(WS)
        serialised = result.model_dump_json()
        recovered = LearningOut.model_validate_json(serialised)
        assert recovered.current_version == result.current_version


# ── TestCacheKeys ─────────────────────────────────────────────────────────────


class TestCacheKeys:
    @pytest.mark.asyncio
    async def test_learning_cache_key_format(self) -> None:
        ws = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(ws)
        key = ps.redis.set.call_args[0][0]
        assert key == f"t:{ORG}:{ws}:analytics:learning"

    @pytest.mark.asyncio
    async def test_version_history_cache_key_format(self) -> None:
        ws = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_version_history(ws)
        key = ps.redis.set.call_args[0][0]
        assert key == f"t:{ORG}:{ws}:analytics:version_history"

    @pytest.mark.asyncio
    async def test_learning_ttl_is_3600(self) -> None:
        ws = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_learning(ws)
        _, kwargs = ps.redis.set.call_args
        assert kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_version_history_ttl_is_3600(self) -> None:
        ws = uuid.uuid4()
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw) as ps:
            await _svc().get_version_history(ws)
        _, kwargs = ps.redis.set.call_args
        assert kwargs.get("ex") == 3600


# ── TestReadOnlyContract ──────────────────────────────────────────────────────


class TestReadOnlyContract:
    @pytest.mark.asyncio
    async def test_get_learning_does_not_call_upsert_snapshot(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            with patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.upsert_snapshot"
            ) as mock_upsert:
                await _svc().get_learning(WS)
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_version_history_does_not_call_upsert_outcome(self) -> None:
        versions_raw = [(DATE_NEW, 5, 70.0), (DATE_OLD, 5, 65.0)]
        with _PatchSet(versions_raw=versions_raw):
            with patch(
                "corpmind.modules.analytics.repo.RecommendationOutcomeRepo.upsert_outcome"
            ) as mock_upsert:
                await _svc().get_version_history(WS)
        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_has_no_create_or_update_methods(self) -> None:
        svc = _svc()
        public_methods = [
            m for m in dir(svc)
            if not m.startswith("_") and callable(getattr(svc, m))
        ]
        mutation_methods = [
            m for m in public_methods
            if any(kw in m for kw in ("create", "update", "delete", "upsert", "write"))
        ]
        assert mutation_methods == []


# ── TestOrderingAggregation ───────────────────────────────────────────────────


class TestOrderingAggregation:
    @pytest.mark.asyncio
    async def test_three_versions_ordered_newest_first(self) -> None:
        versions_raw = [
            (DATE_NEW, 5, 72.0),
            (DATE_OLD, 4, 68.0),
            (DATE_OLDER, 3, 60.0),
        ]
        with _PatchSet(versions_raw=versions_raw):
            result = await _svc().get_version_history(WS)
        assert result.versions[0].version == DATE_NEW.isoformat()
        assert result.versions[1].version == DATE_OLD.isoformat()
        assert result.versions[2].version == DATE_OLDER.isoformat()

    @pytest.mark.asyncio
    async def test_only_first_two_versions_used_for_comparison(self) -> None:
        versions_raw = [
            (DATE_NEW, 5, 80.0),
            (DATE_OLD, 5, 70.0),
            (DATE_OLDER, 5, 60.0),
        ]
        quality_map = {DATE_NEW: 85.0, DATE_OLD: 75.0, DATE_OLDER: 65.0}
        with _PatchSet(versions_raw=versions_raw, quality_map=quality_map):
            result = await _svc().get_learning(WS)
        assert result.current_version == DATE_NEW.isoformat()
        assert result.previous_version == DATE_OLD.isoformat()
