"""Training Engagement REST API — Sprint 42."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.training.schemas import (
    CancelEngagement,
    CompleteEngagement,
    CoordinatorAssign,
    TrainerAssign,
    TrainingEngagementCreate,
    TrainingEngagementFilters,
    TrainingEngagementListOut,
    TrainingEngagementOut,
    TrainingEngagementUpdate,
)
from corpmind.modules.training.service import TrainingEngagementService

router = APIRouter()


@router.post(
    "/",
    response_model=TrainingEngagementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training engagement",
)
async def create_engagement(
    req: TrainingEngagementCreate,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).create_engagement(req)


@router.get(
    "/",
    response_model=TrainingEngagementListOut,
    summary="List training engagements (cursor-paginated)",
)
async def list_engagements(
    workspace_id: uuid.UUID = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    trainer_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    delivery_mode: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementListOut:
    filters = TrainingEngagementFilters(
        workspace_id=workspace_id,
        status=status_filter,
        trainer_id=trainer_id,
        customer_id=customer_id,
        delivery_mode=delivery_mode,
        date_from=date_from,
        date_to=date_to,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await TrainingEngagementService(session).list_engagements(filters)


@router.get(
    "/{engagement_id}",
    response_model=TrainingEngagementOut,
    summary="Get a training engagement by ID",
)
async def get_engagement(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).get_engagement(engagement_id)


@router.patch(
    "/{engagement_id}",
    response_model=TrainingEngagementOut,
    summary="Update training engagement fields",
)
async def update_engagement(
    engagement_id: uuid.UUID,
    req: TrainingEngagementUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).update_engagement(engagement_id, req)


@router.post(
    "/{engagement_id}/start",
    response_model=TrainingEngagementOut,
    summary="Start a training engagement",
)
async def start_engagement(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).start_engagement(engagement_id)


@router.post(
    "/{engagement_id}/complete",
    response_model=TrainingEngagementOut,
    summary="Complete a training engagement",
)
async def complete_engagement(
    engagement_id: uuid.UUID,
    req: CompleteEngagement,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).complete_engagement(engagement_id, req)


@router.post(
    "/{engagement_id}/cancel",
    response_model=TrainingEngagementOut,
    summary="Cancel a training engagement",
)
async def cancel_engagement(
    engagement_id: uuid.UUID,
    req: CancelEngagement,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).cancel_engagement(engagement_id, req)


@router.post(
    "/{engagement_id}/assign-trainer",
    response_model=TrainingEngagementOut,
    summary="Assign a trainer to a training engagement",
)
async def assign_trainer(
    engagement_id: uuid.UUID,
    req: TrainerAssign,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).assign_trainer(
        engagement_id, req.assigned_trainer_id
    )


@router.post(
    "/{engagement_id}/assign-coordinator",
    response_model=TrainingEngagementOut,
    summary="Assign a coordinator to a training engagement",
)
async def assign_coordinator(
    engagement_id: uuid.UUID,
    req: CoordinatorAssign,
    session: AsyncSession = Depends(get_session),
) -> TrainingEngagementOut:
    return await TrainingEngagementService(session).assign_coordinator(
        engagement_id, req.coordinator_id
    )
