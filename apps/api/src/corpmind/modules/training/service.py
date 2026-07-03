"""TrainingEngagementService — business logic for Sprint 42."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.training.models import TrainingEngagement
from corpmind.modules.training.repo import TrainingEngagementRepo, encode_cursor
from corpmind.modules.training.schemas import (
    CompleteEngagement,
    CancelEngagement,
    TrainingEngagementCreate,
    TrainingEngagementFilters,
    TrainingEngagementListOut,
    TrainingEngagementOut,
    TrainingEngagementUpdate,
    VALID_STATUSES,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300
_DETAIL_TTL = 300

# Valid status transitions
_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"scheduled", "in_progress", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:training:list"


def _detail_key(org_id: uuid.UUID, engagement_id: uuid.UUID) -> str:
    return f"t:{org_id}:training:detail:{engagement_id}"


class TrainingEngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrainingEngagementRepo(session)

    async def create_engagement(self, req: TrainingEngagementCreate) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        engagement = TrainingEngagement(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            program_name=req.program_name,
            description=req.description,
            training_type=req.training_type,
            delivery_mode=req.delivery_mode,
            status=req.status,
            priority=req.priority,
            planned_start_date=req.planned_start_date,
            planned_end_date=req.planned_end_date,
            actual_start_date=None,
            actual_end_date=None,
            estimated_participants=req.estimated_participants,
            actual_participants=None,
            assigned_trainer_id=req.assigned_trainer_id,
            coordinator_id=req.coordinator_id,
            location=req.location,
            meeting_link=req.meeting_link,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(engagement)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        log.info(
            "training.created",
            engagement_id=str(engagement.id),
            tenant_id=str(ctx.org_id),
        )
        return TrainingEngagementOut.model_validate(engagement)

    async def get_engagement(self, engagement_id: uuid.UUID) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _detail_key(ctx.org_id, engagement_id)
        try:
            cached = await redis.get(key)
            if cached:
                return TrainingEngagementOut.model_validate_json(cached)
        except Exception:
            pass

        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        out = TrainingEngagementOut.model_validate(engagement)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_engagement(
        self, engagement_id: uuid.UUID, req: TrainingEngagementUpdate
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field_name, value in req.model_dump(exclude_none=True).items():
            fields[field_name] = value
        await self._repo.update_fields(engagement_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def _transition_status(
        self,
        engagement_id: uuid.UUID,
        target_status: str,
        extra_fields: dict | None = None,
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        allowed = _TRANSITIONS.get(engagement.status, set())
        if target_status not in allowed:
            raise ValidationError(
                f"Cannot transition from '{engagement.status}' to '{target_status}'"
            )

        fields: dict = {"status": target_status, "updated_at": datetime.now(UTC)}
        if extra_fields:
            fields.update(extra_fields)
        await self._repo.update_fields(engagement_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def start_engagement(self, engagement_id: uuid.UUID) -> TrainingEngagementOut:
        return await self._transition_status(
            engagement_id,
            "in_progress",
            {"actual_start_date": datetime.now(UTC).date()},
        )

    async def complete_engagement(
        self, engagement_id: uuid.UUID, req: CompleteEngagement
    ) -> TrainingEngagementOut:
        extra: dict = {}
        if req.actual_end_date:
            extra["actual_end_date"] = req.actual_end_date
        else:
            extra["actual_end_date"] = datetime.now(UTC).date()
        if req.actual_participants is not None:
            extra["actual_participants"] = req.actual_participants
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(engagement_id, "completed", extra)

    async def cancel_engagement(
        self, engagement_id: uuid.UUID, req: CancelEngagement
    ) -> TrainingEngagementOut:
        extra: dict = {}
        if req.notes is not None:
            extra["notes"] = req.notes
        return await self._transition_status(engagement_id, "cancelled", extra)

    async def assign_trainer(
        self, engagement_id: uuid.UUID, trainer_id: uuid.UUID
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        await self._repo.update_fields(
            engagement_id,
            assigned_trainer_id=trainer_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        log.info(
            "training.trainer_assigned",
            engagement_id=str(engagement_id),
            trainer_id=str(trainer_id),
        )
        return await self.get_engagement(engagement_id)

    async def assign_coordinator(
        self, engagement_id: uuid.UUID, coordinator_id: uuid.UUID
    ) -> TrainingEngagementOut:
        ctx = get_tenant_context()
        engagement = await self._repo.find_by_id(engagement_id)
        if not engagement:
            raise NotFoundError(f"Training engagement {engagement_id} not found")

        await self._repo.update_fields(
            engagement_id,
            coordinator_id=coordinator_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, engagement.workspace_id)
        await self._bust_detail_cache(ctx.org_id, engagement_id)
        return await self.get_engagement(engagement_id)

    async def list_engagements(
        self, filters: TrainingEngagementFilters
    ) -> TrainingEngagementListOut:
        ctx = get_tenant_context()
        is_default_query = not any([
            filters.status,
            filters.trainer_id,
            filters.customer_id,
            filters.delivery_mode,
            filters.date_from,
            filters.date_to,
            filters.search,
            filters.cursor,
        ]) and filters.limit == 50

        if is_default_query:
            redis = get_redis()
            key = _list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return TrainingEngagementListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            status=filters.status,
            trainer_id=filters.trainer_id,
            customer_id=filters.customer_id,
            delivery_mode=filters.delivery_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            status=filters.status,
            trainer_id=filters.trainer_id,
            customer_id=filters.customer_id,
            delivery_mode=filters.delivery_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = TrainingEngagementListOut(
            items=[TrainingEngagementOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_default_query:
            redis = get_redis()
            try:
                await redis.set(_list_key(ctx.org_id, filters.workspace_id), out.model_dump_json(), ex=_LIST_TTL)
            except Exception:
                pass
        return out

    async def search_engagements(
        self, workspace_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[TrainingEngagementOut]:
        filters = TrainingEngagementFilters(
            workspace_id=workspace_id, search=query, limit=limit
        )
        result = await self.list_engagements(filters)
        return result.items

    async def _bust_list_cache(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_list_key(org_id, workspace_id))
        except Exception:
            pass

    async def _bust_detail_cache(self, org_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_detail_key(org_id, engagement_id))
        except Exception:
            pass
