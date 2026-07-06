"""Customer Success service — Sprint 47."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.customer_success.events import (
    CustomerHealthChanged,
    CustomerSuccessCreated,
    CustomerSuccessUpdated,
    FollowupScheduled,
)
from corpmind.modules.customer_success.models import CustomerSuccess
from corpmind.modules.customer_success.repo import CustomerSuccessRepo, encode_cursor
from corpmind.modules.customer_success.schemas import (
    AssignOwner,
    CustomerSuccessCreate,
    CustomerSuccessFilters,
    CustomerSuccessListOut,
    CustomerSuccessOut,
    CustomerSuccessUpdate,
    ScheduleFollowup,
    UpdateHealth,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300
_DETAIL_TTL = 300


def _list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:customer_success:list"


def _detail_key(org_id: uuid.UUID, record_id: uuid.UUID) -> str:
    return f"t:{org_id}:customer_success:detail:{record_id}"


class CustomerSuccessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CustomerSuccessRepo(session)

    async def create(self, req: CustomerSuccessCreate) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        existing = await self._repo.find_by_customer_id(req.customer_id)
        if existing:
            raise ConflictError(
                f"Customer success record already exists for customer {req.customer_id}"
            )
        now = datetime.now(UTC)
        record = CustomerSuccess(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            health_status=req.health_status,
            health_score=req.health_score,
            risk_level=req.risk_level,
            owner_user_id=req.owner_user_id,
            renewal_date=req.renewal_date,
            last_contact_date=req.last_contact_date,
            next_followup_date=req.next_followup_date,
            expansion_opportunity=req.expansion_opportunity,
            renewal_probability=req.renewal_probability,
            notes=req.notes,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(record)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        log.info(
            "customer_success.created",
            record_id=str(record.id),
            customer_id=str(req.customer_id),
            tenant_id=str(ctx.org_id),
        )
        event = CustomerSuccessCreated(
            success_id=record.id,
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            health_status=record.health_status,
            risk_level=record.risk_level,
        )
        log.debug("customer_success.event", event_type=event.__class__.__name__)
        return CustomerSuccessOut.model_validate(record)

    async def get(self, record_id: uuid.UUID) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _detail_key(ctx.org_id, record_id)
        try:
            cached = await redis.get(key)
            if cached:
                return CustomerSuccessOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")

        out = CustomerSuccessOut.model_validate(record)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def get_by_customer(self, customer_id: uuid.UUID) -> CustomerSuccessOut:
        record = await self._repo.find_by_customer_id(customer_id)
        if not record:
            raise NotFoundError(f"No customer success record for customer {customer_id}")
        return CustomerSuccessOut.model_validate(record)

    async def update(
        self, record_id: uuid.UUID, req: CustomerSuccessUpdate
    ) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")

        changes: dict = {}
        if req.health_status is not None:
            changes["health_status"] = req.health_status
        if req.health_score is not None:
            changes["health_score"] = req.health_score
        if req.risk_level is not None:
            changes["risk_level"] = req.risk_level
        if req.renewal_date is not None:
            changes["renewal_date"] = req.renewal_date
        if req.last_contact_date is not None:
            changes["last_contact_date"] = req.last_contact_date
        if req.next_followup_date is not None:
            changes["next_followup_date"] = req.next_followup_date
        if req.expansion_opportunity is not None:
            changes["expansion_opportunity"] = req.expansion_opportunity
        if req.renewal_probability is not None:
            changes["renewal_probability"] = req.renewal_probability
        if req.notes is not None:
            changes["notes"] = req.notes
        changes["updated_at"] = datetime.now(UTC)

        await self._repo.update_fields(record_id, **changes)
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)

        log.info(
            "customer_success.updated",
            record_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        event = CustomerSuccessUpdated(
            success_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
        )
        log.debug("customer_success.event", event_type=event.__class__.__name__)
        return CustomerSuccessOut.model_validate(updated)

    async def list(self, filters: CustomerSuccessFilters) -> CustomerSuccessListOut:
        ctx = get_tenant_context()
        redis = get_redis()

        # Session-only cache for the default unfiltered page
        _is_default = (
            filters.health_status is None
            and filters.risk_level is None
            and filters.owner_user_id is None
            and filters.renewal_date_from is None
            and filters.renewal_date_to is None
            and filters.followup_due_by is None
            and filters.expansion_opportunity is None
            and filters.search is None
            and not filters.include_archived
            and filters.cursor is None
            and filters.limit == 50
        )
        if _is_default:
            key = _list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return CustomerSuccessListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            health_status=filters.health_status,
            risk_level=filters.risk_level,
            owner_user_id=filters.owner_user_id,
            renewal_date_from=filters.renewal_date_from,
            renewal_date_to=filters.renewal_date_to,
            followup_due_by=filters.followup_due_by,
            expansion_opportunity=filters.expansion_opportunity,
            search=filters.search,
            include_archived=filters.include_archived,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            health_status=filters.health_status,
            risk_level=filters.risk_level,
            owner_user_id=filters.owner_user_id,
            renewal_date_from=filters.renewal_date_from,
            renewal_date_to=filters.renewal_date_to,
            followup_due_by=filters.followup_due_by,
            expansion_opportunity=filters.expansion_opportunity,
            search=filters.search,
            include_archived=filters.include_archived,
            cursor=filters.cursor,
            limit=filters.limit,
        )
        has_more = len(rows) > filters.limit
        page = rows[: filters.limit]
        next_cursor = (
            encode_cursor(page[-1].created_at, page[-1].id) if has_more else None
        )

        out = CustomerSuccessListOut(
            items=[CustomerSuccessOut.model_validate(r) for r in page],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )

        if _is_default:
            try:
                await redis.set(key, out.model_dump_json(), ex=_LIST_TTL)
            except Exception:
                pass
        return out

    async def assign_owner(
        self, record_id: uuid.UUID, req: AssignOwner
    ) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")

        await self._repo.update_fields(
            record_id,
            owner_user_id=req.owner_user_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        log.info(
            "customer_success.owner_assigned",
            record_id=str(record_id),
            owner_user_id=str(req.owner_user_id),
            tenant_id=str(ctx.org_id),
        )
        return CustomerSuccessOut.model_validate(updated)

    async def update_health(
        self, record_id: uuid.UUID, req: UpdateHealth
    ) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")

        previous_health = record.health_status
        await self._repo.update_fields(
            record_id,
            health_status=req.health_status,
            health_score=req.health_score,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)

        if previous_health != req.health_status:
            event = CustomerHealthChanged(
                success_id=record_id,
                tenant_id=ctx.org_id,
                customer_id=updated.customer_id,
                previous_health=previous_health,
                new_health=req.health_status,
                health_score=req.health_score,
            )
            log.info(
                "customer_success.health_changed",
                record_id=str(record_id),
                previous=previous_health,
                new=req.health_status,
                tenant_id=str(ctx.org_id),
            )
            log.debug("customer_success.event", event_type=event.__class__.__name__)
        return CustomerSuccessOut.model_validate(updated)

    async def schedule_followup(
        self, record_id: uuid.UUID, req: ScheduleFollowup
    ) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")

        await self._repo.update_fields(
            record_id,
            next_followup_date=req.next_followup_date,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)

        event = FollowupScheduled(
            success_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
            next_followup_date=req.next_followup_date.isoformat(),
        )
        log.info(
            "customer_success.followup_scheduled",
            record_id=str(record_id),
            next_followup_date=req.next_followup_date.isoformat(),
            tenant_id=str(ctx.org_id),
        )
        log.debug("customer_success.event", event_type=event.__class__.__name__)
        return CustomerSuccessOut.model_validate(updated)

    async def archive(self, record_id: uuid.UUID) -> CustomerSuccessOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer success record {record_id} not found")
        if record.is_archived:
            raise ValidationError("Customer success record is already archived")

        await self._repo.update_fields(
            record_id,
            is_archived=True,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)
        log.info(
            "customer_success.archived",
            record_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        return CustomerSuccessOut.model_validate(updated)

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _bust_detail_cache(self, org_id: uuid.UUID, record_id: uuid.UUID) -> None:
        redis = get_redis()
        try:
            await redis.delete(_detail_key(org_id, record_id))
        except Exception:
            pass

    async def _bust_list_cache(self, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
        redis = get_redis()
        try:
            await redis.delete(_list_key(org_id, ws_id))
        except Exception:
            pass
