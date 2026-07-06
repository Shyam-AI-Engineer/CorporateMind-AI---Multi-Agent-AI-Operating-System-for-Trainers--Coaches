"""Customer Success REST API — Sprint 47."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
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
from corpmind.modules.customer_success.service import CustomerSuccessService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> CustomerSuccessService:
    return CustomerSuccessService(session)


@router.post("", response_model=CustomerSuccessOut, status_code=status.HTTP_201_CREATED)
async def create_success_record(
    body: CustomerSuccessCreate,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.create(body)


@router.get("", response_model=CustomerSuccessListOut)
async def list_success_records(
    workspace_id: uuid.UUID = Query(...),
    health_status: str | None = Query(None),
    risk_level: str | None = Query(None),
    owner_user_id: uuid.UUID | None = Query(None),
    renewal_date_from: str | None = Query(None),
    renewal_date_to: str | None = Query(None),
    followup_due_by: str | None = Query(None),
    expansion_opportunity: bool | None = Query(None),
    search: str | None = Query(None),
    include_archived: bool = Query(False),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessListOut:
    from datetime import date as _date

    def _parse_date(v: str | None) -> _date | None:
        return _date.fromisoformat(v) if v else None

    filters = CustomerSuccessFilters(
        workspace_id=workspace_id,
        health_status=health_status,
        risk_level=risk_level,
        owner_user_id=owner_user_id,
        renewal_date_from=_parse_date(renewal_date_from),
        renewal_date_to=_parse_date(renewal_date_to),
        followup_due_by=_parse_date(followup_due_by),
        expansion_opportunity=expansion_opportunity,
        search=search,
        include_archived=include_archived,
        cursor=cursor,
        limit=limit,
    )
    return await svc.list(filters)


@router.get("/{record_id}", response_model=CustomerSuccessOut)
async def get_success_record(
    record_id: uuid.UUID,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.get(record_id)


@router.patch("/{record_id}", response_model=CustomerSuccessOut)
async def update_success_record(
    record_id: uuid.UUID,
    body: CustomerSuccessUpdate,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.update(record_id, body)


@router.post("/{record_id}/assign-owner", response_model=CustomerSuccessOut)
async def assign_owner(
    record_id: uuid.UUID,
    body: AssignOwner,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.assign_owner(record_id, body)


@router.post("/{record_id}/update-health", response_model=CustomerSuccessOut)
async def update_health(
    record_id: uuid.UUID,
    body: UpdateHealth,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.update_health(record_id, body)


@router.post("/{record_id}/schedule-followup", response_model=CustomerSuccessOut)
async def schedule_followup(
    record_id: uuid.UUID,
    body: ScheduleFollowup,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.schedule_followup(record_id, body)


@router.post("/{record_id}/archive", response_model=CustomerSuccessOut)
async def archive_success_record(
    record_id: uuid.UUID,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.archive(record_id)


# Sub-router: customer-scoped lookup
customer_success_router = APIRouter()


@customer_success_router.get(
    "/{customer_id}/success", response_model=CustomerSuccessOut
)
async def get_success_by_customer(
    customer_id: uuid.UUID,
    svc: CustomerSuccessService = Depends(_svc),
) -> CustomerSuccessOut:
    return await svc.get_by_customer(customer_id)
