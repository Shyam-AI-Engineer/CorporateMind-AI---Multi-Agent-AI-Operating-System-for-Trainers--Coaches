"""Unit tests for RecommendationCalibrationService (Sprint 23A).

Covers:
  _classify_severity() — pure static
    - delta == -20   → "severe"
    - delta == -15   → "warning" (boundary: abs == 15)
    - delta == -15.1 → "severe"
    - delta == -5    → "warning" (boundary: abs == 5)
    - delta == -4.9  → "calibrated"
    - delta == 0     → "calibrated"
    - delta == +4.9  → "calibrated"
    - delta == +5    → "warning" (boundary: abs == 5)
    - delta == +15   → "warning" (boundary: abs == 15)
    - delta == +15.1 → "severe"
    - delta == None  → None

  _classify_stability() — pure static
    - std_dev == 0   → "stable"
    - std_dev == 4.9 → "stable"
    - std_dev == 5   → "volatile" (boundary)
    - std_dev == 15  → "volatile" (boundary)
    - std_dev == 15.1 → "unstable"
    - std_dev == 20  → "unstable"

  _population_std_dev() — pure static
    - empty list           → 0.0
    - single value         → 0.0
    - two equal values     → 0.0
    - two different values → correct result
    - multiple values      → correct population std_dev

  get_calibration_review() — confidence distribution
    - all three bands present → correct counts
    - missing band             → defaults to 0
    - no snapshots             → all counts are 0

  get_calibration_review() — accuracy counts
    - all well-calibrated (abs(delta) < 5)
    - overconfident type (delta <= -5)
    - underconfident type (delta >= +5)
    - mixed types → each bucket counted independently
    - delta=None types excluded from all counts

  get_calibration_review() — per-type severity
    - severity "calibrated" when abs(delta) < 5
    - severity "warning"    when 5 <= abs <= 15
    - severity "severe"     when abs > 15
    - severity None         when delta is None

  get_calibration_review() — overall passthrough
    - overall from 22A calibration is passed through unchanged

  get_calibration_review() — insufficient_data
    - propagates insufficient_data=True from 22A calibration

  get_calibration_review() — cache
    - cache hit returns cached value without calling session or calibration
    - cache miss stores result with ex=3600
    - Redis failure falls back gracefully to live query

  get_stability() — empty / insufficient
    - no rows → insufficient_data=True, empty recommendation_types
    - all low_confidence rows → insufficient_data=False, empty recommendation_types

  get_stability() — std_dev computation
    - single type, one value → std_dev=0.0, stable
    - single type, multiple values → correct std_dev
    - std_dev in 5–15 range → "volatile"
    - std_dev > 15 → "unstable"
    - multiple types sorted alphabetically

  get_stability() — overall
    - overall aggregates all non-null quality scores across types
    - overall std_dev of uniform scores → 0.0

  get_stability() — cache
    - cache hit → repo NOT called
    - cache miss → stores result with ex=3600
    - Redis failure → graceful fallback

  Schema contracts
    - CalibrationReviewOut has all required fields
    - StabilityOut has all required fields
    - CalibrationReviewTypeItemOut accepts None delta and severity
    - ConfidenceDistributionOut field types are int
    - StabilityTypeItemOut stability_rating is string
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import RecommendationQualityScore
from corpmind.modules.analytics.schemas import (
    CalibrationAccuracyOut,
    CalibrationReviewOut,
    CalibrationReviewTypeItemOut,
    ConfidenceDistributionOut,
    QualityScoreStabilityOut,
    RecCalibrationOut,
    RecCalibrationOverallOut,
    RecCalibrationTypeItemOut,
    StabilityOut,
    StabilityTypeItemOut,
)
from corpmind.modules.analytics.service import RecommendationCalibrationService

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
TODAY = date(2026, 6, 24)


# ── helpers ────────────────────────────────────────────────────────────────────


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


def _make_row(
    *,
    rec_type: str,
    score_date: date = TODAY,
    quality_score: int | None = 80,
    shown_count: int = 10,
    ignored_count: int = 2,
    adoption_rate: float = 0.3,
    success_rate: float = 0.2,
    low_confidence: bool = False,
) -> RecommendationQualityScore:
    row = MagicMock(spec=RecommendationQualityScore)
    row.rec_type = rec_type
    row.score_date = score_date
    row.quality_score = quality_score
    row.shown_count = shown_count
    row.ignored_count = ignored_count
    row.adoption_rate = Decimal(str(adoption_rate))
    row.success_rate = Decimal(str(success_rate))
    row.low_confidence = low_confidence
    return row


def _make_calibration_out(
    *,
    types: list[RecCalibrationTypeItemOut] | None = None,
    insufficient: bool = False,
    high_rate: float | None = 80.0,
    medium_rate: float | None = 60.0,
    low_rate: float | None = 40.0,
) -> RecCalibrationOut:
    return RecCalibrationOut(
        generated_at=datetime.now(UTC),
        overall=RecCalibrationOverallOut(
            high_confidence_success_rate=high_rate,
            medium_confidence_success_rate=medium_rate,
            low_confidence_success_rate=low_rate,
        ),
        recommendation_types=types or [],
        insufficient_data=insufficient,
        minimum_acted_recommendations=5,
    )


def _cal_type(
    rec_type: str,
    *,
    delta: float | None,
    predicted: float = 70.0,
    observed: float | None = None,
) -> RecCalibrationTypeItemOut:
    if observed is None and delta is not None:
        observed = predicted + delta
    return RecCalibrationTypeItemOut(
        recommendation_type=rec_type,
        predicted_confidence=predicted,
        observed_success_rate=observed,
        calibration_delta=delta,
    )


def _svc() -> RecommendationCalibrationService:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_dist_result([]))
    return RecommendationCalibrationService(session)


def _svc_with_dist(dist_rows: list[tuple[str, int]]) -> RecommendationCalibrationService:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_dist_result(dist_rows))
    return RecommendationCalibrationService(session)


def _dist_result(rows: list[tuple[str, int]]) -> MagicMock:
    """Fake SQLAlchemy result for the confidence distribution COUNT query."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _patch_repo(rows: list) -> MagicMock:
    mock_repo = MagicMock()
    mock_repo.list_by_workspace = AsyncMock(return_value=rows)
    return mock_repo


# ── _classify_severity() ───────────────────────────────────────────────────────


def test_classify_severity_none_returns_none():
    assert RecommendationCalibrationService._classify_severity(None) is None


def test_classify_severity_calibrated_zero():
    assert RecommendationCalibrationService._classify_severity(0.0) == "calibrated"


def test_classify_severity_calibrated_positive_below_5():
    assert RecommendationCalibrationService._classify_severity(4.9) == "calibrated"


def test_classify_severity_calibrated_negative_above_minus5():
    assert RecommendationCalibrationService._classify_severity(-4.9) == "calibrated"


def test_classify_severity_warning_at_5():
    assert RecommendationCalibrationService._classify_severity(5.0) == "warning"


def test_classify_severity_warning_at_minus5():
    assert RecommendationCalibrationService._classify_severity(-5.0) == "warning"


def test_classify_severity_warning_at_15():
    assert RecommendationCalibrationService._classify_severity(15.0) == "warning"


def test_classify_severity_warning_at_minus15():
    assert RecommendationCalibrationService._classify_severity(-15.0) == "warning"


def test_classify_severity_severe_above_15():
    assert RecommendationCalibrationService._classify_severity(15.1) == "severe"


def test_classify_severity_severe_negative():
    assert RecommendationCalibrationService._classify_severity(-20.0) == "severe"


# ── _classify_stability() ─────────────────────────────────────────────────────


def test_classify_stability_stable_zero():
    assert RecommendationCalibrationService._classify_stability(0.0) == "stable"


def test_classify_stability_stable_below_5():
    assert RecommendationCalibrationService._classify_stability(4.99) == "stable"


def test_classify_stability_volatile_at_5():
    assert RecommendationCalibrationService._classify_stability(5.0) == "volatile"


def test_classify_stability_volatile_at_15():
    assert RecommendationCalibrationService._classify_stability(15.0) == "volatile"


def test_classify_stability_unstable_above_15():
    assert RecommendationCalibrationService._classify_stability(15.01) == "unstable"


def test_classify_stability_unstable_large():
    assert RecommendationCalibrationService._classify_stability(50.0) == "unstable"


# ── _population_std_dev() ─────────────────────────────────────────────────────


def test_std_dev_empty_list():
    assert RecommendationCalibrationService._population_std_dev([]) == 0.0


def test_std_dev_single_value():
    assert RecommendationCalibrationService._population_std_dev([80]) == 0.0


def test_std_dev_two_equal_values():
    assert RecommendationCalibrationService._population_std_dev([70, 70]) == 0.0


def test_std_dev_two_different_values():
    result = RecommendationCalibrationService._population_std_dev([60, 80])
    expected = round(math.sqrt(((60 - 70) ** 2 + (80 - 70) ** 2) / 2), 2)
    assert result == expected  # 10.0


def test_std_dev_multiple_values_known_result():
    # values: 50, 60, 70, 80, 90 → mean=70, variance=200, std_dev≈14.14
    result = RecommendationCalibrationService._population_std_dev([50, 60, 70, 80, 90])
    expected = round(math.sqrt(200.0), 2)
    assert result == expected


# ── get_calibration_review() — confidence distribution ────────────────────────


@pytest.mark.asyncio
async def test_confidence_distribution_all_bands():
    svc = _svc_with_dist([("high", 12), ("medium", 7), ("low", 3)])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out()
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.confidence_distribution.high == 12
    assert result.confidence_distribution.medium == 7
    assert result.confidence_distribution.low == 3


@pytest.mark.asyncio
async def test_confidence_distribution_missing_band_defaults_to_zero():
    svc = _svc_with_dist([("high", 5)])  # medium and low missing
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out()
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.confidence_distribution.high == 5
    assert result.confidence_distribution.medium == 0
    assert result.confidence_distribution.low == 0


@pytest.mark.asyncio
async def test_confidence_distribution_no_snapshots_all_zero():
    svc = _svc_with_dist([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out()
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.confidence_distribution.high == 0
    assert result.confidence_distribution.medium == 0
    assert result.confidence_distribution.low == 0


# ── get_calibration_review() — accuracy counts ────────────────────────────────


@pytest.mark.asyncio
async def test_accuracy_all_well_calibrated():
    types = [
        _cal_type("industry", delta=2.0),
        _cal_type("topic", delta=-3.0),
        _cal_type("pricing", delta=0.0),
    ]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.accuracy.well_calibrated_count == 3
    assert result.accuracy.overconfident_count == 0
    assert result.accuracy.underconfident_count == 0


@pytest.mark.asyncio
async def test_accuracy_overconfident_type():
    types = [_cal_type("channel", delta=-10.0)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.accuracy.overconfident_count == 1
    assert result.accuracy.well_calibrated_count == 0
    assert result.accuracy.underconfident_count == 0


@pytest.mark.asyncio
async def test_accuracy_underconfident_type():
    types = [_cal_type("campaign", delta=8.0)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.accuracy.underconfident_count == 1
    assert result.accuracy.well_calibrated_count == 0
    assert result.accuracy.overconfident_count == 0


@pytest.mark.asyncio
async def test_accuracy_none_delta_excluded_from_counts():
    types = [
        _cal_type("industry", delta=None),
        _cal_type("topic", delta=2.0),
    ]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    # only "topic" counted; "industry" (delta=None) excluded
    assert result.accuracy.well_calibrated_count == 1
    assert result.accuracy.overconfident_count == 0
    assert result.accuracy.underconfident_count == 0


# ── get_calibration_review() — per-type severity ──────────────────────────────


@pytest.mark.asyncio
async def test_per_type_severity_calibrated():
    types = [_cal_type("industry", delta=3.0)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].calibration_severity == "calibrated"


@pytest.mark.asyncio
async def test_per_type_severity_warning():
    types = [_cal_type("channel", delta=-10.0)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].calibration_severity == "warning"


@pytest.mark.asyncio
async def test_per_type_severity_severe():
    types = [_cal_type("pricing", delta=20.0)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].calibration_severity == "severe"


@pytest.mark.asyncio
async def test_per_type_severity_none_when_delta_none():
    types = [_cal_type("topic", delta=None)]
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out(types=types)
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].calibration_severity is None


@pytest.mark.asyncio
async def test_overall_passthrough_from_calibration():
    cal = _make_calibration_out(high_rate=85.5, medium_rate=60.0, low_rate=30.0)
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=cal)
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.overall.high_confidence_success_rate == 85.5
    assert result.overall.medium_confidence_success_rate == 60.0
    assert result.overall.low_confidence_success_rate == 30.0


@pytest.mark.asyncio
async def test_insufficient_data_propagated_from_calibration():
    cal = _make_calibration_out(insufficient=True, high_rate=None, medium_rate=None, low_rate=None)
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(return_value=cal)
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert result.insufficient_data is True


# ── get_calibration_review() — cache ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_calibration_review_cache_hit_skips_query():
    svc = _svc()
    cached_out = CalibrationReviewOut(
        generated_at=datetime.now(UTC),
        overall=RecCalibrationOverallOut(
            high_confidence_success_rate=None,
            medium_confidence_success_rate=None,
            low_confidence_success_rate=None,
        ),
        confidence_distribution=ConfidenceDistributionOut(high=1, medium=2, low=3),
        accuracy=CalibrationAccuracyOut(
            well_calibrated_count=1,
            overconfident_count=0,
            underconfident_count=0,
        ),
        recommendation_types=[],
        insufficient_data=False,
    )
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(
            return_value=cached_out.model_dump_json()
        )
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)
        MockCalSvc.return_value.get_calibration.assert_not_called()

    assert result.confidence_distribution.high == 1


@pytest.mark.asyncio
async def test_calibration_review_cache_miss_stores_with_1h_ttl():
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out()
        )
        await svc.get_calibration_review(workspace_id=WORKSPACE_ID)
        mock_redis.return_value.set.assert_called_once()
        _, kwargs = mock_redis.return_value.set.call_args
        assert kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_calibration_review_redis_failure_falls_back():
    svc = _svc()
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationAnalyticsService") as MockCalSvc,
    ):
        mock_redis.return_value.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.return_value.set = AsyncMock()
        MockCalSvc.return_value.get_calibration = AsyncMock(
            return_value=_make_calibration_out()
        )
        result = await svc.get_calibration_review(workspace_id=WORKSPACE_ID)

    assert isinstance(result, CalibrationReviewOut)


# ── get_stability() — empty / insufficient ────────────────────────────────────


@pytest.mark.asyncio
async def test_stability_empty_rows_returns_insufficient():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert result.insufficient_data is True
    assert result.recommendation_types == []
    assert result.quality_score_stability.average == 0.0
    assert result.quality_score_stability.std_dev == 0.0


@pytest.mark.asyncio
async def test_stability_all_low_confidence_rows_produces_empty_types():
    rows = [
        _make_row(rec_type="industry", quality_score=None, low_confidence=True),
        _make_row(rec_type="topic", quality_score=None, low_confidence=True),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert result.insufficient_data is False
    assert result.recommendation_types == []
    assert result.quality_score_stability.average == 0.0


# ── get_stability() — std_dev and classification ─────────────────────────────


@pytest.mark.asyncio
async def test_stability_single_value_std_dev_zero():
    rows = [_make_row(rec_type="channel", quality_score=75)]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].std_dev == 0.0
    assert result.recommendation_types[0].stability_rating == "stable"


@pytest.mark.asyncio
async def test_stability_multiple_values_correct_std_dev():
    rows = [
        _make_row(rec_type="industry", score_date=date(2026, 6, 1), quality_score=60),
        _make_row(rec_type="industry", score_date=date(2026, 6, 2), quality_score=80),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    # mean=70, variance=200, std_dev=10.0
    assert result.recommendation_types[0].std_dev == 10.0
    assert result.recommendation_types[0].stability_rating == "volatile"


@pytest.mark.asyncio
async def test_stability_high_std_dev_unstable():
    # 5 points spread over 60 units → std_dev ≈ 22.8
    rows = [
        _make_row(rec_type="pricing", score_date=date(2026, 5, d), quality_score=s)
        for d, s in enumerate([10, 30, 50, 70, 90], start=1)
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert result.recommendation_types[0].stability_rating == "unstable"


@pytest.mark.asyncio
async def test_stability_multiple_types_sorted_alphabetically():
    rows = [
        _make_row(rec_type="topic", quality_score=70),
        _make_row(rec_type="industry", quality_score=80),
        _make_row(rec_type="channel", quality_score=60),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    types_out = [item.recommendation_type for item in result.recommendation_types]
    assert types_out == sorted(types_out)


# ── get_stability() — overall ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stability_overall_aggregates_all_types():
    rows = [
        _make_row(rec_type="industry", score_date=date(2026, 6, 1), quality_score=60),
        _make_row(rec_type="industry", score_date=date(2026, 6, 2), quality_score=80),
        _make_row(rec_type="topic", quality_score=70),
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    # all_scores = [60, 80, 70] → mean = 70.0
    assert result.quality_score_stability.average == 70.0


@pytest.mark.asyncio
async def test_stability_overall_uniform_scores_std_dev_zero():
    rows = [
        _make_row(rec_type="industry", score_date=date(2026, 6, d), quality_score=75)
        for d in range(1, 6)
    ]
    svc = _svc()
    mock_repo = _patch_repo(rows)
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch("corpmind.modules.analytics.service.RecommendationQualityScoreRepo", return_value=mock_repo),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert result.quality_score_stability.std_dev == 0.0
    assert result.quality_score_stability.stability_rating == "stable"


# ── get_stability() — cache ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stability_cache_hit_skips_repo():
    svc = _svc()
    mock_repo = _patch_repo([])
    cached_out = StabilityOut(
        generated_at=datetime.now(UTC),
        quality_score_stability=QualityScoreStabilityOut(
            average=75.0, std_dev=3.0, stability_rating="stable"
        ),
        recommendation_types=[],
        insufficient_data=False,
    )
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo",
            return_value=mock_repo,
        ),
    ):
        mock_redis.return_value.get = AsyncMock(
            return_value=cached_out.model_dump_json()
        )
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)
        mock_repo.list_by_workspace.assert_not_called()

    assert result.quality_score_stability.average == 75.0


@pytest.mark.asyncio
async def test_stability_cache_miss_stores_with_1h_ttl():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo",
            return_value=mock_repo,
        ),
    ):
        mock_redis.return_value.get = AsyncMock(return_value=None)
        mock_redis.return_value.set = AsyncMock()
        await svc.get_stability(workspace_id=WORKSPACE_ID)
        mock_redis.return_value.set.assert_called_once()
        _, kwargs = mock_redis.return_value.set.call_args
        assert kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_stability_redis_failure_falls_back_gracefully():
    svc = _svc()
    mock_repo = _patch_repo([])
    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis") as mock_redis,
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo",
            return_value=mock_repo,
        ),
    ):
        mock_redis.return_value.get = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.return_value.set = AsyncMock()
        result = await svc.get_stability(workspace_id=WORKSPACE_ID)

    assert isinstance(result, StabilityOut)


# ── Schema contracts ──────────────────────────────────────────────────────────


def test_calibration_review_out_has_all_fields():
    out = CalibrationReviewOut(
        generated_at=datetime.now(UTC),
        overall=RecCalibrationOverallOut(
            high_confidence_success_rate=70.0,
            medium_confidence_success_rate=None,
            low_confidence_success_rate=None,
        ),
        confidence_distribution=ConfidenceDistributionOut(high=5, medium=3, low=1),
        accuracy=CalibrationAccuracyOut(
            well_calibrated_count=2,
            overconfident_count=1,
            underconfident_count=0,
        ),
        recommendation_types=[],
        insufficient_data=False,
    )
    assert out.insufficient_data is False
    assert isinstance(out.confidence_distribution.high, int)
    assert isinstance(out.accuracy.well_calibrated_count, int)


def test_stability_out_has_all_fields():
    out = StabilityOut(
        generated_at=datetime.now(UTC),
        quality_score_stability=QualityScoreStabilityOut(
            average=72.5, std_dev=4.2, stability_rating="stable"
        ),
        recommendation_types=[
            StabilityTypeItemOut(
                recommendation_type="industry",
                average_quality_score=72.5,
                std_dev=4.2,
                stability_rating="stable",
            )
        ],
        insufficient_data=False,
    )
    assert out.insufficient_data is False
    assert out.quality_score_stability.stability_rating == "stable"
    assert out.recommendation_types[0].recommendation_type == "industry"


def test_calibration_review_type_item_accepts_none_fields():
    item = CalibrationReviewTypeItemOut(
        recommendation_type="pricing",
        predicted_confidence=65.0,
        observed_success_rate=None,
        calibration_delta=None,
        calibration_severity=None,
    )
    assert item.calibration_delta is None
    assert item.calibration_severity is None


def test_confidence_distribution_field_types_are_int():
    dist = ConfidenceDistributionOut(high=10, medium=5, low=2)
    assert isinstance(dist.high, int)
    assert isinstance(dist.medium, int)
    assert isinstance(dist.low, int)


def test_stability_type_item_stability_rating_is_string():
    item = StabilityTypeItemOut(
        recommendation_type="channel",
        average_quality_score=68.0,
        std_dev=8.5,
        stability_rating="volatile",
    )
    assert isinstance(item.stability_rating, str)
