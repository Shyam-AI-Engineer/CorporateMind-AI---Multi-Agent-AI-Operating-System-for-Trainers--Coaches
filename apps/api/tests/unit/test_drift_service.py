"""Unit tests for RecommendationDriftService (Sprint 23B).

Covers:
  _classify_direction() — pure static
    - change > 5   → "improving"
    - change == 5  → "stable"   (boundary: 5 is NOT > 5)
    - change == 5.1 → "improving"
    - change < -5  → "declining"
    - change == -5 → "stable"   (boundary: -5 is NOT < -5)
    - change == -5.1 → "declining"
    - change == 0  → "stable"

  _classify_reliability() — pure static
    - score >= 75  → "high"
    - score == 75  → "high"    (boundary)
    - score == 74.9 → "medium"
    - score >= 50  → "medium"
    - score == 50  → "medium"  (boundary)
    - score == 49.9 → "low"
    - score == 0   → "low"

  _period_averages() — pure static
    - empty list                   → (0.0, 0.0, 0.0)
    - single row, all zeros        → (0.0, 0.0, 0.0)
    - adoption_rate=0.5            → avg_adoption_pct == 50.0
    - success_rate=0.25            → avg_success_pct == 25.0
    - quality_score=None excluded  → avg_quality == 0.0
    - non-None quality_score used  → correct average
    - multiple rows                → correct averages

  _make_trend() — classmethod
    - current > previous by >5    → direction "improving"
    - current < previous by >5    → direction "declining"
    - current == previous         → direction "stable", change == 0.0
    - change rounds to 2dp        → correct rounding

  get_drift() — insufficient_data
    - no rows at all              → insufficient_data=True
    - only current rows (no prev) → insufficient_data=True
    - previous_rows empty         → insufficient_data=True, by_type=[]

  get_drift() — with data
    - improving quality_score     → direction "improving"
    - declining quality_score     → direction "declining"
    - adoption_rate converted ×100 before threshold
    - by_type has correct rec_type
    - by_type sorted alphabetically
    - overall change computed correctly

  get_drift() — cache
    - cache hit → repo NOT called
    - cache miss → stores result with ex=3600
    - Redis failure → graceful fallback to live query

  get_reliability() — insufficient_data
    - no rows → insufficient_data=True, overall score 0.0, rating "low"

  get_reliability() — formula
    - success_rate=1.0, adoption=1.0, quality=100 → score=100.0
    - quality_score=None → contributes 0.0 to formula
    - high score ≥ 75 → rating "high"
    - medium score 50–74 → rating "medium"
    - low score < 50 → rating "low"
    - overall == average of type scores
    - types sorted alphabetically

  get_reliability() — cache
    - cache hit → repo NOT called
    - cache miss → stores result with ex=3600
    - Redis failure → graceful fallback
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.service import RecommendationDriftService
from corpmind.modules.analytics.models import RecommendationQualityScore


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ctx(
    org_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    ctx.workspace_id = workspace_id or uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
    return ctx


def _make_row(
    rec_type: str = "industry",
    score_date: date | None = None,
    quality_score: int | None = 70,
    adoption_rate: float = 0.40,
    success_rate: float = 0.50,
) -> RecommendationQualityScore:
    row = MagicMock(spec=RecommendationQualityScore)
    row.rec_type = rec_type
    row.score_date = score_date or date.today()
    row.quality_score = quality_score
    row.adoption_rate = Decimal(str(adoption_rate))
    row.success_rate = Decimal(str(success_rate))
    return row


def _svc() -> tuple[RecommendationDriftService, AsyncMock]:
    session = AsyncMock()
    svc = RecommendationDriftService(session)
    return svc, session


# ── _classify_direction ───────────────────────────────────────────────────────


def test_classify_direction_improving() -> None:
    assert RecommendationDriftService._classify_direction(5.1) == "improving"


def test_classify_direction_boundary_5_is_stable() -> None:
    assert RecommendationDriftService._classify_direction(5.0) == "stable"


def test_classify_direction_declining() -> None:
    assert RecommendationDriftService._classify_direction(-5.1) == "declining"


def test_classify_direction_boundary_neg5_is_stable() -> None:
    assert RecommendationDriftService._classify_direction(-5.0) == "stable"


def test_classify_direction_zero() -> None:
    assert RecommendationDriftService._classify_direction(0.0) == "stable"


def test_classify_direction_large_positive() -> None:
    assert RecommendationDriftService._classify_direction(20.0) == "improving"


def test_classify_direction_large_negative() -> None:
    assert RecommendationDriftService._classify_direction(-20.0) == "declining"


# ── _classify_reliability ─────────────────────────────────────────────────────


def test_classify_reliability_high() -> None:
    assert RecommendationDriftService._classify_reliability(75.0) == "high"


def test_classify_reliability_just_below_high() -> None:
    assert RecommendationDriftService._classify_reliability(74.9) == "medium"


def test_classify_reliability_medium() -> None:
    assert RecommendationDriftService._classify_reliability(60.0) == "medium"


def test_classify_reliability_boundary_50_is_medium() -> None:
    assert RecommendationDriftService._classify_reliability(50.0) == "medium"


def test_classify_reliability_just_below_medium() -> None:
    assert RecommendationDriftService._classify_reliability(49.9) == "low"


def test_classify_reliability_zero() -> None:
    assert RecommendationDriftService._classify_reliability(0.0) == "low"


# ── _period_averages ──────────────────────────────────────────────────────────


def test_period_averages_empty() -> None:
    avg_q, avg_a, avg_s = RecommendationDriftService._period_averages([])
    assert avg_q == 0.0
    assert avg_a == 0.0
    assert avg_s == 0.0


def test_period_averages_adoption_converted_to_pct() -> None:
    row = _make_row(adoption_rate=0.35, success_rate=0.0, quality_score=None)
    _, avg_a, _ = RecommendationDriftService._period_averages([row])
    assert avg_a == 35.0


def test_period_averages_success_converted_to_pct() -> None:
    row = _make_row(success_rate=0.60, adoption_rate=0.0, quality_score=None)
    _, _, avg_s = RecommendationDriftService._period_averages([row])
    assert avg_s == 60.0


def test_period_averages_none_quality_excluded() -> None:
    row = _make_row(quality_score=None)
    avg_q, _, _ = RecommendationDriftService._period_averages([row])
    assert avg_q == 0.0


def test_period_averages_quality_score_used() -> None:
    row = _make_row(quality_score=80)
    avg_q, _, _ = RecommendationDriftService._period_averages([row])
    assert avg_q == 80.0


def test_period_averages_multiple_rows() -> None:
    rows = [_make_row(quality_score=60), _make_row(quality_score=80)]
    avg_q, _, _ = RecommendationDriftService._period_averages(rows)
    assert avg_q == 70.0


# ── _make_trend ───────────────────────────────────────────────────────────────


def test_make_trend_improving() -> None:
    trend = RecommendationDriftService._make_trend(80.0, 60.0)
    assert trend.change == 20.0
    assert trend.direction == "improving"


def test_make_trend_declining() -> None:
    trend = RecommendationDriftService._make_trend(50.0, 70.0)
    assert trend.change == -20.0
    assert trend.direction == "declining"


def test_make_trend_stable_zero() -> None:
    trend = RecommendationDriftService._make_trend(60.0, 60.0)
    assert trend.change == 0.0
    assert trend.direction == "stable"


def test_make_trend_boundary_exactly_5() -> None:
    trend = RecommendationDriftService._make_trend(65.0, 60.0)
    assert trend.change == 5.0
    assert trend.direction == "stable"


# ── get_drift — insufficient_data ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_drift_no_rows_insufficient_data() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out.insufficient_data is True
    assert out.by_type == []


@pytest.mark.asyncio
async def test_get_drift_only_current_rows_insufficient_data() -> None:
    """If all rows fall in the current window (no prior history), drift cannot be measured."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    current_rows = [_make_row(score_date=today)]  # only current

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=current_rows,
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out.insufficient_data is True


# ── get_drift — with data ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_drift_improving_quality_score() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    current_row = _make_row(quality_score=80, score_date=today)
    previous_row = _make_row(quality_score=60, score_date=prev_start)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[current_row, previous_row],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out.insufficient_data is False
    assert out.overall.quality_score.direction == "improving"
    assert out.overall.quality_score.change == 20.0


@pytest.mark.asyncio
async def test_get_drift_declining_quality_score() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    current_row = _make_row(quality_score=50, score_date=today)
    previous_row = _make_row(quality_score=80, score_date=prev_start)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[current_row, previous_row],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out.overall.quality_score.direction == "declining"
    assert out.overall.quality_score.change == -30.0


@pytest.mark.asyncio
async def test_get_drift_adoption_rate_converted_to_pct() -> None:
    """adoption_rate stored as 0-1 fraction must be ×100 before threshold."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    # current: adoption 0.80 (80%), previous: adoption 0.60 (60%) → change = +20 → improving
    current_row = _make_row(adoption_rate=0.80, success_rate=0.0, quality_score=None, score_date=today)
    previous_row = _make_row(adoption_rate=0.60, success_rate=0.0, quality_score=None, score_date=prev_start)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[current_row, previous_row],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out.overall.adoption_rate.current == 80.0
    assert out.overall.adoption_rate.previous == 60.0
    assert out.overall.adoption_rate.direction == "improving"


@pytest.mark.asyncio
async def test_get_drift_by_type_correct_rec_type() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    current_row = _make_row(rec_type="channel", quality_score=70, score_date=today)
    previous_row = _make_row(rec_type="channel", quality_score=60, score_date=prev_start)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[current_row, previous_row],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert len(out.by_type) == 1
    assert out.by_type[0].recommendation_type == "channel"


@pytest.mark.asyncio
async def test_get_drift_by_type_sorted_alphabetically() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    rows = [
        _make_row(rec_type="topic", quality_score=70, score_date=today),
        _make_row(rec_type="channel", quality_score=70, score_date=today),
        _make_row(rec_type="topic", quality_score=60, score_date=prev_start),
        _make_row(rec_type="channel", quality_score=60, score_date=prev_start),
    ]

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=rows,
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    types = [item.recommendation_type for item in out.by_type]
    assert types == sorted(types)


# ── get_drift — cache ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_drift_cache_hit_returns_cached() -> None:
    from corpmind.modules.analytics.schemas import (
        DriftOut,
        DriftOverallOut,
        MetricTrendOut,
    )

    cached_out = DriftOut(
        generated_at=datetime.now(UTC),
        overall=DriftOverallOut(
            quality_score=MetricTrendOut(current=70.0, previous=60.0, change=10.0, direction="improving"),
            adoption_rate=MetricTrendOut(current=40.0, previous=35.0, change=5.0, direction="stable"),
            success_rate=MetricTrendOut(current=50.0, previous=45.0, change=5.0, direction="stable"),
        ),
        by_type=[],
        insufficient_data=False,
    )

    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()

    mock_repo = AsyncMock()

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(
                get=AsyncMock(return_value=cached_out.model_dump_json()),
            ),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo",
            return_value=mock_repo,
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    mock_repo.list_by_workspace.assert_not_called()
    assert out.overall.quality_score.direction == "improving"


@pytest.mark.asyncio
async def test_get_drift_cache_miss_stores_result() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    redis_mock = AsyncMock(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
    )

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[
                _make_row(quality_score=70, score_date=today),
                _make_row(quality_score=60, score_date=prev_start),
            ],
        ),
    ):
        await svc.get_drift(workspace_id=ws)

    redis_mock.set.assert_called_once()
    call_kwargs = redis_mock.set.call_args
    assert call_kwargs.kwargs.get("ex") == 3600 or (
        len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 3600
    ) or (call_kwargs.kwargs.get("ex") == 3600)


@pytest.mark.asyncio
async def test_get_drift_redis_failure_falls_back() -> None:
    """Redis get/set failure must not raise — live query runs instead."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev_start = today - timedelta(days=59)

    failing_redis = MagicMock()
    failing_redis.get = AsyncMock(side_effect=Exception("redis down"))
    failing_redis.set = AsyncMock(side_effect=Exception("redis down"))

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=failing_redis,
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[
                _make_row(quality_score=70, score_date=today),
                _make_row(quality_score=60, score_date=prev_start),
            ],
        ),
    ):
        out = await svc.get_drift(workspace_id=ws)

    assert out is not None


# ── get_reliability — insufficient_data ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reliability_no_rows_insufficient_data() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out.insufficient_data is True
    assert out.overall_reliability.score == 0.0
    assert out.overall_reliability.rating == "low"
    assert out.recommendation_types == []


# ── get_reliability — formula ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reliability_perfect_score() -> None:
    """success=1.0 × 50 + adoption=1.0 × 30 + quality=100 × 20 = 100.0 → "high"."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    row = _make_row(success_rate=1.0, adoption_rate=1.0, quality_score=100)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[row],
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out.recommendation_types[0].reliability_score == 100.0
    assert out.recommendation_types[0].rating == "high"


@pytest.mark.asyncio
async def test_get_reliability_none_quality_contributes_zero() -> None:
    """quality_score=None → formula = success*50 + adoption*30 + 0."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    # success=0.6 (→60%), adoption=0.5 (→50%), quality=None → 60*0.5 + 50*0.3 + 0 = 30+15 = 45.0
    row = _make_row(success_rate=0.6, adoption_rate=0.5, quality_score=None)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[row],
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out.recommendation_types[0].reliability_score == 45.0
    assert out.recommendation_types[0].rating == "low"


@pytest.mark.asyncio
async def test_get_reliability_medium_rating() -> None:
    """score in 50–74 range → "medium"."""
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    # success=0.6 (60%), adoption=0.6 (60%), quality=50 → 60*0.5 + 60*0.3 + 50*0.2 = 30+18+10 = 58.0
    row = _make_row(success_rate=0.6, adoption_rate=0.6, quality_score=50)

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[row],
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out.recommendation_types[0].rating == "medium"


@pytest.mark.asyncio
async def test_get_reliability_overall_is_mean_of_types() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev = today - timedelta(days=1)
    # type "channel": score = 100*0.5 + 100*0.3 + 100*0.2 = 100.0
    # type "industry": score = 0*0.5 + 0*0.3 + 0*0.2 = 0.0
    # overall = (100 + 0) / 2 = 50.0 → "medium"
    rows = [
        _make_row(rec_type="channel", success_rate=1.0, adoption_rate=1.0, quality_score=100, score_date=today),
        _make_row(rec_type="industry", success_rate=0.0, adoption_rate=0.0, quality_score=0, score_date=prev),
    ]

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=rows,
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out.overall_reliability.score == 50.0
    assert out.overall_reliability.rating == "medium"


@pytest.mark.asyncio
async def test_get_reliability_types_sorted_alphabetically() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    today = date.today()
    prev = today - timedelta(days=1)

    rows = [
        _make_row(rec_type="topic", score_date=today),
        _make_row(rec_type="channel", score_date=prev),
    ]

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock()),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=rows,
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    types = [t.recommendation_type for t in out.recommendation_types]
    assert types == sorted(types)


# ── get_reliability — cache ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reliability_cache_hit_returns_cached() -> None:
    from corpmind.modules.analytics.schemas import (
        ReliabilityOut,
        ReliabilityOverallOut,
    )

    cached_out = ReliabilityOut(
        generated_at=datetime.now(UTC),
        overall_reliability=ReliabilityOverallOut(score=80.0, rating="high"),
        recommendation_types=[],
        insufficient_data=False,
    )

    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()
    mock_repo = AsyncMock()

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(
                get=AsyncMock(return_value=cached_out.model_dump_json()),
            ),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo",
            return_value=mock_repo,
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    mock_repo.list_by_workspace.assert_not_called()
    assert out.overall_reliability.score == 80.0


@pytest.mark.asyncio
async def test_get_reliability_cache_miss_stores_result() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()

    redis_mock = AsyncMock(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
    )

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[_make_row()],
        ),
    ):
        await svc.get_reliability(workspace_id=ws)

    redis_mock.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_reliability_redis_failure_falls_back() -> None:
    svc, _ = _svc()
    ctx = _ctx()
    ws = uuid.uuid4()

    failing_redis = MagicMock()
    failing_redis.get = AsyncMock(side_effect=Exception("redis down"))
    failing_redis.set = AsyncMock(side_effect=Exception("redis down"))

    with (
        patch(
            "corpmind.modules.analytics.service.get_tenant_context",
            return_value=ctx,
        ),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=failing_redis,
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationQualityScoreRepo.list_by_workspace",
            new_callable=AsyncMock,
            return_value=[_make_row()],
        ),
    ):
        out = await svc.get_reliability(workspace_id=ws)

    assert out is not None
