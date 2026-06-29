"""Unit tests for RecommendationAnalyticsService (Sprint 22A).

Covers:
  get_effectiveness()
    - empty quality scores → zero summary, empty by_type, empty trend
    - one type with full data → correct by_type row, correct summary totals
    - multiple types → summary aggregates across all, by_type per type
    - quality_trend includes all rows in period ordered by date asc
    - only latest row per type used in by_type (when multiple dates exist)
    - Redis cache hit → returns cached value without DB query
    - Redis cache miss → computes and stores in Redis
    - Redis unavailable → falls back to live query gracefully
    - adoption_rate = 0.0 when generated == 0 (no ZeroDivisionError)
    - success_rate = 0.0 when acted == 0 (no ZeroDivisionError)
    - low_confidence type → quality_score=None in by_type item
    - TenantContext.org_id scopes repo query (tenant isolation)

  get_calibration()
    - no snapshots → empty recommendation_types, insufficient_data=True
    - no outcomes → all observed_success_rate=None, insufficient_data=True
    - acted < 5 → insufficient_data=True
    - acted >= 5 → insufficient_data=False
    - correct predicted_confidence = avg confidence_score
    - correct observed_success_rate = success/acted * 100
    - calibration_delta sign: negative when overconfident (obs < pred)
    - calibration_delta sign: positive when underconfident (obs > pred)
    - calibration_delta = None when no acted outcomes for the type
    - overall.high_confidence_success_rate computed from 'high' band
    - overall.medium_confidence_success_rate computed from 'medium' band
    - overall.low_confidence_success_rate computed from 'low' band
    - overall rates = None when no acted in that band
    - Redis cache hit returns cached value
    - Redis unavailable falls back gracefully
    - TenantContext.org_id scopes queries

  Schema contracts
    - RecEffectivenessOut has summary, by_type, quality_trend fields
    - RecEffectivenessSummaryOut adoption_rate/success_rate are 0.0–1.0
    - RecCalibrationOut has generated_at, overall, recommendation_types
    - RecCalibrationOut.minimum_acted_recommendations == 5
    - RecCalibrationTypeItemOut fields present

  Calibration delta formula (pure arithmetic)
    - overconfident: obs=65, pred=80 → delta=-15.0
    - underconfident: obs=90, pred=70 → delta=+20.0
    - perfect calibration: obs=75, pred=75 → delta=0.0
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import RecommendationQualityScore
from corpmind.modules.analytics.schemas import (
    RecCalibrationOut,
    RecCalibrationOverallOut,
    RecCalibrationTypeItemOut,
    RecEffectivenessOut,
    RecEffectivenessSummaryOut,
    RecEffectivenessTypeItemOut,
    QualityTrendPointOut,
)
from corpmind.modules.analytics.service import RecommendationAnalyticsService

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
TODAY = date(2026, 6, 23)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _score_row(
    *,
    rec_type: str = "industry",
    score_date: date = TODAY,
    shown_count: int = 10,
    acted_count: int = 4,
    success_count: int = 2,
    ignored_count: int = 6,
    feedback_helpful: int = 3,
    feedback_not_helpful: int = 1,
    feedback_dismissed: int = 0,
    adoption_rate: Decimal = Decimal("0.4"),
    success_rate: Decimal = Decimal("0.5"),
    quality_score: int | None = 75,
    low_confidence: bool = False,
) -> RecommendationQualityScore:
    row = MagicMock(spec=RecommendationQualityScore)
    row.rec_type = rec_type
    row.score_date = score_date
    row.shown_count = shown_count
    row.acted_count = acted_count
    row.success_count = success_count
    row.ignored_count = ignored_count
    row.feedback_helpful = feedback_helpful
    row.feedback_not_helpful = feedback_not_helpful
    row.feedback_dismissed = feedback_dismissed
    row.adoption_rate = adoption_rate
    row.success_rate = success_rate
    row.quality_score = quality_score
    row.low_confidence = low_confidence
    return row


def _make_svc() -> RecommendationAnalyticsService:
    return RecommendationAnalyticsService(AsyncMock())


# ── get_effectiveness ─────────────────────────────────────────────────────────


class TestGetEffectivenessEmpty:
    @pytest.mark.asyncio
    async def test_empty_quality_scores_zero_summary(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert isinstance(result, RecEffectivenessOut)
        assert result.summary.recommendations_generated == 0
        assert result.summary.recommendations_acted == 0
        assert result.summary.recommendations_successful == 0
        assert result.summary.adoption_rate == 0.0
        assert result.summary.success_rate == 0.0
        assert result.by_type == []
        assert result.quality_trend == []

    @pytest.mark.asyncio
    async def test_no_division_error_when_generated_zero(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            row = _score_row(shown_count=0, acted_count=0, success_count=0)
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[row])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.summary.adoption_rate == 0.0
        assert result.summary.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_no_division_error_when_acted_zero(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            row = _score_row(shown_count=5, acted_count=0, success_count=0)
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[row])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.summary.success_rate == 0.0


class TestGetEffectivenessData:
    @pytest.mark.asyncio
    async def test_one_type_by_type_row_fields(self):
        svc = _make_svc()
        row = _score_row(
            rec_type="channel",
            shown_count=20,
            acted_count=8,
            success_count=5,
            adoption_rate=Decimal("0.4"),
            success_rate=Decimal("0.625"),
            quality_score=80,
        )
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[row])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert len(result.by_type) == 1
        item = result.by_type[0]
        assert isinstance(item, RecEffectivenessTypeItemOut)
        assert item.recommendation_type == "channel"
        assert item.generated == 20
        assert item.acted == 8
        assert item.successful == 5
        assert item.adoption_rate == pytest.approx(0.4)
        assert item.success_rate == pytest.approx(0.625)
        assert item.quality_score == 80

    @pytest.mark.asyncio
    async def test_summary_aggregates_across_types(self):
        svc = _make_svc()
        row1 = _score_row(rec_type="industry", shown_count=10, acted_count=3, success_count=2)
        row2 = _score_row(rec_type="topic", shown_count=15, acted_count=5, success_count=3)
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[row1, row2])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.summary.recommendations_generated == 25
        assert result.summary.recommendations_acted == 8
        assert result.summary.recommendations_successful == 5
        assert result.summary.adoption_rate == pytest.approx(8 / 25, rel=1e-3)
        assert result.summary.success_rate == pytest.approx(5 / 8, rel=1e-3)

    @pytest.mark.asyncio
    async def test_low_confidence_type_quality_score_none(self):
        svc = _make_svc()
        row = _score_row(quality_score=None, low_confidence=True)
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[row])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert result.by_type[0].quality_score is None

    @pytest.mark.asyncio
    async def test_quality_trend_ordered_by_date_asc(self):
        svc = _make_svc()
        row1 = _score_row(rec_type="industry", score_date=date(2026, 6, 20))
        row2 = _score_row(rec_type="industry", score_date=date(2026, 6, 22))
        row3 = _score_row(rec_type="industry", score_date=date(2026, 6, 21))
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(
                return_value=[row1, row2, row3]
            )

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        dates = [p.score_date for p in result.quality_trend]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_quality_trend_includes_all_rows(self):
        svc = _make_svc()
        rows = [
            _score_row(rec_type="industry", score_date=date(2026, 6, d))
            for d in [20, 21, 22]
        ]
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=rows)

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert len(result.quality_trend) == 3

    @pytest.mark.asyncio
    async def test_by_type_uses_latest_row_per_type(self):
        svc = _make_svc()
        older = _score_row(rec_type="industry", score_date=date(2026, 6, 1), quality_score=60)
        newer = _score_row(rec_type="industry", score_date=date(2026, 6, 22), quality_score=80)
        # list_by_workspace returns desc order; newer first
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[newer, older])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert len(result.by_type) == 1
        assert result.by_type[0].quality_score == 80


class TestGetEffectivenessCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db_query(self):
        svc = _make_svc()
        cached_payload = RecEffectivenessOut(
            generated_at=datetime.now(UTC),
            summary=RecEffectivenessSummaryOut(
                recommendations_generated=5,
                recommendations_acted=2,
                recommendations_successful=1,
                adoption_rate=0.4,
                success_rate=0.5,
            ),
            by_type=[],
            quality_trend=[],
        ).model_dump_json()

        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=cached_payload)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        MockRepo.assert_not_called()
        assert result.summary.recommendations_generated == 5

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[])

            await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        mock_redis.return_value.set.assert_called_once()
        args = mock_redis.return_value.set.call_args
        assert args.kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_gracefully(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(side_effect=ConnectionError("redis down"))
            mock_redis.return_value.set = AsyncMock(side_effect=ConnectionError("redis down"))
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[])

            result = await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        assert isinstance(result, RecEffectivenessOut)

    @pytest.mark.asyncio
    async def test_effectiveness_scoped_to_tenant_context(self):
        svc = _make_svc()
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
            patch(
                "corpmind.modules.analytics.service.RecommendationQualityScoreRepo"
            ) as MockRepo,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            MockRepo.return_value.list_by_workspace = AsyncMock(return_value=[])

            await svc.get_effectiveness(workspace_id=WORKSPACE_ID)

        # Cache key includes tenant_id so keys don't bleed across tenants
        set_call = mock_redis.return_value.set.call_args
        cache_key = set_call.args[0]
        assert str(TENANT_ID) in cache_key


# ── get_calibration ───────────────────────────────────────────────────────────


def _mock_text_result(rows: list[tuple]) -> MagicMock:
    """Return a mock that simulates session.execute(...).all()."""
    result = MagicMock()
    result.all.return_value = rows
    return result


class TestGetCalibrationEmpty:
    @pytest.mark.asyncio
    async def test_no_snapshots_empty_types(self):
        svc = _make_svc()
        svc._session.execute = AsyncMock(return_value=_mock_text_result([]))
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        assert result.recommendation_types == []
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_no_outcomes_all_observed_none(self):
        svc = _make_svc()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # predicted: has snapshots
                return _mock_text_result([("industry", 75.0)])
            else:
                # observed / band: no outcomes
                return _mock_text_result([])

        svc._session.execute = side_effect
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        assert result.insufficient_data is True
        assert len(result.recommendation_types) == 1
        item = result.recommendation_types[0]
        assert item.observed_success_rate is None
        assert item.calibration_delta is None

    @pytest.mark.asyncio
    async def test_acted_below_threshold_insufficient_data_true(self):
        svc = _make_svc()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_text_result([("industry", 70.0)])
            elif call_count == 2:
                # only 4 acted — below threshold of 5
                return _mock_text_result([("industry", 4, 2)])
            else:
                return _mock_text_result([])

        svc._session.execute = side_effect
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_acted_at_threshold_insufficient_data_false(self):
        svc = _make_svc()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_text_result([("industry", 70.0)])
            elif call_count == 2:
                return _mock_text_result([("industry", 5, 3)])  # exactly 5 acted
            else:
                return _mock_text_result([])

        svc._session.execute = side_effect
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        assert result.insufficient_data is False


class TestGetCalibrationCalculations:
    async def _run(
        self, pred_rows: list, obs_rows: list, band_rows: list
    ) -> RecCalibrationOut:
        svc = _make_svc()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_text_result(pred_rows)
            elif call_count == 2:
                return _mock_text_result(obs_rows)
            else:
                return _mock_text_result(band_rows)

        svc._session.execute = side_effect
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()
            return await svc.get_calibration(workspace_id=WORKSPACE_ID)

    @pytest.mark.asyncio
    async def test_predicted_confidence_correct(self):
        result = await self._run(
            pred_rows=[("industry", 72.5)],
            obs_rows=[("industry", 10, 6)],
            band_rows=[],
        )
        item = result.recommendation_types[0]
        assert item.predicted_confidence == pytest.approx(72.5)

    @pytest.mark.asyncio
    async def test_observed_success_rate_correct(self):
        result = await self._run(
            pred_rows=[("channel", 60.0)],
            obs_rows=[("channel", 10, 7)],  # 7/10 * 100 = 70.0
            band_rows=[],
        )
        item = result.recommendation_types[0]
        assert item.observed_success_rate == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_calibration_delta_overconfident_negative(self):
        # predicted=80, observed=65 → delta = 65 - 80 = -15
        result = await self._run(
            pred_rows=[("industry", 80.0)],
            obs_rows=[("industry", 10, 6)],  # 60% observed
            band_rows=[],
        )
        item = result.recommendation_types[0]
        assert item.calibration_delta == pytest.approx(60.0 - 80.0)

    @pytest.mark.asyncio
    async def test_calibration_delta_underconfident_positive(self):
        # predicted=60, observed=90 → delta = 90 - 60 = +30
        result = await self._run(
            pred_rows=[("topic", 60.0)],
            obs_rows=[("topic", 10, 9)],  # 90% observed
            band_rows=[],
        )
        item = result.recommendation_types[0]
        assert item.calibration_delta == pytest.approx(90.0 - 60.0)

    @pytest.mark.asyncio
    async def test_calibration_delta_perfect_zero(self):
        result = await self._run(
            pred_rows=[("pricing", 75.0)],
            obs_rows=[("pricing", 4, 3)],  # 75% observed
            band_rows=[],
        )
        item = result.recommendation_types[0]
        assert item.calibration_delta == pytest.approx(0.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_overall_high_confidence_band(self):
        result = await self._run(
            pred_rows=[("industry", 80.0)],
            obs_rows=[("industry", 10, 8)],
            band_rows=[("high", 10, 8)],  # 80% success in high band
        )
        assert result.overall.high_confidence_success_rate == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_overall_medium_confidence_band(self):
        result = await self._run(
            pred_rows=[("industry", 55.0)],
            obs_rows=[("industry", 6, 3)],
            band_rows=[("medium", 6, 3)],  # 50% success in medium band
        )
        assert result.overall.medium_confidence_success_rate == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_overall_low_confidence_band(self):
        result = await self._run(
            pred_rows=[("industry", 30.0)],
            obs_rows=[("industry", 5, 1)],
            band_rows=[("low", 5, 1)],  # 20% success in low band
        )
        assert result.overall.low_confidence_success_rate == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_overall_band_none_when_no_acted(self):
        result = await self._run(
            pred_rows=[("industry", 80.0)],
            obs_rows=[("industry", 10, 8)],
            band_rows=[],  # no band data at all
        )
        assert result.overall.high_confidence_success_rate is None
        assert result.overall.medium_confidence_success_rate is None
        assert result.overall.low_confidence_success_rate is None

    @pytest.mark.asyncio
    async def test_minimum_acted_recommendations_field_value(self):
        result = await self._run(pred_rows=[], obs_rows=[], band_rows=[])
        assert result.minimum_acted_recommendations == 5

    @pytest.mark.asyncio
    async def test_multiple_types_all_present(self):
        result = await self._run(
            pred_rows=[("industry", 70.0), ("topic", 60.0), ("channel", 80.0)],
            obs_rows=[
                ("industry", 10, 7),
                ("topic", 8, 5),
                ("channel", 12, 10),
            ],
            band_rows=[],
        )
        types = {item.recommendation_type for item in result.recommendation_types}
        assert types == {"industry", "topic", "channel"}


class TestGetCalibrationCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db_query(self):
        svc = _make_svc()
        cached = RecCalibrationOut(
            generated_at=datetime.now(UTC),
            overall=RecCalibrationOverallOut(
                high_confidence_success_rate=None,
                medium_confidence_success_rate=None,
                low_confidence_success_rate=None,
            ),
            recommendation_types=[],
            insufficient_data=True,
        ).model_dump_json()

        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=cached)
            mock_redis.return_value.set = AsyncMock()

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        svc._session.execute.assert_not_called()  # type: ignore[attr-defined]
        assert result.insufficient_data is True

    @pytest.mark.asyncio
    async def test_cache_miss_stores_with_1h_ttl(self):
        svc = _make_svc()
        svc._session.execute = AsyncMock(return_value=_mock_text_result([]))
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            await svc.get_calibration(workspace_id=WORKSPACE_ID)

        set_call = mock_redis.return_value.set.call_args
        assert set_call.kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_gracefully(self):
        svc = _make_svc()
        svc._session.execute = AsyncMock(return_value=_mock_text_result([]))
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(side_effect=ConnectionError)
            mock_redis.return_value.set = AsyncMock(side_effect=ConnectionError)

            result = await svc.get_calibration(workspace_id=WORKSPACE_ID)

        assert isinstance(result, RecCalibrationOut)

    @pytest.mark.asyncio
    async def test_calibration_scoped_to_tenant_cache_key(self):
        svc = _make_svc()
        svc._session.execute = AsyncMock(return_value=_mock_text_result([]))
        with (
            patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
            patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        ):
            mock_redis.return_value.get = AsyncMock(return_value=None)
            mock_redis.return_value.set = AsyncMock()

            await svc.get_calibration(workspace_id=WORKSPACE_ID)

        cache_key = mock_redis.return_value.set.call_args.args[0]
        assert str(TENANT_ID) in cache_key
        assert "calibration" in cache_key


# ── Schema contract tests ─────────────────────────────────────────────────────


class TestSchemaContracts:
    def test_rec_effectiveness_out_has_required_fields(self):
        out = RecEffectivenessOut(
            generated_at=datetime.now(UTC),
            summary=RecEffectivenessSummaryOut(
                recommendations_generated=0,
                recommendations_acted=0,
                recommendations_successful=0,
                adoption_rate=0.0,
                success_rate=0.0,
            ),
            by_type=[],
            quality_trend=[],
        )
        assert hasattr(out, "summary")
        assert hasattr(out, "by_type")
        assert hasattr(out, "quality_trend")
        assert hasattr(out, "generated_at")

    def test_rec_calibration_type_item_has_delta(self):
        item = RecCalibrationTypeItemOut(
            recommendation_type="industry",
            predicted_confidence=75.0,
            observed_success_rate=65.0,
            calibration_delta=-10.0,
        )
        assert item.calibration_delta == -10.0

    def test_adoption_rate_and_success_rate_zero_to_one_scale(self):
        summary = RecEffectivenessSummaryOut(
            recommendations_generated=10,
            recommendations_acted=4,
            recommendations_successful=2,
            adoption_rate=0.4,
            success_rate=0.5,
        )
        assert 0.0 <= summary.adoption_rate <= 1.0
        assert 0.0 <= summary.success_rate <= 1.0

    def test_quality_trend_point_fields(self):
        pt = QualityTrendPointOut(
            score_date=date(2026, 6, 1),
            rec_type="channel",
            quality_score=82,
            adoption_rate=0.45,
            success_rate=0.6,
        )
        assert pt.score_date == date(2026, 6, 1)
        assert pt.quality_score == 82


# ── Pure calibration delta arithmetic ────────────────────────────────────────


class TestCalibrationDeltaArithmetic:
    """Verifies the delta formula without any mocking — pure math."""

    def _delta(self, predicted: float, acted: int, success: int) -> float | None:
        if acted == 0:
            return None
        observed = round(success / acted * 100, 2)
        return round(observed - predicted, 2)

    def test_overconfident_negative_delta(self):
        assert self._delta(80.0, 10, 6) == pytest.approx(-20.0)

    def test_underconfident_positive_delta(self):
        assert self._delta(60.0, 10, 9) == pytest.approx(30.0)

    def test_perfect_calibration_zero_delta(self):
        assert self._delta(75.0, 4, 3) == pytest.approx(0.0, abs=0.01)

    def test_no_acted_returns_none(self):
        assert self._delta(80.0, 0, 0) is None

    def test_all_success_rate_100(self):
        assert self._delta(70.0, 5, 5) == pytest.approx(30.0)

    def test_zero_success_rate(self):
        assert self._delta(70.0, 5, 0) == pytest.approx(-70.0)
