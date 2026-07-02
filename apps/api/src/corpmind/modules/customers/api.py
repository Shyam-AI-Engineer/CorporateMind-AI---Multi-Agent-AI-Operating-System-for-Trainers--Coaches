"""Customer module REST API — Sprint 41."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.customers.schemas import (
    CustomerCreate,
    CustomerFilters,
    CustomerHealthUpdate,
    CustomerListOut,
    CustomerOut,
    CustomerOwnerAssign,
    CustomerUpdate,
)
from corpmind.modules.customers.service import CustomerService

router = APIRouter()


@router.post(
    "/",
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer account",
)
async def create_customer(
    req: CustomerCreate,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).create_customer(req)


@router.get(
    "/",
    response_model=CustomerListOut,
    summary="List customers (cursor-paginated)",
)
async def list_customers(
    workspace_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    industry: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> CustomerListOut:
    filters = CustomerFilters(
        workspace_id=workspace_id,
        status=status_filter,
        industry=industry,
        health_status=health_status,
        owner_id=owner_id,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await CustomerService(session).list_customers(filters)


@router.get(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Get a customer by ID",
)
async def get_customer(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).get_customer(customer_id)


@router.patch(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Update customer fields",
)
async def update_customer(
    customer_id: uuid.UUID,
    req: CustomerUpdate,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).update_customer(customer_id, req)


@router.delete(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="Archive (soft-delete) a customer",
)
async def archive_customer(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).archive_customer(customer_id)


@router.post(
    "/{customer_id}/assign-owner",
    response_model=CustomerOut,
    summary="Assign relationship owner to a customer",
)
async def assign_owner(
    customer_id: uuid.UUID,
    req: CustomerOwnerAssign,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).assign_owner(customer_id, req.relationship_owner_id)


@router.post(
    "/{customer_id}/health",
    response_model=CustomerOut,
    summary="Update customer health status",
)
async def update_health(
    customer_id: uuid.UUID,
    req: CustomerHealthUpdate,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    return await CustomerService(session).change_health(customer_id, req.health_status)
