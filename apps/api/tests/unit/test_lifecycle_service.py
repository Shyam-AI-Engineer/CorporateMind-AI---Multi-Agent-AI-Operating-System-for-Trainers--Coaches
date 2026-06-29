"""Unit tests for RecommendationLifecycleService (Sprint 24A).

Covers:
  _classify_age_bucket() — pure static
    - 0 days   → "0-7"
    - 7 days   → "0-7"     (boundary inclusive)
    - 8 days   → "8-30"
    - 30 days  → "8-30"    (boundary inclusive)
    - 31 days  → "31-60"
    - 60 days  → "31-60"   (boundary inclusive)
    - 61 days  → "60+"
    - 365 days → "60+"

  _decay_detected() — pure static
    - best − worst = 10.0  → True  (boundary inclusive)
    - best − worst = 9.9   → False
    - best − worst = 0     → False
    - best − worst = 20    → True

  _compute_lifecycle_stats() — pure static
    - empty list                        → (0.0, 0.0, 0.0, 0.0)
    - acted=True with acted_at          → non-zero avg_days_to_action
    - acted=False rows excluded from days_to_action avg but counted in denominator
    - success=True with success_measured_at → non-zero avg_days_to_success
    - success=False rows excluded from days_to_success avg
    - acted_at=None rows excluded from timing avg
    - acted_rate = acted_count / total × 100
    - success_rate = success=True count / total × 100
    - correct rounding (2dp)

  get_lifecycle() — insufficient_data
    - no rows → insufficient_data=True, overall zeros, types=[]

  get_lifecycle() — with data
    - overall rates computed correctly
    - types sorted alphabetically
    - types list matches distinct rec_types in rows
    - overall avg_days_to_action > 0 when acted rows have acted_at

  get_lifecycle() — cache
    - cache hit  → repo NOT called
    - cache miss → result stored ex=3600
    - Redis failure → graceful fallback

  get_decay() — bucket classification
    - each row lands in correct bucket based on today - snapshot_date
    - bucket order is canonical 0-7, 8-30, 31-60, 60+
    - always emits all 4 buckets even if empty

  get_decay() — rates
    - acted_rate = acted / total × 100 per bucket
    - success_rate = success / total × 100 per bucket
    - empty bucket has sample_size=0, rates 0.0

  get_decay() — decay detection
    - type with only 1 non-empty bucket excluded from recommendation_types
    - decay_detected=True when best − worst >= 10
    - decay_detected=False when best − worst < 10
    - recommendation_types sorted alphabetically

  get_decay() — cache
    - cache hit  → repo NOT called
    - cache miss → result stored ex=3600
    - Redis failure → graceful fallback
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.repo import OutcomeWithTiming
from corpmind.modules.analytics.service import RecommendationLifecycleService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    return ctx


def _make_row(
    rec_type: str = "channel",
    acted: bool = False,
    acted_at: datetime | None = None,
    success: bool | None = None,
    success_measured_at: datetime | None = None,
    snapshot_generated_at: datetime | None = None,
    snapshot_date: date | None = None,
) -> OutcomeWithTiming:
    return OutcomeWithTiming(
        rec_type=rec_type,
        acted=acted,
        acted_at=acted_at,
        success=success,
        success_measured_at=success_measured_at,
        snapshot_generated_at=snapshot_generated_at or datetime(2026, 1, 1, tzinfo=UTC),
        snapshot_date=snapshot_date or date(2026, 1, 1),
    )


def _acted_row(
    rec_type: str = "channel",
    days_after_snapshot: float = 5.0,
    success: bool | None = None,
    success_days: float | None = None,
    snapshot_date: date | None = None,
) -> OutcomeWithTiming:
    gen_at = datetime(2026, 1, 1, tzinfo=UTC)
    acted_at = gen_at + timedelta(days=days_after_snapshot)
    s_measured_at = (gen_at + timedelta(days=success_days)) if success_days is not None else None
    return OutcomeWithTiming(
        rec_type=rec_type,
        acted=True,
        acted_at=acted_at,
        success=success,
        success_measured_at=s_measured_at,
        snapshot_generated_at=gen_at,
        snapshot_date=snapshot_date or date(2026, 1, 1),
    )


def _svc() -> RecommendationLifecycleService:
    session = AsyncMock()
    return RecommendationLifecycleService(session)


def _patch_all(rows: list[OutcomeWithTiming], redis_cached: str | None = None):
    ctx = _ctx()
    redis_mock = AsyncMock(
        get=AsyncMock(return_value=redis_cached),
        set=AsyncMock(),
    )
    return (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
        patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo.list_with_snapshot",
            new_callable=AsyncMock,
            return_value=rows,
        ),
        redis_mock,
    )


# ── _classify_age_bucket ──────────────────────────────────────────────────────


def test_bucket_zero_days() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(0) == "0-7"


def test_bucket_7_days_inclusive() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(7) == "0-7"


def test_bucket_8_days() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(8) == "8-30"


def test_bucket_30_days_inclusive() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(30) == "8-30"


def test_bucket_31_days() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(31) == "31-60"


def test_bucket_60_days_inclusive() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(60) == "31-60"


def test_bucket_61_days() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(61) == "60+"


def test_bucket_365_days() -> None:
    assert RecommendationLifecycleService._classify_age_bucket(365) == "60+"


# ── _decay_detected ───────────────────────────────────────────────────────────


def test_decay_detected_exactly_10_is_true() -> None:
    assert RecommendationLifecycleService._decay_detected(50.0, 40.0) is True


def test_decay_detected_9_9_is_false() -> None:
    assert RecommendationLifecycleService._decay_detected(49.9, 40.0) is False


def test_decay_detected_zero_is_false() -> None:
    assert RecommendationLifecycleService._decay_detected(50.0, 50.0) is False


def test_decay_detected_large_gap() -> None:
    assert RecommendationLifecycleService._decay_detected(80.0, 20.0) is True


# ── _compute_lifecycle_stats ──────────────────────────────────────────────────


def test_lifecycle_stats_empty() -> None:
    result = RecommendationLifecycleService._compute_lifecycle_stats([])
    assert result == (0.0, 0.0, 0.0, 0.0)


def test_lifecycle_stats_acted_rate() -> None:
    rows = [_acted_row(), _make_row(acted=False)]
    _, _, acted_rate, _ = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    assert acted_rate == 50.0


def test_lifecycle_stats_success_rate() -> None:
    rows = [
        _acted_row(success=True, success_days=10.0),
        _make_row(acted=False, success=False),
        _make_row(acted=False, success=None),
    ]
    _, _, _, success_rate = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    assert success_rate == pytest.approx(33.33, abs=0.1)


def test_lifecycle_stats_avg_days_to_action() -> None:
    rows = [_acted_row(days_after_snapshot=10.0), _acted_row(days_after_snapshot=20.0)]
    avg_a, _, _, _ = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    assert avg_a == 15.0


def test_lifecycle_stats_acted_at_none_excluded_from_avg() -> None:
    """acted=True but acted_at=None must not crash and must not skew the avg."""
    rows = [
        _acted_row(days_after_snapshot=10.0),
        _make_row(acted=True, acted_at=None),  # acted but no timestamp
    ]
    avg_a, _, acted_rate, _ = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    assert avg_a == 10.0  # only the row with a timestamp contributes
    assert acted_rate == 100.0  # both rows are acted=True


def test_lifecycle_stats_avg_days_to_success() -> None:
    rows = [
        _acted_row(success=True, success_days=20.0),
        _acted_row(success=True, success_days=40.0),
    ]
    _, avg_s, _, _ = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    assert avg_s == 30.0


def test_lifecycle_stats_rounding() -> None:
    rows = [
        _acted_row(days_after_snapshot=1.0 / 3),
    ]
    avg_a, _, _, _ = RecommendationLifecycleService._compute_lifecycle_stats(rows)
    # 1/3 day ≈ 0.33
    assert avg_a == pytest.approx(0.33, abs=0.01)


# ── get_lifecycle() — insufficient_data ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lifecycle_no_rows_insufficient_data() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    p_ctx, p_redis, p_repo, _ = _patch_all([])
    with p_ctx, p_redis, p_repo:
        out = await svc.get_lifecycle(workspace_id=ws)

    assert out.insufficient_data is True
    assert out.recommendation_types == []
    assert out.overall.avg_days_to_action == 0.0


# ── get_lifecycle() — with data ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lifecycle_overall_rates() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    rows = [
        _acted_row(days_after_snapshot=5.0, success=True, success_days=15.0),
        _make_row(acted=False, success=False),
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_lifecycle(workspace_id=ws)

    assert out.insufficient_data is False
    assert out.overall.acted_rate == 50.0
    assert out.overall.success_rate == 50.0
    assert out.overall.avg_days_to_action == 5.0
    assert out.overall.avg_days_to_success == 15.0


@pytest.mark.asyncio
async def test_get_lifecycle_types_sorted_alphabetically() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    rows = [
        _acted_row(rec_type="topic"),
        _acted_row(rec_type="channel"),
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_lifecycle(workspace_id=ws)

    types = [t.recommendation_type for t in out.recommendation_types]
    assert types == sorted(types)


@pytest.mark.asyncio
async def test_get_lifecycle_per_type_matches_rec_types() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    rows = [
        _acted_row(rec_type="channel"),
        _acted_row(rec_type="channel"),
        _acted_row(rec_type="industry"),
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_lifecycle(workspace_id=ws)

    type_names = {t.recommendation_type for t in out.recommendation_types}
    assert type_names == {"channel", "industry"}


@pytest.mark.asyncio
async def test_get_lifecycle_overall_avg_days_positive() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    rows = [_acted_row(days_after_snapshot=12.0)]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_lifecycle(workspace_id=ws)

    assert out.overall.avg_days_to_action == 12.0


# ── get_lifecycle() — cache ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lifecycle_cache_hit_skips_repo() -> None:
    from corpmind.modules.analytics.schemas import LifecycleOut, LifecycleOverallOut

    cached = LifecycleOut(
        generated_at=datetime.now(UTC),
        overall=LifecycleOverallOut(
            avg_days_to_action=7.0,
            avg_days_to_success=14.0,
            acted_rate=60.0,
            success_rate=40.0,
        ),
        recommendation_types=[],
        insufficient_data=False,
    )
    svc = _svc()
    ws = uuid.uuid4()
    ctx = _ctx()
    mock_repo = AsyncMock()

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=ctx),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=cached.model_dump_json())),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo",
            return_value=mock_repo,
        ),
    ):
        out = await svc.get_lifecycle(workspace_id=ws)

    mock_repo.list_with_snapshot.assert_not_called()
    assert out.overall.avg_days_to_action == 7.0


@pytest.mark.asyncio
async def test_get_lifecycle_cache_miss_stores_with_ttl() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    redis_mock = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
    rows = [_acted_row(days_after_snapshot=5.0)]

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo.list_with_snapshot",
            new_callable=AsyncMock,
            return_value=rows,
        ),
    ):
        await svc.get_lifecycle(workspace_id=ws)

    redis_mock.set.assert_called_once()
    call_kwargs = redis_mock.set.call_args.kwargs
    assert call_kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_get_lifecycle_redis_failure_graceful() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    failing = MagicMock()
    failing.get = AsyncMock(side_effect=Exception("redis down"))
    failing.set = AsyncMock(side_effect=Exception("redis down"))

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis", return_value=failing),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo.list_with_snapshot",
            new_callable=AsyncMock,
            return_value=[_acted_row()],
        ),
    ):
        out = await svc.get_lifecycle(workspace_id=ws)

    assert out is not None


# ── get_decay() — bucket classification ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_decay_always_emits_four_buckets() -> None:
    """Even with no data, all 4 buckets must appear in canonical order."""
    svc = _svc()
    ws = uuid.uuid4()
    p_ctx, p_redis, p_repo, _ = _patch_all([])
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    bucket_names = [b.age_bucket for b in out.buckets]
    assert bucket_names == ["0-7", "8-30", "31-60", "60+"]


@pytest.mark.asyncio
async def test_get_decay_empty_bucket_zero_sample_size() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    # Only a row in 0-7 bucket; the rest should be zero
    row = _make_row(acted=True, snapshot_date=today - timedelta(days=3))
    p_ctx, p_redis, p_repo, _ = _patch_all([row])
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    for b in out.buckets:
        if b.age_bucket != "0-7":
            assert b.sample_size == 0
            assert b.acted_rate == 0.0
            assert b.success_rate == 0.0


@pytest.mark.asyncio
async def test_get_decay_row_lands_in_correct_bucket() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        _make_row(acted=True, success=True, snapshot_date=today - timedelta(days=5)),   # 0-7
        _make_row(acted=True, success=False, snapshot_date=today - timedelta(days=15)), # 8-30
        _make_row(acted=False, success=None, snapshot_date=today - timedelta(days=45)), # 31-60
        _make_row(acted=False, success=None, snapshot_date=today - timedelta(days=90)), # 60+
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    bucket_map = {b.age_bucket: b for b in out.buckets}
    assert bucket_map["0-7"].sample_size == 1
    assert bucket_map["8-30"].sample_size == 1
    assert bucket_map["31-60"].sample_size == 1
    assert bucket_map["60+"].sample_size == 1


@pytest.mark.asyncio
async def test_get_decay_acted_rate_per_bucket() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        _make_row(acted=True, snapshot_date=today - timedelta(days=2)),  # 0-7
        _make_row(acted=False, snapshot_date=today - timedelta(days=4)), # 0-7
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    bucket_map = {b.age_bucket: b for b in out.buckets}
    assert bucket_map["0-7"].acted_rate == 50.0


@pytest.mark.asyncio
async def test_get_decay_success_rate_per_bucket() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        _make_row(success=True, snapshot_date=today - timedelta(days=10)),
        _make_row(success=True, snapshot_date=today - timedelta(days=12)),
        _make_row(success=False, snapshot_date=today - timedelta(days=14)),
        _make_row(success=False, snapshot_date=today - timedelta(days=16)),
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    bucket_map = {b.age_bucket: b for b in out.buckets}
    assert bucket_map["8-30"].success_rate == 50.0


# ── get_decay() — decay detection ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_decay_type_with_one_bucket_excluded() -> None:
    """A type with outcomes only in one bracket cannot show decay."""
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [_make_row(rec_type="channel", success=True, snapshot_date=today - timedelta(days=3))]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    assert all(t.recommendation_type != "channel" for t in out.recommendation_types)


@pytest.mark.asyncio
async def test_get_decay_detected_true() -> None:
    """Best bracket 80% success, worst bracket 50% → decay=True (diff=30)."""
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        # 0-7: 4 rows, all success → 100%
        *[_make_row(rec_type="topic", success=True, snapshot_date=today - timedelta(days=3)) for _ in range(4)],
        # 31-60: 4 rows, none success → 0%
        *[_make_row(rec_type="topic", success=False, snapshot_date=today - timedelta(days=45)) for _ in range(4)],
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    topic_items = [t for t in out.recommendation_types if t.recommendation_type == "topic"]
    assert len(topic_items) == 1
    assert topic_items[0].decay_detected is True
    assert topic_items[0].best_bucket == "0-7"
    assert topic_items[0].worst_bucket == "31-60"


@pytest.mark.asyncio
async def test_get_decay_detected_false_small_diff() -> None:
    """Best bracket 55%, worst 50% → diff=5 → decay=False."""
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        # 0-7: 11 success out of 20 → 55%
        *[_make_row(rec_type="channel", success=True, snapshot_date=today - timedelta(days=3)) for _ in range(11)],
        *[_make_row(rec_type="channel", success=False, snapshot_date=today - timedelta(days=4)) for _ in range(9)],
        # 8-30: 10 success out of 20 → 50%
        *[_make_row(rec_type="channel", success=True, snapshot_date=today - timedelta(days=15)) for _ in range(10)],
        *[_make_row(rec_type="channel", success=False, snapshot_date=today - timedelta(days=16)) for _ in range(10)],
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    ch_items = [t for t in out.recommendation_types if t.recommendation_type == "channel"]
    assert len(ch_items) == 1
    assert ch_items[0].decay_detected is False


@pytest.mark.asyncio
async def test_get_decay_types_sorted_alphabetically() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    today = date.today()
    rows = [
        # topic: 0-7 and 60+
        _make_row(rec_type="topic", success=True, snapshot_date=today - timedelta(days=3)),
        _make_row(rec_type="topic", success=False, snapshot_date=today - timedelta(days=90)),
        # channel: 0-7 and 60+
        _make_row(rec_type="channel", success=True, snapshot_date=today - timedelta(days=3)),
        _make_row(rec_type="channel", success=False, snapshot_date=today - timedelta(days=90)),
    ]
    p_ctx, p_redis, p_repo, _ = _patch_all(rows)
    with p_ctx, p_redis, p_repo:
        out = await svc.get_decay(workspace_id=ws)

    types = [t.recommendation_type for t in out.recommendation_types]
    assert types == sorted(types)


# ── get_decay() — cache ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_decay_cache_hit_skips_repo() -> None:
    from corpmind.modules.analytics.schemas import DecayOut, DecayBucketOut

    cached = DecayOut(
        generated_at=datetime.now(UTC),
        buckets=[
            DecayBucketOut(age_bucket="0-7", acted_rate=50.0, success_rate=40.0, sample_size=10),
            DecayBucketOut(age_bucket="8-30", acted_rate=0.0, success_rate=0.0, sample_size=0),
            DecayBucketOut(age_bucket="31-60", acted_rate=0.0, success_rate=0.0, sample_size=0),
            DecayBucketOut(age_bucket="60+", acted_rate=0.0, success_rate=0.0, sample_size=0),
        ],
        recommendation_types=[],
    )
    svc = _svc()
    ws = uuid.uuid4()
    mock_repo = AsyncMock()

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch(
            "corpmind.modules.analytics.service.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=cached.model_dump_json())),
        ),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo",
            return_value=mock_repo,
        ),
    ):
        out = await svc.get_decay(workspace_id=ws)

    mock_repo.list_with_snapshot.assert_not_called()
    assert out.buckets[0].sample_size == 10


@pytest.mark.asyncio
async def test_get_decay_cache_miss_stores_with_ttl() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    redis_mock = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
    today = date.today()
    rows = [
        _make_row(snapshot_date=today - timedelta(days=5)),
        _make_row(snapshot_date=today - timedelta(days=35)),
    ]

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis", return_value=redis_mock),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo.list_with_snapshot",
            new_callable=AsyncMock,
            return_value=rows,
        ),
    ):
        await svc.get_decay(workspace_id=ws)

    redis_mock.set.assert_called_once()
    assert redis_mock.set.call_args.kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_get_decay_redis_failure_graceful() -> None:
    svc = _svc()
    ws = uuid.uuid4()
    failing = MagicMock()
    failing.get = AsyncMock(side_effect=Exception("redis down"))
    failing.set = AsyncMock(side_effect=Exception("redis down"))
    today = date.today()

    with (
        patch("corpmind.modules.analytics.service.get_tenant_context", return_value=_ctx()),
        patch("corpmind.modules.analytics.service.get_redis", return_value=failing),
        patch(
            "corpmind.modules.analytics.service.RecommendationOutcomeRepo.list_with_snapshot",
            new_callable=AsyncMock,
            return_value=[_make_row(snapshot_date=today - timedelta(days=5))],
        ),
    ):
        out = await svc.get_decay(workspace_id=ws)

    assert out is not None
    assert len(out.buckets) == 4
