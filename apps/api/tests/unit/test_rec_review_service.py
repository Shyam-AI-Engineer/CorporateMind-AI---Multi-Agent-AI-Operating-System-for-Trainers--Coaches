"""Unit tests for RecommendationReviewService (Sprint 22B).

Covers:
  get_review() — empty state
    - no quality score rows → insufficient_data=True, all fields None/empty
    - caches the empty response with 1h TTL
    - generated_at is present

  get_review() — performer rankings
    - best_performing_type: rec_type with highest quality_score (non-null)
    - worst_performing_type: rec_type with lowest quality_score (non-null)
    - low_confidence types (quality_score=None) excluded from best/worst
    - all types low_confidence → best/worst are None
    - most_ignored_type: highest ignored_count / shown_count
    - types with shown_count=0 excluded from most_ignored
    - most_adopted_type: highest adoption_rate (zero excluded)
    - all zero adoption_rate → most_adopted_type is None
    - most_successful_type: highest success_rate (zero excluded)
    - all zero success_rate → most_successful_type is None
    - single type → best and worst are the same type

  _classify_calibration() — pure static function
    - delta == -15 → overconfident
    - delta == -5  → overconfident (boundary: delta <= -5)
    - delta == -4.9 → well_calibrated
    - delta == 0   → well_calibrated
    - delta == +4.9 → well_calibrated
    - delta == +5  → underconfident (boundary: delta >= 5)
    - delta == +20 → underconfident
    - delta == None → excluded from all groups
    - multiple types → each classified independently
    - empty input → all three groups empty

  quality_trend — daily average
    - single type per day → quality_score equals that type's score
    - multiple types per day → quality_score is their average
    - low_confidence days (all None) excluded from trend
    - trend sorted date asc
    - mixed null and non-null on same day → only averages non-null

  Redis cache
    - cache hit → returns cached value without calling repo
    - cache miss → stores result with 1h TTL
    - Redis unavailable → falls back gracefully to live query
    - cache key includes tenant_id for tenant isolation

  Schema contracts
    - RecReviewOut has all required fields
    - insufficient_data defaults to False
    - RecBestWorstPerformerOut quality_score is int
    - RecIgnoredTypeOut ignored_rate is float
    - RecReviewTrendPointOut quality_score is float
    - RecCalibrationGroupSummaryOut has the three group fields
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import RecommendationQualityScore
from corpmind.modules.analytics.schemas import (
    RecBestWorstPerformerOut,
    RecCalibrationGroupSummaryOut,
    RecCalibrationOut,
    RecCalibrationOverallOut,
    RecCalibrationTypeItemOut,
    RecIgnoredTypeOut,
    RecReviewOut,
    RecReviewTrendPointOut,
)
from corpmind.modules.analytics.service import RecommendationReviewService

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
TODAY = date(2026, 6, 24)


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _make_row(
    *,
    rec_type: str,
    score_date: date = TODAY,
    quality_score: int | None = 80,
    adoption_rate: float = 0.4,
    success_rate: float = 0.5,
    shown_count: int = 10,
    acted_count: int = 4,
    success_count: int = 2,
    ignored_count: int = 3,
    low_confidence: bool = False,
) -> RecommendationQualityScore:
    row = MagicMock(spec=RecommendationQualityScore)
    row.rec_type = rec_type
    row.score_date = score_date
    row.quality_score = quality_score
    row.adoption_rate = Decimal(str(adoption_rate))
    row.success_rate = Decimal(str(success_rate))
    row.shown_count = shown_count
    row.acted_count = acted_count
    row.success_count = success_count
    row.ignored_count = ignored_count
    row.low_confidence = low_confidence
    return row


def _make_calibration_out(
    types: list[RecCalibrationTypeItemOut] | None = None,
) -> RecCalibrationOut:
    return RecCalibrationOut(
        generated_at=datetime.now(UTC),
        overall=RecCalibrationOverallOut(
            high_confidence_success_rate=None,
            medium_confidence_success_rate=None,
            low_confidence_success_rate=None,
        ),
        recommendation_types=types or [],
        insufficient_data=False,
        minimum_acted_recommendations=5,
    )


def _svc() -> RecommendationReviewService:
    return RecommendationReviewService(MagicMock())


def _patch_repo(rows: list) -> MagicMock:
    mock_repo = MagicMock()
    mock_repo.list_by_workspace = AsyncMock(return_value=rows)
    return mock_repo


# ── get_review() — empty state ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_rows_returns_insufficient_data():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.insufficient_data is True
    assert result.best_performing_type is None
    assert result.worst_performing_type is None
    assert result.most_ignored_type is None
    assert result.most_adopted_type is None
    assert result.most_successful_type is None
    assert result.quality_trend == []
    assert result.calibration_summary.overconfident == []
    assert result.calibration_summary.underconfident == []
    assert result.calibration_summary.well_calibrated == []


@pytest.mark.asyncio
async def test_empty_result_cached_with_1h_ttl():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        await svc.get_review(workspace_id=WORKSPACE_ID)

    mock_redis.return_value.set.assert_called_once()
    assert mock_redis.return_value.set.call_args[1]["ex"] == 3600


@pytest.mark.asyncio
async def test_empty_result_has_generated_at():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.generated_at is not None


# ── get_review() — performer rankings ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_best_performing_type_highest_quality_score():
    rows = [
        _make_row(rec_type="industry", quality_score=90),
        _make_row(rec_type="channel", quality_score=60),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.best_performing_type is not None
    assert result.best_performing_type.recommendation_type == "industry"
    assert result.best_performing_type.quality_score == 90


@pytest.mark.asyncio
async def test_worst_performing_type_lowest_quality_score():
    rows = [
        _make_row(rec_type="industry", quality_score=90),
        _make_row(rec_type="channel", quality_score=60),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.worst_performing_type is not None
    assert result.worst_performing_type.recommendation_type == "channel"
    assert result.worst_performing_type.quality_score == 60


@pytest.mark.asyncio
async def test_low_confidence_excluded_from_best_worst():
    rows = [
        _make_row(rec_type="industry", quality_score=None, low_confidence=True),
        _make_row(rec_type="channel", quality_score=70),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.best_performing_type is not None
    assert result.best_performing_type.recommendation_type == "channel"
    assert result.worst_performing_type is not None
    assert result.worst_performing_type.recommendation_type == "channel"


@pytest.mark.asyncio
async def test_all_low_confidence_best_worst_are_none():
    rows = [
        _make_row(rec_type="industry", quality_score=None, low_confidence=True),
        _make_row(rec_type="channel", quality_score=None, low_confidence=True),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.best_performing_type is None
    assert result.worst_performing_type is None


@pytest.mark.asyncio
async def test_most_ignored_type_highest_ignored_rate():
    rows = [
        _make_row(rec_type="industry", shown_count=10, ignored_count=8),
        _make_row(rec_type="channel", shown_count=10, ignored_count=2),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_ignored_type is not None
    assert result.most_ignored_type.recommendation_type == "industry"
    assert result.most_ignored_type.ignored_rate == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_shown_count_zero_excluded_from_most_ignored():
    rows = [
        _make_row(rec_type="industry", shown_count=0, ignored_count=0),
        _make_row(rec_type="channel", shown_count=10, ignored_count=3),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_ignored_type is not None
    assert result.most_ignored_type.recommendation_type == "channel"


@pytest.mark.asyncio
async def test_most_adopted_type_highest_adoption_rate():
    rows = [
        _make_row(rec_type="industry", adoption_rate=0.7),
        _make_row(rec_type="channel", adoption_rate=0.3),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_adopted_type is not None
    assert result.most_adopted_type.recommendation_type == "industry"
    assert result.most_adopted_type.adoption_rate == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_all_zero_adoption_rate_returns_none():
    rows = [
        _make_row(rec_type="industry", adoption_rate=0.0),
        _make_row(rec_type="channel", adoption_rate=0.0),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_adopted_type is None


@pytest.mark.asyncio
async def test_most_successful_type_highest_success_rate():
    rows = [
        _make_row(rec_type="topic", success_rate=0.8),
        _make_row(rec_type="channel", success_rate=0.3),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_successful_type is not None
    assert result.most_successful_type.recommendation_type == "topic"
    assert result.most_successful_type.success_rate == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_all_zero_success_rate_returns_none():
    rows = [_make_row(rec_type="industry", success_rate=0.0)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.most_successful_type is None


@pytest.mark.asyncio
async def test_single_type_is_both_best_and_worst():
    rows = [_make_row(rec_type="pricing", quality_score=75)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.best_performing_type is not None
    assert result.worst_performing_type is not None
    assert result.best_performing_type.recommendation_type == "pricing"
    assert result.worst_performing_type.recommendation_type == "pricing"


# ── _classify_calibration() — pure static function ────────────────────────────

def _cal_item(rec_type: str, delta: float | None) -> RecCalibrationTypeItemOut:
    return RecCalibrationTypeItemOut(
        recommendation_type=rec_type,
        predicted_confidence=70.0,
        observed_success_rate=None if delta is None else 70.0 + delta,
        calibration_delta=delta,
    )


def test_classify_large_negative_delta_overconfident():
    result = RecommendationReviewService._classify_calibration([_cal_item("industry", -15.0)])
    assert len(result.overconfident) == 1
    assert result.overconfident[0].recommendation_type == "industry"


def test_classify_delta_minus_5_boundary_overconfident():
    result = RecommendationReviewService._classify_calibration([_cal_item("channel", -5.0)])
    assert len(result.overconfident) == 1


def test_classify_delta_minus_4_9_is_well_calibrated():
    result = RecommendationReviewService._classify_calibration([_cal_item("topic", -4.9)])
    assert len(result.well_calibrated) == 1
    assert result.well_calibrated[0].recommendation_type == "topic"


def test_classify_delta_zero_is_well_calibrated():
    result = RecommendationReviewService._classify_calibration([_cal_item("pricing", 0.0)])
    assert len(result.well_calibrated) == 1


def test_classify_delta_plus_4_9_is_well_calibrated():
    result = RecommendationReviewService._classify_calibration([_cal_item("campaign", 4.9)])
    assert len(result.well_calibrated) == 1


def test_classify_delta_plus_5_boundary_underconfident():
    result = RecommendationReviewService._classify_calibration([_cal_item("industry", 5.0)])
    assert len(result.underconfident) == 1


def test_classify_large_positive_delta_underconfident():
    result = RecommendationReviewService._classify_calibration([_cal_item("channel", 20.0)])
    assert len(result.underconfident) == 1
    assert result.underconfident[0].recommendation_type == "channel"


def test_classify_none_delta_excluded_from_all_groups():
    result = RecommendationReviewService._classify_calibration([_cal_item("pricing", None)])
    assert len(result.overconfident) == 0
    assert len(result.underconfident) == 0
    assert len(result.well_calibrated) == 0


def test_classify_multiple_types_classified_independently():
    items = [
        _cal_item("industry", -10.0),
        _cal_item("channel", 2.0),
        _cal_item("topic", 8.0),
        _cal_item("pricing", None),
    ]
    result = RecommendationReviewService._classify_calibration(items)
    assert len(result.overconfident) == 1
    assert len(result.well_calibrated) == 1
    assert len(result.underconfident) == 1


def test_classify_empty_input_all_groups_empty():
    result = RecommendationReviewService._classify_calibration([])
    assert result.overconfident == []
    assert result.underconfident == []
    assert result.well_calibrated == []


# ── quality_trend ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trend_single_type_equals_that_score():
    rows = [_make_row(rec_type="industry", score_date=TODAY, quality_score=80)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert len(result.quality_trend) == 1
    assert result.quality_trend[0].quality_score == pytest.approx(80.0)
    assert result.quality_trend[0].date == TODAY


@pytest.mark.asyncio
async def test_trend_multiple_types_per_day_averaged():
    rows = [
        _make_row(rec_type="industry", score_date=TODAY, quality_score=80),
        _make_row(rec_type="channel", score_date=TODAY, quality_score=60),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert len(result.quality_trend) == 1
    assert result.quality_trend[0].quality_score == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_trend_all_null_quality_scores_excluded():
    rows = [
        _make_row(rec_type="industry", score_date=TODAY, quality_score=None, low_confidence=True),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.quality_trend == []


@pytest.mark.asyncio
async def test_trend_sorted_date_asc():
    d1 = date(2026, 6, 10)
    d2 = date(2026, 6, 20)
    rows = [
        _make_row(rec_type="industry", score_date=d2, quality_score=90),
        _make_row(rec_type="industry", score_date=d1, quality_score=70),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    dates = [p.date for p in result.quality_trend]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_trend_mixed_null_and_non_null_averages_only_non_null():
    rows = [
        _make_row(rec_type="industry", score_date=TODAY, quality_score=None, low_confidence=True),
        _make_row(rec_type="channel", score_date=TODAY, quality_score=80),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert len(result.quality_trend) == 1
    assert result.quality_trend[0].quality_score == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_trend_two_distinct_days_produce_two_points():
    d1 = date(2026, 6, 10)
    d2 = date(2026, 6, 20)
    rows = [
        _make_row(rec_type="industry", score_date=d1, quality_score=70),
        _make_row(rec_type="industry", score_date=d2, quality_score=80),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert len(result.quality_trend) == 2


# ── Redis cache ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_hit_skips_db_query():
    svc = _svc()
    mock_repo = _patch_repo([])
    cached_data = RecReviewOut(
        generated_at=datetime.now(UTC),
        best_performing_type=None,
        worst_performing_type=None,
        most_ignored_type=None,
        most_adopted_type=None,
        most_successful_type=None,
        calibration_summary=RecCalibrationGroupSummaryOut(
            overconfident=[], underconfident=[], well_calibrated=[],
        ),
        quality_trend=[],
        insufficient_data=True,
    )
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=cached_data.model_dump_json())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    mock_repo.list_by_workspace.assert_not_called()
    assert result.insufficient_data is True


@pytest.mark.asyncio
async def test_cache_miss_stores_with_3600s_ttl():
    rows = [_make_row(rec_type="industry", quality_score=80)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        await svc.get_review(workspace_id=WORKSPACE_ID)

    mock_redis.return_value.set.assert_called_once()
    assert mock_redis.return_value.set.call_args[1]["ex"] == 3600


@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_live_query():
    rows = [_make_row(rec_type="industry", quality_score=70)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.return_value.set = AsyncMock(side_effect=Exception("redis down"))
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        result = await svc.get_review(workspace_id=WORKSPACE_ID)

    assert result.insufficient_data is False
    assert result.best_performing_type is not None


@pytest.mark.asyncio
async def test_cache_key_includes_tenant_and_workspace():
    rows = [_make_row(rec_type="industry")]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    ctx = _ctx()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=_make_calibration_out())
        await svc.get_review(workspace_id=WORKSPACE_ID)

    set_key = mock_redis.return_value.set.call_args[0][0]
    assert str(ctx.org_id) in set_key
    assert str(WORKSPACE_ID) in set_key
    assert "review" in set_key


# ── Schema contracts ───────────────────────────────────────────────────────────

def test_rec_review_out_has_all_required_fields():
    fields = RecReviewOut.model_fields
    for field in [
        "best_performing_type",
        "worst_performing_type",
        "most_ignored_type",
        "most_adopted_type",
        "most_successful_type",
        "calibration_summary",
        "quality_trend",
        "insufficient_data",
        "generated_at",
    ]:
        assert field in fields


def test_insufficient_data_defaults_false():
    out = RecReviewOut(
        generated_at=datetime.now(UTC),
        best_performing_type=None,
        worst_performing_type=None,
        most_ignored_type=None,
        most_adopted_type=None,
        most_successful_type=None,
        calibration_summary=RecCalibrationGroupSummaryOut(
            overconfident=[], underconfident=[], well_calibrated=[],
        ),
        quality_trend=[],
    )
    assert out.insufficient_data is False


def test_rec_best_worst_performer_out_fields():
    p = RecBestWorstPerformerOut(recommendation_type="industry", quality_score=85)
    assert p.recommendation_type == "industry"
    assert p.quality_score == 85
    assert isinstance(p.quality_score, int)


def test_rec_ignored_type_out_rate_is_float():
    i = RecIgnoredTypeOut(recommendation_type="channel", ignored_rate=0.75)
    assert i.ignored_rate == 0.75
    assert isinstance(i.ignored_rate, float)


def test_rec_review_trend_point_quality_score_is_float():
    p = RecReviewTrendPointOut(date=TODAY, quality_score=72.5)
    assert p.quality_score == 72.5
    assert isinstance(p.quality_score, float)


def test_calibration_group_summary_has_three_fields():
    fields = RecCalibrationGroupSummaryOut.model_fields
    assert "overconfident" in fields
    assert "underconfident" in fields
    assert "well_calibrated" in fields
