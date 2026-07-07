"""Customer 360 Timeline REST API — Sprint 49.

Read-only endpoints. No writes. No mutations.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.customer_success.timeline_schemas import (
    Customer360Out,
    CustomerRelationshipSummaryOut,
    CustomerTimelinePageOut,
)
from corpmind.modules.customer_success.timeline_service import CustomerTimelineService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> CustomerTimelineService:
    return CustomerTimelineService(session)


@router.get("/customer-360/{customer_id}", response_model=Customer360Out)
async def get_customer_360(
    customer_id: uuid.UUID,
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    svc: CustomerTimelineService = Depends(_svc),
) -> Customer360Out:
    return await svc.get_customer_360(customer_id)


@router.get("/customer-timeline/{customer_id}", response_model=CustomerTimelinePageOut)
async def get_customer_timeline(
    customer_id: uuid.UUID,
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    event_type: Annotated[list[str] | None, Query()] = None,
    svc: CustomerTimelineService = Depends(_svc),
) -> CustomerTimelinePageOut:
    return await svc.get_timeline(
        customer_id,
        cursor=cursor,
        limit=limit,
        event_types=event_type,
    )


@router.get(
    "/customer-relationship-summary/{customer_id}",
    response_model=CustomerRelationshipSummaryOut,
)
async def get_customer_relationship_summary(
    customer_id: uuid.UUID,
    workspace_id: Annotated[uuid.UUID, Query(..., description="Workspace context")],
    svc: CustomerTimelineService = Depends(_svc),
) -> CustomerRelationshipSummaryOut:
    return await svc.get_relationship_summary(customer_id)
