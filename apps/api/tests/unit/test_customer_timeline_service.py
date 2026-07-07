"""Unit tests for CustomerTimelineService — Sprint 49.

All tests mock CustomerTimelineRepo so no DB or Redis required.
Covers: timeline ordering, cursor pagination, cache, tenant isolation,
event mapping, empty history, event type filtering, relationship summary,
customer 360 aggregation.
"""

from __future__ import annotations

import base64
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.customer_success.timeline_repo import RawEvent, RawSummaryStats
from corpmind.modules.customer_success.timeline_schemas import (
    VALID_TIMELINE_EVENT_TYPES,
    CustomerRelationshipSummaryOut,
    CustomerTimelineEventOut,
    CustomerTimelinePageOut,
)
from corpmind.modules.customer_success.timeline_service import (
    CustomerTimelineService,
    _days_since,
    _360_key,
    _summary_key,
    _timeline_key,
    decode_cursor,
    encode_cursor,
)

_PATCH_CTX = "corpmind.modules.customer_success.timeline_service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.customer_success.timeline_service.get_redis"
_PATCH_REPO_EVENTS = "corpmind.modules.customer_success.timeline_service.CustomerTimelineRepo.fetch_all_events"
_PATCH_REPO_STATS = "corpmind.modules.customer_success.timeline_service.CustomerTimelineRepo.fetch_summary_stats"

_ORG = uuid.uuid4()
_NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
_CID = uuid.uuid4()


def _ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or _ORG
    return ctx


def _redis() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@contextmanager
def _patch(ctx: MagicMock, redis: MagicMock) -> Generator[None, None, None]:
    with patch(_PATCH_CTX, return_value=ctx):
        with patch(_PATCH_REDIS, return_value=redis):
            yield


def _make_svc() -> tuple[CustomerTimelineService, MagicMock]:
    db = MagicMock()
    svc = CustomerTimelineService(db)
    svc._repo = MagicMock()
    return svc, db


def _raw(
    *,
    event_id: str | None = None,
    event_type: str = "customer_created",
    hours_ago: int = 0,
    title: str = "Test event",
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict | None = None,
) -> RawEvent:
    return RawEvent(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=_NOW - timedelta(hours=hours_ago),
        title=title,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
    )


def _summary(**kw) -> RawSummaryStats:
    defaults = dict(
        total_trainings=0,
        completed_trainings=0,
        total_certificates=0,
        avg_feedback_rating=None,
        current_health=None,
        renewal_status=None,
        latest_activity_at=None,
    )
    defaults.update(kw)
    return RawSummaryStats(**defaults)


# ── TestCursorEncoding ────────────────────────────────────────────────────────

class TestCursorEncoding:
    def test_encode_decode_roundtrip(self) -> None:
        ts = datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC)
        eid = "abc-123"
        cursor = encode_cursor(ts, eid)
        result = decode_cursor(cursor)
        assert result is not None
        decoded_ts, decoded_id = result
        assert decoded_id == eid
        assert decoded_ts.utcoffset().total_seconds() == 0

    def test_decode_invalid_returns_none(self) -> None:
        assert decode_cursor("not-valid-base64!!!!") is None

    def test_decode_empty_returns_none(self) -> None:
        assert decode_cursor("") is None

    def test_encode_produces_url_safe_base64(self) -> None:
        ts = _NOW
        cursor = encode_cursor(ts, "some-id")
        assert "+" not in cursor
        assert "/" not in cursor

    def test_cursor_differs_for_different_timestamps(self) -> None:
        ts1 = _NOW
        ts2 = _NOW + timedelta(seconds=1)
        assert encode_cursor(ts1, "id") != encode_cursor(ts2, "id")

    def test_cursor_differs_for_different_event_ids(self) -> None:
        assert encode_cursor(_NOW, "id-1") != encode_cursor(_NOW, "id-2")

    def test_decode_naive_ts_gets_utc(self) -> None:
        naive = datetime(2026, 7, 7, 10, 0, 0)
        raw = f"{naive.isoformat()}|some-id"
        encoded = base64.urlsafe_b64encode(raw.encode()).decode()
        result = decode_cursor(encoded)
        assert result is not None
        ts, _ = result
        assert ts.tzinfo is not None


# ── TestDaysSince ──────────────────────────────────────────────────────────────

class TestDaysSince:
    def test_none_returns_none(self) -> None:
        assert _days_since(None) is None

    def test_today_returns_zero(self) -> None:
        now = datetime.now(UTC)
        assert _days_since(now) == 0

    def test_yesterday_returns_one(self) -> None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert _days_since(yesterday) == 1

    def test_seven_days_ago(self) -> None:
        seven = datetime.now(UTC) - timedelta(days=7)
        result = _days_since(seven)
        assert result in (7, 6)  # allow off-by-one at midnight boundaries

    def test_naive_ts_handled(self) -> None:
        naive = datetime.now() - timedelta(days=2)
        result = _days_since(naive)
        assert result is not None
        assert result >= 0


# ── TestCacheKeys ──────────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_timeline_key_includes_org_and_customer(self) -> None:
        org = uuid.uuid4()
        cid = uuid.uuid4()
        key = _timeline_key(org, cid)
        assert str(org) in key
        assert str(cid) in key

    def test_summary_key_includes_org_and_customer(self) -> None:
        org = uuid.uuid4()
        cid = uuid.uuid4()
        key = _summary_key(org, cid)
        assert str(org) in key
        assert str(cid) in key

    def test_360_key_includes_org_and_customer(self) -> None:
        org = uuid.uuid4()
        cid = uuid.uuid4()
        key = _360_key(org, cid)
        assert str(org) in key
        assert str(cid) in key

    def test_different_orgs_produce_different_timeline_keys(self) -> None:
        cid = uuid.uuid4()
        o1, o2 = uuid.uuid4(), uuid.uuid4()
        assert _timeline_key(o1, cid) != _timeline_key(o2, cid)

    def test_different_customers_produce_different_timeline_keys(self) -> None:
        org = uuid.uuid4()
        c1, c2 = uuid.uuid4(), uuid.uuid4()
        assert _timeline_key(org, c1) != _timeline_key(org, c2)

    def test_different_key_types_differ(self) -> None:
        org, cid = uuid.uuid4(), uuid.uuid4()
        assert _timeline_key(org, cid) != _summary_key(org, cid)
        assert _summary_key(org, cid) != _360_key(org, cid)


# ── TestGetTimeline ───────────────────────────────────────────────────────────

class TestGetTimeline:
    @pytest.mark.asyncio
    async def test_returns_events(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="customer_created")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_empty_returns_empty(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items == []
        assert result.total == 0
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_events_sorted_desc_by_occurred_at(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [
            _raw(event_type="renewal_created", hours_ago=5),
            _raw(event_type="customer_created", hours_ago=24),
            _raw(event_type="feedback_submitted", hours_ago=1),
        ]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        types = [e.event_type for e in result.items]
        assert types[0] == "feedback_submitted"
        assert types[-1] == "customer_created"

    @pytest.mark.asyncio
    async def test_total_reflects_all_matching_events(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(10)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=5)
        assert result.total == 10

    @pytest.mark.asyncio
    async def test_has_more_true_when_exceeds_limit(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(25)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=20)
        assert result.has_more is True
        assert len(result.items) == 20

    @pytest.mark.asyncio
    async def test_has_more_false_when_under_limit(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(5)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=20)
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_next_cursor_present_when_has_more(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(25)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=20)
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_cursor_filters_events(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(10)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            first_page = await svc.get_timeline(_CID, limit=5)
        assert first_page.next_cursor is not None

        svc._repo.fetch_all_events = AsyncMock(return_value=events)
        with _patch(ctx, redis):
            second_page = await svc.get_timeline(
                _CID, limit=5, cursor=first_page.next_cursor
            )
        # Second page should have different events
        first_ids = {e.event_id for e in first_page.items}
        second_ids = {e.event_id for e in second_page.items}
        assert not first_ids & second_ids

    @pytest.mark.asyncio
    async def test_invalid_cursor_ignored(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(5)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, cursor="not-valid-cursor")
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_event_type_filter_applied(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [
            _raw(event_type="customer_created"),
            _raw(event_type="renewal_created", hours_ago=1),
            _raw(event_type="feedback_submitted", hours_ago=2),
        ]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(
                _CID, event_types=["renewal_created", "feedback_submitted"]
            )
        assert all(e.event_type in {"renewal_created", "feedback_submitted"} for e in result.items)
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_invalid_event_type_filter_excluded(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="customer_created")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, event_types=["fake_type"])
        assert result.items == []

    @pytest.mark.asyncio
    async def test_cache_hit_default_params(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cached = CustomerTimelinePageOut(items=[], total=0).model_dump_json()
        redis.get = AsyncMock(return_value=cached)

        with _patch(ctx, redis):
            await svc.get_timeline(_CID)
        svc._repo.fetch_all_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_set_on_miss_default_params(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_timeline(_CID)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_cache_when_cursor_provided(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(return_value=None)
        svc._repo.fetch_all_events = AsyncMock(return_value=[])
        cursor = encode_cursor(_NOW - timedelta(hours=1), "some-id")

        with _patch(ctx, redis):
            await svc.get_timeline(_CID, cursor=cursor)
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cache_when_event_types_provided(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(return_value=None)
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_timeline(_CID, event_types=["renewal_created"])
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_failure_falls_back(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc._repo.fetch_all_events = AsyncMock(return_value=[_raw()])

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_cache_key_includes_org_id(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_timeline(_CID)
        set_key = redis.set.call_args[0][0]
        assert str(org) in set_key
        assert str(_CID) in set_key

    @pytest.mark.asyncio
    async def test_event_type_attribute_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="certificate_issued")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "certificate_issued"

    @pytest.mark.asyncio
    async def test_detail_dict_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(detail={"key": "value", "count": 5})]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].detail == {"key": "value", "count": 5}

    @pytest.mark.asyncio
    async def test_entity_type_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(entity_type="training_engagement", entity_id="eid-1")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].entity_type == "training_engagement"
        assert result.items[0].entity_id == "eid-1"

    @pytest.mark.asyncio
    async def test_all_10_valid_event_types_accepted(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type=t) for t in sorted(VALID_TIMELINE_EVENT_TYPES)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(
                _CID, event_types=list(VALID_TIMELINE_EVENT_TYPES)
            )
        assert len(result.items) == len(VALID_TIMELINE_EVENT_TYPES)

    @pytest.mark.asyncio
    async def test_limit_1_returns_only_one(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(5)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=1)
        assert len(result.items) == 1
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_limit_100_returns_all_100(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(100)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID, limit=100)
        assert len(result.items) == 100
        assert result.has_more is False


# ── TestGetRelationshipSummary ────────────────────────────────────────────────

class TestGetRelationshipSummary:
    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary(total_trainings=3))

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.total_trainings == 3

    @pytest.mark.asyncio
    async def test_empty_history_returns_zeros(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.total_trainings == 0
        assert result.completed_trainings == 0
        assert result.total_certificates == 0
        assert result.avg_feedback_rating is None

    @pytest.mark.asyncio
    async def test_completed_trainings_counted(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(total_trainings=5, completed_trainings=3)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.completed_trainings == 3

    @pytest.mark.asyncio
    async def test_avg_feedback_rounded(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(avg_feedback_rating=4.3333)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.avg_feedback_rating == 4.33

    @pytest.mark.asyncio
    async def test_no_avg_when_null(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.avg_feedback_rating is None

    @pytest.mark.asyncio
    async def test_current_health_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(current_health="at_risk")
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.current_health == "at_risk"

    @pytest.mark.asyncio
    async def test_renewal_status_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(renewal_status="negotiation")
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.renewal_status == "negotiation"

    @pytest.mark.asyncio
    async def test_latest_activity_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        ts = _NOW - timedelta(days=3)
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(latest_activity_at=ts)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.latest_activity_at == ts

    @pytest.mark.asyncio
    async def test_days_since_calculated(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        ts = datetime.now(UTC) - timedelta(days=5)
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(latest_activity_at=ts)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.days_since_last_interaction in (5, 4)  # boundary tolerance

    @pytest.mark.asyncio
    async def test_days_since_none_when_no_activity(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.days_since_last_interaction is None

    @pytest.mark.asyncio
    async def test_customer_id_included_in_out(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.customer_id == str(_CID)

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        summary = CustomerRelationshipSummaryOut(
            customer_id=str(_CID), total_trainings=99
        )
        redis.get = AsyncMock(return_value=summary.model_dump_json())

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        svc._repo.fetch_summary_stats.assert_not_called()
        assert result.total_trainings == 99

    @pytest.mark.asyncio
    async def test_cache_set_on_miss(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            await svc.get_relationship_summary(_CID)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_failure_fallback(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(total_trainings=2)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.total_trainings == 2

    @pytest.mark.asyncio
    async def test_certificates_counted(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(total_certificates=7)
        )

        with _patch(ctx, redis):
            result = await svc.get_relationship_summary(_CID)
        assert result.total_certificates == 7


# ── TestGetCustomer360 ────────────────────────────────────────────────────────

class TestGetCustomer360:
    @pytest.mark.asyncio
    async def test_returns_360_out(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert result.customer_id == str(_CID)

    @pytest.mark.asyncio
    async def test_includes_summary(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(
            return_value=_summary(total_trainings=4)
        )
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert result.summary.total_trainings == 4

    @pytest.mark.asyncio
    async def test_recent_events_limited_to_10(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i) for i in range(25)]
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert len(result.recent_events) == 10

    @pytest.mark.asyncio
    async def test_recent_events_most_recent_first(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(hours_ago=i, event_type="customer_created") for i in range(15)]
        # override so each has distinct type for ordering verification
        events[0] = _raw(event_type="feedback_submitted", hours_ago=0)
        events[14] = _raw(event_type="customer_created", hours_ago=100)
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert result.recent_events[0].event_type == "feedback_submitted"

    @pytest.mark.asyncio
    async def test_empty_history_no_events(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert result.recent_events == []

    @pytest.mark.asyncio
    async def test_360_cache_hit(self) -> None:
        from corpmind.modules.customer_success.timeline_schemas import Customer360Out
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cached = Customer360Out(
            customer_id=str(_CID),
            summary=CustomerRelationshipSummaryOut(customer_id=str(_CID)),
            recent_events=[],
        )
        redis.get = AsyncMock(return_value=cached.model_dump_json())

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        svc._repo.fetch_all_events.assert_not_called()
        svc._repo.fetch_summary_stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_360_cache_set_on_miss(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_customer_360(_CID)
        assert redis.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_360_cache_failure_fallback(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            result = await svc.get_customer_360(_CID)
        assert result.customer_id == str(_CID)

    @pytest.mark.asyncio
    async def test_360_customer_id_in_out(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        cid2 = uuid.uuid4()
        with _patch(ctx, redis):
            result = await svc.get_customer_360(cid2)
        assert result.customer_id == str(cid2)


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_timeline_key_uses_context_org(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_timeline(_CID)
        set_key = redis.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_summary_key_uses_context_org(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            await svc.get_relationship_summary(_CID)
        set_key = redis.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_different_orgs_different_timeline_cache(self) -> None:
        cid = uuid.uuid4()
        o1, o2 = uuid.uuid4(), uuid.uuid4()
        assert _timeline_key(o1, cid) != _timeline_key(o2, cid)

    @pytest.mark.asyncio
    async def test_different_customers_different_cache(self) -> None:
        org = uuid.uuid4()
        c1, c2 = uuid.uuid4(), uuid.uuid4()
        assert _timeline_key(org, c1) != _timeline_key(org, c2)

    @pytest.mark.asyncio
    async def test_repo_called_with_org_from_context(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        svc._repo.fetch_all_events = AsyncMock(return_value=[])

        with _patch(ctx, redis):
            await svc.get_timeline(_CID)
        call_args = svc._repo.fetch_all_events.call_args
        assert call_args[0][1] == org

    @pytest.mark.asyncio
    async def test_summary_repo_called_with_org_from_context(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        svc._repo.fetch_summary_stats = AsyncMock(return_value=_summary())

        with _patch(ctx, redis):
            await svc.get_relationship_summary(_CID)
        call_args = svc._repo.fetch_summary_stats.call_args
        assert call_args[0][1] == org

    @pytest.mark.asyncio
    async def test_bust_cache_deletes_all_three_keys(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()

        with _patch(ctx, redis):
            await svc.bust_customer_cache(_CID)
        deleted_keys = redis.delete.call_args[0]
        assert len(deleted_keys) == 3

    @pytest.mark.asyncio
    async def test_bust_cache_keys_include_customer_id(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cid = uuid.uuid4()

        with _patch(ctx, redis):
            await svc.bust_customer_cache(cid)
        deleted_keys = redis.delete.call_args[0]
        assert all(str(cid) in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_bust_cache_failure_does_not_raise(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))

        with _patch(ctx, redis):
            await svc.bust_customer_cache(_CID)  # should not raise


# ── TestEventMapping ──────────────────────────────────────────────────────────

class TestEventMapping:
    @pytest.mark.asyncio
    async def test_customer_created_event_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="customer_created")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "customer_created"

    @pytest.mark.asyncio
    async def test_training_engagement_created_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="training_engagement_created")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "training_engagement_created"

    @pytest.mark.asyncio
    async def test_training_session_started_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="training_session_started")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "training_session_started"

    @pytest.mark.asyncio
    async def test_training_session_completed_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="training_session_completed")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "training_session_completed"

    @pytest.mark.asyncio
    async def test_attendance_recorded_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="attendance_recorded")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "attendance_recorded"

    @pytest.mark.asyncio
    async def test_certificate_issued_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="certificate_issued")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "certificate_issued"

    @pytest.mark.asyncio
    async def test_feedback_submitted_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="feedback_submitted")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "feedback_submitted"

    @pytest.mark.asyncio
    async def test_customer_health_updated_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="customer_health_updated")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "customer_health_updated"

    @pytest.mark.asyncio
    async def test_renewal_created_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="renewal_created")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "renewal_created"

    @pytest.mark.asyncio
    async def test_renewal_status_changed_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(event_type="renewal_status_changed")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].event_type == "renewal_status_changed"

    @pytest.mark.asyncio
    async def test_occurred_at_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        ts = _NOW - timedelta(hours=48)
        events = [_raw(hours_ago=48)]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        diff = abs((result.items[0].occurred_at - ts).total_seconds())
        assert diff < 1

    @pytest.mark.asyncio
    async def test_title_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        events = [_raw(title="My specific title")]
        svc._repo.fetch_all_events = AsyncMock(return_value=events)

        with _patch(ctx, redis):
            result = await svc.get_timeline(_CID)
        assert result.items[0].title == "My specific title"

    @pytest.mark.asyncio
    async def test_valid_event_types_set_is_complete(self) -> None:
        expected = {
            "customer_created",
            "training_engagement_created",
            "training_session_started",
            "training_session_completed",
            "attendance_recorded",
            "certificate_issued",
            "feedback_submitted",
            "customer_health_updated",
            "renewal_created",
            "renewal_status_changed",
        }
        assert VALID_TIMELINE_EVENT_TYPES == expected


# ── TestSchemas ───────────────────────────────────────────────────────────────

class TestSchemas:
    def test_event_out_default_detail_empty(self) -> None:
        evt = CustomerTimelineEventOut(
            event_id="id-1",
            event_type="customer_created",
            occurred_at=_NOW,
            title="Test",
        )
        assert evt.detail == {}

    def test_event_out_entity_optional(self) -> None:
        evt = CustomerTimelineEventOut(
            event_id="id-1",
            event_type="customer_created",
            occurred_at=_NOW,
            title="Test",
        )
        assert evt.entity_type is None
        assert evt.entity_id is None

    def test_page_out_defaults(self) -> None:
        page = CustomerTimelinePageOut(items=[])
        assert page.has_more is False
        assert page.next_cursor is None
        assert page.total == 0

    def test_summary_out_defaults(self) -> None:
        s = CustomerRelationshipSummaryOut(customer_id="cid-1")
        assert s.total_trainings == 0
        assert s.avg_feedback_rating is None
        assert s.current_health is None
