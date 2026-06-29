"""Unit tests for RecommendationPortfolioService (Sprint 24B).

Covers:
  _shannon_entropy        (6 tests)
  _normalize_entropy      (5 tests)
  _balance_rating         (6 tests)
  get_portfolio()         (12 tests — insufficient, distribution, entropy, cache)
  get_coverage()          (12 tests — all present, missing, stale, cache)
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.service import (
    RecommendationPortfolioService,
    _KNOWN_REC_TYPES,
    _PORTFOLIO_STALE_DAYS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _snap_repo_mock(type_counts: list[tuple[str, int]]) -> AsyncMock:
    m = AsyncMock()
    m.list_type_counts.return_value = type_counts
    m.find_latest_snapshot_date_per_type.return_value = {}
    return m


def _outcome_repo_mock(outcome_map: dict[str, tuple[int, int, int]]) -> AsyncMock:
    m = AsyncMock()
    m.aggregate_by_type_for_period.return_value = outcome_map
    return m


def _ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or uuid.uuid4()
    return ctx


WS = uuid.uuid4()


# ── _shannon_entropy ──────────────────────────────────────────────────────────


class TestShannonEntropy:
    svc = RecommendationPortfolioService

    def test_empty_list_returns_zero(self):
        assert self.svc._shannon_entropy([]) == 0.0

    def test_single_type_returns_zero(self):
        assert self.svc._shannon_entropy([100]) == 0.0

    def test_equal_distribution_two_types(self):
        H = self.svc._shannon_entropy([50, 50])
        assert abs(H - math.log(2)) < 1e-9

    def test_equal_distribution_five_types(self):
        H = self.svc._shannon_entropy([20, 20, 20, 20, 20])
        assert abs(H - math.log(5)) < 1e-9

    def test_skewed_distribution_lower_than_equal(self):
        H_equal = self.svc._shannon_entropy([20, 20, 20, 20, 20])
        H_skewed = self.svc._shannon_entropy([80, 5, 5, 5, 5])
        assert H_skewed < H_equal

    def test_zero_count_entries_excluded(self):
        # [50, 50, 0] should equal [50, 50]
        H_with_zero = self.svc._shannon_entropy([50, 50, 0])
        H_without = self.svc._shannon_entropy([50, 50])
        assert abs(H_with_zero - H_without) < 1e-9


# ── _normalize_entropy ────────────────────────────────────────────────────────


class TestNormalizeEntropy:
    svc = RecommendationPortfolioService

    def test_single_type_returns_zero(self):
        assert self.svc._normalize_entropy(0.0, 1) == 0.0

    def test_zero_types_returns_zero(self):
        assert self.svc._normalize_entropy(0.0, 0) == 0.0

    def test_equal_distribution_returns_100(self):
        H_max = math.log(5)
        result = self.svc._normalize_entropy(H_max, 5)
        assert abs(result - 100.0) < 1e-6

    def test_zero_entropy_returns_zero(self):
        assert self.svc._normalize_entropy(0.0, 5) == 0.0

    def test_half_entropy_returns_50(self):
        H_max = math.log(4)
        result = self.svc._normalize_entropy(H_max / 2, 4)
        assert abs(result - 50.0) < 1e-6


# ── _balance_rating ───────────────────────────────────────────────────────────


class TestBalanceRating:
    svc = RecommendationPortfolioService

    def test_100_is_excellent(self):
        assert self.svc._balance_rating(100.0) == "excellent"

    def test_80_is_excellent(self):
        assert self.svc._balance_rating(80.0) == "excellent"

    def test_79_is_good(self):
        assert self.svc._balance_rating(79.9) == "good"

    def test_60_is_good(self):
        assert self.svc._balance_rating(60.0) == "good"

    def test_59_is_moderate(self):
        assert self.svc._balance_rating(59.9) == "moderate"

    def test_39_is_poor(self):
        assert self.svc._balance_rating(39.9) == "poor"


# ── get_portfolio ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetPortfolio:
    async def _call(
        self,
        type_counts: list[tuple[str, int]],
        outcome_map: dict[str, tuple[int, int, int]] | None = None,
        redis_miss: bool = True,
    ):
        session = MagicMock()
        svc = RecommendationPortfolioService(session)

        redis_mock = AsyncMock()
        redis_mock.get.return_value = None if redis_miss else None
        redis_mock.set = AsyncMock()

        snap_repo = _snap_repo_mock(type_counts)
        outcome_repo = _outcome_repo_mock(outcome_map or {})

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationOutcomeRepo",
                return_value=outcome_repo,
            ),
        ):
            return await svc.get_portfolio(workspace_id=WS, period_days=90)

    async def test_insufficient_data_when_no_snapshots(self):
        out = await self._call([])
        assert out.insufficient_data is True
        assert out.total_recommendations == 0
        assert out.dominant_type is None
        assert out.least_used_type is None

    async def test_insufficient_data_balance_rating_is_poor(self):
        out = await self._call([])
        assert out.portfolio_balance.balance_rating == "poor"

    async def test_total_recommendations_is_sum_of_counts(self):
        out = await self._call([("topic", 30), ("channel", 20)])
        assert out.total_recommendations == 50

    async def test_dominant_type_is_highest_count(self):
        out = await self._call([("topic", 40), ("channel", 10)])
        assert out.dominant_type == "topic"

    async def test_least_used_type_is_lowest_count(self):
        out = await self._call([("topic", 40), ("channel", 10)])
        assert out.least_used_type == "channel"

    async def test_percentage_sums_to_100(self):
        out = await self._call([("topic", 25), ("channel", 25), ("industry", 50)])
        total_pct = sum(i.percentage for i in out.recommendation_types)
        assert abs(total_pct - 100.0) < 0.1

    async def test_acted_rate_computed_from_outcomes(self):
        # topic: 10 total outcomes, 7 acted → 70%
        out = await self._call(
            [("topic", 10)],
            outcome_map={"topic": (10, 7, 3)},
        )
        assert out.recommendation_types[0].acted_rate == 70.0

    async def test_success_rate_computed_from_outcomes(self):
        # topic: 10 total outcomes, 3 success → 30%
        out = await self._call(
            [("topic", 10)],
            outcome_map={"topic": (10, 7, 3)},
        )
        assert out.recommendation_types[0].success_rate == 30.0

    async def test_acted_rate_zero_when_no_outcomes(self):
        out = await self._call([("topic", 10)], outcome_map={})
        assert out.recommendation_types[0].acted_rate == 0.0

    async def test_equal_distribution_gives_excellent_rating(self):
        # 5 types with equal counts → H/H_max = 1.0 → 100 → excellent
        counts = [("campaign", 20), ("channel", 20), ("industry", 20), ("pricing", 20), ("topic", 20)]
        out = await self._call(counts)
        assert out.portfolio_balance.balance_rating == "excellent"
        assert abs(out.portfolio_balance.diversity_index - 100.0) < 1e-6

    async def test_cache_hit_returns_early(self):
        import json
        from corpmind.modules.analytics.schemas import PortfolioOut, PortfolioBalanceOut

        cached = PortfolioOut(
            generated_at=datetime.now(UTC),
            total_recommendations=5,
            recommendation_types=[],
            dominant_type="topic",
            least_used_type="pricing",
            portfolio_balance=PortfolioBalanceOut(
                diversity_index=75.0,
                balance_rating="good",
            ),
        )
        session = MagicMock()
        svc = RecommendationPortfolioService(session)
        redis_mock = AsyncMock()
        redis_mock.get.return_value = cached.model_dump_json()

        snap_repo = _snap_repo_mock([])
        outcome_repo = _outcome_repo_mock({})

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationOutcomeRepo",
                return_value=outcome_repo,
            ),
        ):
            out = await svc.get_portfolio(workspace_id=WS)

        snap_repo.list_type_counts.assert_not_called()
        assert out.dominant_type == "topic"

    async def test_cache_miss_stores_result(self):
        session = MagicMock()
        svc = RecommendationPortfolioService(session)
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None

        snap_repo = _snap_repo_mock([("topic", 10)])
        outcome_repo = _outcome_repo_mock({})

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationOutcomeRepo",
                return_value=outcome_repo,
            ),
        ):
            await svc.get_portfolio(workspace_id=WS)

        redis_mock.set.assert_awaited_once()
        _, kwargs = redis_mock.set.call_args
        assert kwargs.get("ex") == 3600 or redis_mock.set.call_args[0][2] == 3600


# ── get_coverage ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetCoverage:
    async def _call(
        self,
        period_counts: list[tuple[str, int]],
        latest_dates: dict[str, date],
        redis_miss: bool = True,
    ):
        session = MagicMock()
        svc = RecommendationPortfolioService(session)

        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.set = AsyncMock()

        snap_repo = AsyncMock()
        snap_repo.list_type_counts.return_value = period_counts
        snap_repo.find_latest_snapshot_date_per_type.return_value = latest_dates

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
        ):
            return await svc.get_coverage(workspace_id=WS, period_days=90)

    async def test_all_known_types_in_coverage(self):
        out = await self._call([], {})
        types = {c.recommendation_type for c in out.coverage}
        assert types == set(_KNOWN_REC_TYPES)

    async def test_coverage_sorted_alphabetically(self):
        out = await self._call([], {})
        names = [c.recommendation_type for c in out.coverage]
        assert names == sorted(names)

    async def test_missing_type_when_no_snapshot(self):
        out = await self._call([], {})
        assert set(out.missing_types) == set(_KNOWN_REC_TYPES)

    async def test_present_type_not_in_missing(self):
        today = date.today()
        out = await self._call(
            [("topic", 5)],
            {"topic": today},
        )
        assert "topic" not in out.missing_types

    async def test_stale_type_when_days_exceed_threshold(self):
        stale_date = date.today() - timedelta(days=_PORTFOLIO_STALE_DAYS + 1)
        out = await self._call(
            [("topic", 3)],
            {"topic": stale_date},
        )
        assert "topic" in out.stale_types

    async def test_healthy_type_not_stale(self):
        fresh_date = date.today() - timedelta(days=_PORTFOLIO_STALE_DAYS - 1)
        out = await self._call(
            [("topic", 3)],
            {"topic": fresh_date},
        )
        assert "topic" not in out.stale_types

    async def test_boundary_at_stale_threshold(self):
        # Exactly 30 days → NOT stale (> 30, not >= 30)
        boundary_date = date.today() - timedelta(days=_PORTFOLIO_STALE_DAYS)
        out = await self._call([("topic", 1)], {"topic": boundary_date})
        assert "topic" not in out.stale_types

    async def test_days_since_computed_correctly(self):
        days_ago = 15
        target_date = date.today() - timedelta(days=days_ago)
        out = await self._call([("topic", 2)], {"topic": target_date})
        topic_row = next(c for c in out.coverage if c.recommendation_type == "topic")
        assert topic_row.days_since_last_generated == days_ago

    async def test_period_count_in_row(self):
        today = date.today()
        out = await self._call([("topic", 7)], {"topic": today})
        topic_row = next(c for c in out.coverage if c.recommendation_type == "topic")
        assert topic_row.count == 7

    async def test_missing_type_has_none_last_generated(self):
        out = await self._call([], {})
        campaign_row = next(c for c in out.coverage if c.recommendation_type == "campaign")
        assert campaign_row.last_generated_at is None
        assert campaign_row.days_since_last_generated is None
        assert campaign_row.present is False

    async def test_cache_hit_returns_early(self):
        from corpmind.modules.analytics.schemas import CoverageOut

        cached = CoverageOut(
            generated_at=datetime.now(UTC),
            coverage=[],
            missing_types=["topic"],
            stale_types=[],
        )
        session = MagicMock()
        svc = RecommendationPortfolioService(session)
        redis_mock = AsyncMock()
        redis_mock.get.return_value = cached.model_dump_json()

        snap_repo = AsyncMock()

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
        ):
            out = await svc.get_coverage(workspace_id=WS)

        snap_repo.list_type_counts.assert_not_called()
        assert out.missing_types == ["topic"]

    async def test_cache_miss_stores_result_with_1h_ttl(self):
        session = MagicMock()
        svc = RecommendationPortfolioService(session)
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None

        snap_repo = AsyncMock()
        snap_repo.list_type_counts.return_value = []
        snap_repo.find_latest_snapshot_date_per_type.return_value = {}

        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_ctx(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.service.RecommendationSnapshotRepo",
                return_value=snap_repo,
            ),
        ):
            await svc.get_coverage(workspace_id=WS)

        redis_mock.set.assert_awaited_once()
        call_args = redis_mock.set.call_args
        ex_value = call_args[1].get("ex") if call_args[1] else call_args[0][2]
        assert ex_value == 3600
