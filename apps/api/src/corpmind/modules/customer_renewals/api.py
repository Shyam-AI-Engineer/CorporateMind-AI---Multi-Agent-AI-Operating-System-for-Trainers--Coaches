"""Customer Renewal REST API — Sprint 48."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
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
from corpmind.modules.customer_renewals.service import CustomerRenewalService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> CustomerRenewalService:
    return CustomerRenewalService(session)


@router.post("", response_model=CustomerRenewalOut, status_code=status.HTTP_201_CREATED)
async def create_renewal(
    body: CustomerRenewalCreate,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.create(body)


@router.get("", response_model=CustomerRenewalListOut)
async def list_renewals(
    workspace_id: uuid.UUID = Query(...),
    customer_id: uuid.UUID | None = Query(None),
    renewal_type: str | None = Query(None),
    renewal_status: str | None = Query(None),
    owner_user_id: uuid.UUID | None = Query(None),
    renewal_date_from: str | None = Query(None),
    renewal_date_to: str | None = Query(None),
    search: str | None = Query(None),
    include_archived: bool = Query(False),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalListOut:
    from datetime import date as _date

    def _parse_date(v: str | None) -> _date | None:
        return _date.fromisoformat(v) if v else None

    filters = CustomerRenewalFilters(
        workspace_id=workspace_id,
        customer_id=customer_id,
        renewal_type=renewal_type,
        renewal_status=renewal_status,
        owner_user_id=owner_user_id,
        renewal_date_from=_parse_date(renewal_date_from),
        renewal_date_to=_parse_date(renewal_date_to),
        search=search,
        include_archived=include_archived,
        cursor=cursor,
        limit=limit,
    )
    return await svc.list(filters)


@router.get("/{record_id}", response_model=CustomerRenewalOut)
async def get_renewal(
    record_id: uuid.UUID,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.get(record_id)


@router.patch("/{record_id}", response_model=CustomerRenewalOut)
async def update_renewal(
    record_id: uuid.UUID,
    body: CustomerRenewalUpdate,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.update(record_id, body)


@router.post("/{record_id}/assign-owner", response_model=CustomerRenewalOut)
async def assign_owner(
    record_id: uuid.UUID,
    body: AssignRenewalOwner,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.assign_owner(record_id, body)


@router.post("/{record_id}/update-status", response_model=CustomerRenewalOut)
async def update_status(
    record_id: uuid.UUID,
    body: UpdateRenewalStatus,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.update_status(record_id, body)


@router.post("/{record_id}/attach-proposal", response_model=CustomerRenewalOut)
async def attach_proposal(
    record_id: uuid.UUID,
    body: AttachProposal,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.attach_proposal(record_id, body)


@router.post("/{record_id}/archive", response_model=CustomerRenewalOut)
async def archive_renewal(
    record_id: uuid.UUID,
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalOut:
    return await svc.archive(record_id)


# Sub-router: customer-scoped renewal lookup
customer_renewal_router = APIRouter()


@customer_renewal_router.get(
    "/{customer_id}/renewals", response_model=CustomerRenewalListOut
)
async def get_renewals_by_customer(
    customer_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: CustomerRenewalService = Depends(_svc),
) -> CustomerRenewalListOut:
    from corpmind.modules.customer_renewals.schemas import CustomerRenewalFilters

    filters = CustomerRenewalFilters(
        workspace_id=workspace_id,
        customer_id=customer_id,
    )
    return await svc.list(filters)
