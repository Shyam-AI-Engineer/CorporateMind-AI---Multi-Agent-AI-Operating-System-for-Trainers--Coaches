"""CustomerService — all business logic for the Customer Account module (Sprint 41)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.customers.models import Customer
from corpmind.modules.customers.repo import CustomerRepo, encode_cursor
from corpmind.modules.customers.schemas import (
    CustomerCreate,
    CustomerFilters,
    CustomerListOut,
    CustomerOut,
    CustomerUpdate,
    VALID_HEALTH_STATUSES,
    VALID_STATUSES,
)

log = structlog.get_logger(__name__)

_LIST_TTL = 300
_DETAIL_TTL = 300


def _list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:customers:list"


def _detail_key(org_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    return f"t:{org_id}:customers:detail:{customer_id}"


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CustomerRepo(session)

    async def create_customer(self, req: CustomerCreate) -> CustomerOut:
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        customer = Customer(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            company_name=req.company_name,
            display_name=req.display_name,
            industry=req.industry,
            website=req.website,
            email=req.email,
            phone=req.phone,
            address=req.address,
            city=req.city,
            state=req.state,
            country=req.country,
            postal_code=req.postal_code,
            company_size=req.company_size,
            annual_revenue_inr=req.annual_revenue_inr,
            status=req.status,
            health_status=req.health_status,
            relationship_owner_id=req.relationship_owner_id,
            primary_contact_name=req.primary_contact_name,
            primary_contact_email=req.primary_contact_email,
            primary_contact_phone=req.primary_contact_phone,
            notes=req.notes,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(customer)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, req.workspace_id)
        log.info("customer.created", customer_id=str(customer.id), tenant_id=str(ctx.org_id))
        return CustomerOut.model_validate(customer)

    async def get_customer(self, customer_id: uuid.UUID) -> CustomerOut:
        ctx = get_tenant_context()
        redis = get_redis()
        key = _detail_key(ctx.org_id, customer_id)
        try:
            cached = await redis.get(key)
            if cached:
                return CustomerOut.model_validate_json(cached)
        except Exception:
            pass

        customer = await self._repo.find_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")

        out = CustomerOut.model_validate(customer)
        try:
            await redis.set(key, out.model_dump_json(), ex=_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def update_customer(self, customer_id: uuid.UUID, req: CustomerUpdate) -> CustomerOut:
        ctx = get_tenant_context()
        customer = await self._repo.find_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")

        fields: dict = {"updated_at": datetime.now(UTC)}
        for field, value in req.model_dump(exclude_none=True).items():
            fields[field] = value
        await self._repo.update_fields(customer_id, **fields)
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, customer.workspace_id)
        await self._bust_detail_cache(ctx.org_id, customer_id)
        return await self.get_customer(customer_id)

    async def archive_customer(self, customer_id: uuid.UUID) -> CustomerOut:
        ctx = get_tenant_context()
        customer = await self._repo.find_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")

        await self._repo.update_fields(
            customer_id, status="archived", updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, customer.workspace_id)
        await self._bust_detail_cache(ctx.org_id, customer_id)
        log.info("customer.archived", customer_id=str(customer_id), tenant_id=str(ctx.org_id))
        return await self.get_customer(customer_id)

    async def change_health(self, customer_id: uuid.UUID, health_status: str) -> CustomerOut:
        if health_status not in VALID_HEALTH_STATUSES:
            raise ValidationError(f"Invalid health_status: {health_status}")
        ctx = get_tenant_context()
        customer = await self._repo.find_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")

        await self._repo.update_fields(
            customer_id, health_status=health_status, updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, customer.workspace_id)
        await self._bust_detail_cache(ctx.org_id, customer_id)
        return await self.get_customer(customer_id)

    async def assign_owner(self, customer_id: uuid.UUID, owner_id: uuid.UUID) -> CustomerOut:
        ctx = get_tenant_context()
        customer = await self._repo.find_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer {customer_id} not found")

        await self._repo.update_fields(
            customer_id, relationship_owner_id=owner_id, updated_at=datetime.now(UTC)
        )
        await self._session.commit()
        await self._bust_list_cache(ctx.org_id, customer.workspace_id)
        await self._bust_detail_cache(ctx.org_id, customer_id)
        return await self.get_customer(customer_id)

    async def list_customers(self, filters: CustomerFilters) -> CustomerListOut:
        ctx = get_tenant_context()
        is_default_query = not any([
            filters.status, filters.industry, filters.health_status,
            filters.owner_id, filters.search, filters.cursor,
        ]) and filters.limit == 50

        if is_default_query:
            redis = get_redis()
            key = _list_key(ctx.org_id, filters.workspace_id)
            try:
                cached = await redis.get(key)
                if cached:
                    return CustomerListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            status=filters.status,
            industry=filters.industry,
            health_status=filters.health_status,
            owner_id=filters.owner_id,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            status=filters.status,
            industry=filters.industry,
            health_status=filters.health_status,
            owner_id=filters.owner_id,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        next_cursor = None
        if len(rows) == filters.limit:
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)

        out = CustomerListOut(
            items=[CustomerOut.model_validate(r) for r in rows],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total=total,
        )

        if is_default_query:
            try:
                await redis.set(key, out.model_dump_json(), ex=_LIST_TTL)
            except Exception:
                pass
        return out

    async def search_customers(
        self, workspace_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[CustomerOut]:
        filters = CustomerFilters(workspace_id=workspace_id, search=query, limit=limit)
        result = await self.list_customers(filters)
        return result.items

    async def _bust_list_cache(self, org_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_list_key(org_id, workspace_id))
        except Exception:
            pass

    async def _bust_detail_cache(self, org_id: uuid.UUID, customer_id: uuid.UUID) -> None:
        try:
            redis = get_redis()
            await redis.delete(_detail_key(org_id, customer_id))
        except Exception:
            pass
