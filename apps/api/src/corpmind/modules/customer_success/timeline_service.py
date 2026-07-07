"""Customer 360 timeline service — Sprint 49.

Pure read-only. No writes. No LLM. No Celery.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.customer_success.timeline_repo import (
    CustomerTimelineRepo,
    RawEvent,
)
from corpmind.modules.customer_success.timeline_schemas import (
    Customer360Out,
    CustomerRelationshipSummaryOut,
    CustomerTimelineEventOut,
    CustomerTimelinePageOut,
    VALID_TIMELINE_EVENT_TYPES,
)

log = structlog.get_logger(__name__)

_TIMELINE_TTL = 300
_SUMMARY_TTL = 300
_360_TTL = 300
_RECENT_EVENTS_COUNT = 10


def _timeline_key(org_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    return f"t:{org_id}:customer_timeline:{customer_id}"


def _summary_key(org_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    return f"t:{org_id}:customer_relationship:{customer_id}"


def _360_key(org_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    return f"t:{org_id}:customer360:{customer_id}"


def encode_cursor(occurred_at: datetime, event_id: str) -> str:
    ts = occurred_at.astimezone(UTC).isoformat()
    raw = f"{ts}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, event_id = raw.split("|", 1)
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts, event_id
    except Exception:
        return None


def _to_out(event: RawEvent) -> CustomerTimelineEventOut:
    return CustomerTimelineEventOut(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        title=event.title,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        detail=event.detail,
    )


def _days_since(ts: datetime | None) -> int | None:
    if ts is None:
        return None
    now = datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = now - ts
    return max(0, delta.days)


class CustomerTimelineService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = CustomerTimelineRepo(db)

    # ── get_timeline ──────────────────────────────────────────────────────────

    async def get_timeline(
        self,
        customer_id: uuid.UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        event_types: list[str] | None = None,
    ) -> CustomerTimelinePageOut:
        ctx = get_tenant_context()
        redis = get_redis()

        is_default = cursor is None and event_types is None
        cache_key = _timeline_key(ctx.org_id, customer_id)

        if is_default:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    return CustomerTimelinePageOut.model_validate_json(cached)
            except Exception:
                pass

        all_events = await self._repo.fetch_all_events(customer_id, ctx.org_id)

        # filter by event_type
        if event_types:
            valid_types = {t for t in event_types if t in VALID_TIMELINE_EVENT_TYPES}
            all_events = [e for e in all_events if e.event_type in valid_types]

        # events arrive already sorted DESC from SQL, but re-sort defensively
        all_events.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)

        # cursor-based slice
        if cursor:
            decoded = decode_cursor(cursor)
            if decoded:
                cursor_ts, cursor_id = decoded
                all_events = [
                    e for e in all_events
                    if e.occurred_at < cursor_ts
                    or (e.occurred_at == cursor_ts and e.event_id > cursor_id)
                ]

        total = len(all_events)
        page_events = all_events[: limit + 1]
        has_more = len(page_events) > limit
        if has_more:
            page_events = page_events[:limit]

        next_cursor: str | None = None
        if has_more and page_events:
            last = page_events[-1]
            next_cursor = encode_cursor(last.occurred_at, last.event_id)

        result = CustomerTimelinePageOut(
            items=[_to_out(e) for e in page_events],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )

        if is_default:
            try:
                await redis.set(cache_key, result.model_dump_json(), ex=_TIMELINE_TTL)
            except Exception:
                pass

        return result

    # ── get_relationship_summary ──────────────────────────────────────────────

    async def get_relationship_summary(
        self,
        customer_id: uuid.UUID,
    ) -> CustomerRelationshipSummaryOut:
        ctx = get_tenant_context()
        redis = get_redis()
        cache_key = _summary_key(ctx.org_id, customer_id)

        try:
            cached = await redis.get(cache_key)
            if cached:
                return CustomerRelationshipSummaryOut.model_validate_json(cached)
        except Exception:
            pass

        stats = await self._repo.fetch_summary_stats(customer_id, ctx.org_id)

        result = CustomerRelationshipSummaryOut(
            customer_id=str(customer_id),
            total_trainings=stats.total_trainings,
            completed_trainings=stats.completed_trainings,
            total_certificates=stats.total_certificates,
            avg_feedback_rating=round(stats.avg_feedback_rating, 2)
            if stats.avg_feedback_rating is not None
            else None,
            current_health=stats.current_health,
            renewal_status=stats.renewal_status,
            latest_activity_at=stats.latest_activity_at,
            days_since_last_interaction=_days_since(stats.latest_activity_at),
        )

        try:
            await redis.set(cache_key, result.model_dump_json(), ex=_SUMMARY_TTL)
        except Exception:
            pass

        return result

    # ── get_customer_360 ──────────────────────────────────────────────────────

    async def get_customer_360(
        self,
        customer_id: uuid.UUID,
    ) -> Customer360Out:
        ctx = get_tenant_context()
        redis = get_redis()
        cache_key = _360_key(ctx.org_id, customer_id)

        try:
            cached = await redis.get(cache_key)
            if cached:
                return Customer360Out.model_validate_json(cached)
        except Exception:
            pass

        summary = await self.get_relationship_summary(customer_id)

        all_events = await self._repo.fetch_all_events(customer_id, ctx.org_id)
        all_events.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)
        recent = [_to_out(e) for e in all_events[:_RECENT_EVENTS_COUNT]]

        result = Customer360Out(
            customer_id=str(customer_id),
            summary=summary,
            recent_events=recent,
        )

        try:
            await redis.set(cache_key, result.model_dump_json(), ex=_360_TTL)
        except Exception:
            pass

        return result

    # ── cache invalidation ────────────────────────────────────────────────────

    async def bust_customer_cache(self, customer_id: uuid.UUID) -> None:
        ctx = get_tenant_context()
        redis = get_redis()
        try:
            await redis.delete(
                _timeline_key(ctx.org_id, customer_id),
                _summary_key(ctx.org_id, customer_id),
                _360_key(ctx.org_id, customer_id),
            )
        except Exception:
            pass
