"""Training Engagement, Session, and Attendance REST API — Sprint 42/43/44."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.training.schemas import (
    CancelEngagement,
    CancelSession,
    CheckOutAttendance,
    CompleteEngagement,
    CompleteSession,
    CoordinatorAssign,
    SessionTrainerAssign,
    TrainerAssign,
    TrainingAttendanceCreate,
    TrainingAttendanceFilters,
    TrainingAttendanceListOut,
    TrainingAttendanceOut,
    TrainingAttendanceUpdate,
    TrainingEngagementCreate,
    TrainingEngagementFilters,
    TrainingEngagementListOut,
    TrainingEngagementOut,
    TrainingEngagementUpdate,
    TrainingSessionCreate,
    TrainingSessionFilters,
    TrainingSessionListOut,
    TrainingSessionOut,
    TrainingSessionUpdate,
)
from corpmind.modules.training.service import (
    TrainingAttendanceService,
    TrainingEngagementService,
    TrainingSessionService,
)

router = APIRouter()
sessions_router = APIRouter()
attendance_router = APIRouter()


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


@router.get(
    "/{engagement_id}/sessions",
    response_model=list[TrainingSessionOut],
    summary="List all sessions for an engagement (ordered by session_number / scheduled_start)",
)
async def list_sessions_for_engagement(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[TrainingSessionOut]:
    return await TrainingSessionService(session).list_by_engagement(engagement_id)


# ── Training Session endpoints ─────────────────────────────────────────────────

@sessions_router.post(
    "/",
    response_model=TrainingSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training session",
)
async def create_session(
    req: TrainingSessionCreate,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).create_session(req)


@sessions_router.get(
    "/",
    response_model=TrainingSessionListOut,
    summary="List training sessions (cursor-paginated)",
)
async def list_sessions(
    workspace_id: uuid.UUID = Query(...),
    engagement_id: uuid.UUID | None = Query(default=None),
    trainer_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionListOut:
    filters = TrainingSessionFilters(
        workspace_id=workspace_id,
        engagement_id=engagement_id,
        trainer_id=trainer_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
        limit=limit,
    )
    return await TrainingSessionService(session).list_sessions(filters)


@sessions_router.get(
    "/{session_id}",
    response_model=TrainingSessionOut,
    summary="Get a training session by ID",
)
async def get_session(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).get_session(session_id)


@sessions_router.patch(
    "/{session_id}",
    response_model=TrainingSessionOut,
    summary="Update training session fields",
)
async def update_session(
    session_id: uuid.UUID,
    req: TrainingSessionUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).update_session(session_id, req)


@sessions_router.post(
    "/{session_id}/start",
    response_model=TrainingSessionOut,
    summary="Start a training session",
)
async def start_session(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).start_session(session_id)


@sessions_router.post(
    "/{session_id}/complete",
    response_model=TrainingSessionOut,
    summary="Complete a training session",
)
async def complete_session(
    session_id: uuid.UUID,
    req: CompleteSession,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).complete_session(session_id, req)


@sessions_router.post(
    "/{session_id}/cancel",
    response_model=TrainingSessionOut,
    summary="Cancel a training session",
)
async def cancel_session(
    session_id: uuid.UUID,
    req: CancelSession,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).cancel_session(session_id, req)


@sessions_router.post(
    "/{session_id}/assign-trainer",
    response_model=TrainingSessionOut,
    summary="Assign a trainer to a training session",
)
async def assign_trainer_to_session(
    session_id: uuid.UUID,
    req: SessionTrainerAssign,
    session: AsyncSession = Depends(get_session),
) -> TrainingSessionOut:
    return await TrainingSessionService(session).assign_trainer(session_id, req.trainer_id)


@sessions_router.get(
    "/{session_id}/attendance",
    response_model=list[TrainingAttendanceOut],
    summary="List all attendance records for a session",
)
async def list_session_attendance(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[TrainingAttendanceOut]:
    return await TrainingAttendanceService(session).list_by_session(session_id)


# ── Attendance endpoints ───────────────────────────────────────────────────────

@attendance_router.post(
    "/",
    response_model=TrainingAttendanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a participant for a session",
)
async def register_participant(
    req: TrainingAttendanceCreate,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).register_participant(req)


@attendance_router.get(
    "/",
    response_model=TrainingAttendanceListOut,
    summary="List attendance records (cursor-paginated)",
)
async def list_attendance(
    workspace_id: uuid.UUID = Query(...),
    session_id: uuid.UUID | None = Query(default=None),
    attendance_status: str | None = Query(default=None),
    company: str | None = Query(default=None),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceListOut:
    filters = TrainingAttendanceFilters(
        workspace_id=workspace_id,
        session_id=session_id,
        attendance_status=attendance_status,
        company=company,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await TrainingAttendanceService(session).list_attendance(filters)


@attendance_router.get(
    "/{attendance_id}",
    response_model=TrainingAttendanceOut,
    summary="Get an attendance record by ID",
)
async def get_participant(
    attendance_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).get_participant(attendance_id)


@attendance_router.patch(
    "/{attendance_id}",
    response_model=TrainingAttendanceOut,
    summary="Update participant details",
)
async def update_participant(
    attendance_id: uuid.UUID,
    req: TrainingAttendanceUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).update_participant(attendance_id, req)


@attendance_router.post(
    "/{attendance_id}/present",
    response_model=TrainingAttendanceOut,
    summary="Mark participant as present",
)
async def mark_present(
    attendance_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).mark_present(attendance_id)


@attendance_router.post(
    "/{attendance_id}/late",
    response_model=TrainingAttendanceOut,
    summary="Mark participant as late",
)
async def mark_late(
    attendance_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).mark_late(attendance_id)


@attendance_router.post(
    "/{attendance_id}/absent",
    response_model=TrainingAttendanceOut,
    summary="Mark participant as absent",
)
async def mark_absent(
    attendance_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).mark_absent(attendance_id)


@attendance_router.post(
    "/{attendance_id}/left-early",
    response_model=TrainingAttendanceOut,
    summary="Mark participant as left early",
)
async def mark_left_early(
    attendance_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).mark_left_early(attendance_id)


@attendance_router.post(
    "/{attendance_id}/check-out",
    response_model=TrainingAttendanceOut,
    summary="Check out a participant (records departure time)",
)
async def check_out(
    attendance_id: uuid.UUID,
    req: CheckOutAttendance,
    session: AsyncSession = Depends(get_session),
) -> TrainingAttendanceOut:
    return await TrainingAttendanceService(session).check_out(attendance_id, req)
