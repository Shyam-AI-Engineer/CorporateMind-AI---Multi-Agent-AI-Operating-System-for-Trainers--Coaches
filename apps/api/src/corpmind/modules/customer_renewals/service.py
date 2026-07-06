"""Customer Renewal service — Sprint 48."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.customer_renewals.events import (
    RenewalCreated,
    RenewalProposalAttached,
    RenewalStatusChanged,
    RenewalUpdated,
)
from corpmind.modules.customer_renewals.models import CustomerRenewal
from corpmind.modules.customer_renewals.repo import CustomerRenewalRepo, encode_cursor
from corpmind.modules.customer_renewals.schemas import (
    AssignRenewalOwner,
    AttachProposal,
    CustomerRenewalCreate,
    CustomerRenewalFilters,
    CustomerRenewalListOut,
    CustomerRenewalOut,
    CustomerRenewalUpdate,
    UpdateRenewalStatus,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300
_DETAIL_TTL = 300


def _list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:customer_renewals:list"


def _detail_key(org_id: uuid.UUID, record_id: uuid.UUID) -> str:
    return f"t:{org_id}:customer_renewals:detail:{record_id}"


class CustomerRenewalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CustomerRenewalRepo(session)

    async def create(self, req: CustomerRenewalCreate) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        record = CustomerRenewal(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            contract_name=req.contract_name,
            contract_value=req.contract_value,
            renewal_type=req.renewal_type,
            renewal_status=req.renewal_status,
            renewal_date=req.renewal_date,
            owner_user_id=req.owner_user_id,
            probability=req.probability,
            expected_value=req.expected_value,
            proposal_id=req.proposal_id,
            notes=req.notes,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(record)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        log.info(
            "customer_renewal.created",
            record_id=str(record.id),
            customer_id=str(req.customer_id),
            tenant_id=str(ctx.org_id),
        )
        event = RenewalCreated(
            renewal_id=record.id,
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            customer_id=req.customer_id,
            renewal_type=record.renewal_type,
            renewal_status=record.renewal_status,
        )
        log.debug("customer_renewal.event", event_type=event.__class__.__name__)
        return CustomerRenewalOut.model_validate(record)

    async def get(self, record_id: uuid.UUID) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _detail_key(ctx.org_id, record_id)
        try:
            cached = await redis.get(key)
            if cached:
                return CustomerRenewalOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")

        out = CustomerRenewalOut.model_validate(record)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update(
        self, record_id: uuid.UUID, req: CustomerRenewalUpdate
    ) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")

        changes: dict = {}
        if req.contract_name is not None:
            changes["contract_name"] = req.contract_name
        if req.contract_value is not None:
            changes["contract_value"] = req.contract_value
        if req.renewal_type is not None:
            changes["renewal_type"] = req.renewal_type
        if req.renewal_date is not None:
            changes["renewal_date"] = req.renewal_date
        if req.owner_user_id is not None:
            changes["owner_user_id"] = req.owner_user_id
        if req.probability is not None:
            changes["probability"] = req.probability
        if req.expected_value is not None:
            changes["expected_value"] = req.expected_value
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
            "customer_renewal.updated",
            record_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        event = RenewalUpdated(
            renewal_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
        )
        log.debug("customer_renewal.event", event_type=event.__class__.__name__)
        return CustomerRenewalOut.model_validate(updated)

    async def list(
        self, filters: CustomerRenewalFilters
    ) -> CustomerRenewalListOut:
        ctx = get_tenant_context()
        redis = get_redis()

        _is_default = (
            filters.customer_id is None
            and filters.renewal_type is None
            and filters.renewal_status is None
            and filters.owner_user_id is None
            and filters.renewal_date_from is None
            and filters.renewal_date_to is None
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
                    return CustomerRenewalListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            customer_id=filters.customer_id,
            renewal_type=filters.renewal_type,
            renewal_status=filters.renewal_status,
            owner_user_id=filters.owner_user_id,
            renewal_date_from=filters.renewal_date_from,
            renewal_date_to=filters.renewal_date_to,
            search=filters.search,
            include_archived=filters.include_archived,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            customer_id=filters.customer_id,
            renewal_type=filters.renewal_type,
            renewal_status=filters.renewal_status,
            owner_user_id=filters.owner_user_id,
            renewal_date_from=filters.renewal_date_from,
            renewal_date_to=filters.renewal_date_to,
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

        out = CustomerRenewalListOut(
            items=[CustomerRenewalOut.model_validate(r) for r in page],
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
        self, record_id: uuid.UUID, req: AssignRenewalOwner
    ) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")

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
            "customer_renewal.owner_assigned",
            record_id=str(record_id),
            owner_user_id=str(req.owner_user_id),
            tenant_id=str(ctx.org_id),
        )
        return CustomerRenewalOut.model_validate(updated)

    async def update_status(
        self, record_id: uuid.UUID, req: UpdateRenewalStatus
    ) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")

        previous_status = record.renewal_status
        await self._repo.update_fields(
            record_id,
            renewal_status=req.renewal_status,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)

        if previous_status != req.renewal_status:
            event = RenewalStatusChanged(
                renewal_id=record_id,
                tenant_id=ctx.org_id,
                customer_id=updated.customer_id,
                previous_status=previous_status,
                new_status=req.renewal_status,
            )
            log.info(
                "customer_renewal.status_changed",
                record_id=str(record_id),
                previous=previous_status,
                new=req.renewal_status,
                tenant_id=str(ctx.org_id),
            )
            log.debug("customer_renewal.event", event_type=event.__class__.__name__)
        return CustomerRenewalOut.model_validate(updated)

    async def attach_proposal(
        self, record_id: uuid.UUID, req: AttachProposal
    ) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")

        await self._repo.update_fields(
            record_id,
            proposal_id=req.proposal_id,
            updated_at=datetime.now(UTC),
        )
        await self._session.commit()
        updated = await self._repo.find_by_id(record_id)
        assert updated is not None

        await self._bust_detail_cache(ctx.org_id, record_id)
        await self._bust_list_cache(ctx.org_id, updated.workspace_id)

        event = RenewalProposalAttached(
            renewal_id=record_id,
            tenant_id=ctx.org_id,
            customer_id=updated.customer_id,
            proposal_id=req.proposal_id,
        )
        log.info(
            "customer_renewal.proposal_attached",
            record_id=str(record_id),
            proposal_id=str(req.proposal_id),
            tenant_id=str(ctx.org_id),
        )
        log.debug("customer_renewal.event", event_type=event.__class__.__name__)
        return CustomerRenewalOut.model_validate(updated)

    async def archive(self, record_id: uuid.UUID) -> CustomerRenewalOut:
        ctx = get_tenant_context()
        record = await self._repo.find_by_id(record_id)
        if not record:
            raise NotFoundError(f"Customer renewal {record_id} not found")
        if record.is_archived:
            raise ValidationError("Customer renewal is already archived")

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
            "customer_renewal.archived",
            record_id=str(record_id),
            tenant_id=str(ctx.org_id),
        )
        return CustomerRenewalOut.model_validate(updated)

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _bust_detail_cache(
        self, org_id: uuid.UUID, record_id: uuid.UUID
    ) -> None:
        redis = get_redis()
        try:
            await redis.delete(_detail_key(org_id, record_id))
        except Exception:
            pass

    async def _bust_list_cache(
        self, org_id: uuid.UUID, ws_id: uuid.UUID
    ) -> None:
        redis = get_redis()
        try:
            await redis.delete(_list_key(org_id, ws_id))
        except Exception:
            pass
