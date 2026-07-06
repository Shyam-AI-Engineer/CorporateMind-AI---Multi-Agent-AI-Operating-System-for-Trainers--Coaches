"""Training Engagement, Session, Attendance, Certificate, and Feedback REST API — Sprint 42–46."""

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
    IssueCertificate,
    RevokeCertificate,
    SessionTrainerAssign,
    TrainerAssign,
    TrainingAttendanceCreate,
    TrainingAttendanceFilters,
    TrainingAttendanceListOut,
    TrainingAttendanceOut,
    TrainingAttendanceUpdate,
    TrainingCertificateCreate,
    TrainingCertificateFilters,
    TrainingCertificateListOut,
    TrainingCertificateOut,
    TrainingCertificateUpdate,
    TrainingEngagementCreate,
    TrainingEngagementFilters,
    TrainingEngagementListOut,
    TrainingEngagementOut,
    TrainingEngagementUpdate,
    TrainingFeedbackCreate,
    TrainingFeedbackFilters,
    TrainingFeedbackListOut,
    TrainingFeedbackOut,
    TrainingFeedbackUpdate,
    TrainingSessionCreate,
    TrainingSessionFilters,
    TrainingSessionListOut,
    TrainingSessionOut,
    TrainingSessionUpdate,
)
from corpmind.modules.training.service import (
    TrainingAttendanceService,
    TrainingCertificateService,
    TrainingEngagementService,
    TrainingFeedbackService,
    TrainingSessionService,
)

router = APIRouter()
sessions_router = APIRouter()
attendance_router = APIRouter()
certificates_router = APIRouter()
feedback_router = APIRouter()
customers_feedback_router = APIRouter()
trainers_feedback_router = APIRouter()


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


# ── Certificate endpoints ──────────────────────────────────────────────────────

@certificates_router.post(
    "/",
    response_model=TrainingCertificateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a certificate for an eligible attendance record",
)
async def create_certificate(
    req: TrainingCertificateCreate,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).create_certificate(req)


@certificates_router.get(
    "/",
    response_model=TrainingCertificateListOut,
    summary="List certificates (cursor-paginated)",
)
async def list_certificates(
    workspace_id: uuid.UUID = Query(...),
    session_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    issued_by: str | None = Query(default=None),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateListOut:
    filters = TrainingCertificateFilters(
        workspace_id=workspace_id,
        session_id=session_id,
        status=status_filter,
        issued_by=issued_by,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await TrainingCertificateService(session).list_certificates(filters)


# verify MUST be declared before /{cert_id} so FastAPI doesn't parse "verify" as a UUID
@certificates_router.get(
    "/verify/{verification_code}",
    response_model=TrainingCertificateOut,
    summary="Verify a certificate by its verification code",
)
async def verify_certificate(
    verification_code: str,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).verify_certificate(verification_code)


@certificates_router.get(
    "/{cert_id}",
    response_model=TrainingCertificateOut,
    summary="Get a certificate by ID",
)
async def get_certificate(
    cert_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).get_certificate(cert_id)


@certificates_router.patch(
    "/{cert_id}",
    response_model=TrainingCertificateOut,
    summary="Update a draft certificate",
)
async def update_certificate(
    cert_id: uuid.UUID,
    req: TrainingCertificateUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).update_certificate(cert_id, req)


@certificates_router.post(
    "/{cert_id}/issue",
    response_model=TrainingCertificateOut,
    summary="Issue a draft certificate",
)
async def issue_certificate(
    cert_id: uuid.UUID,
    req: IssueCertificate,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).issue_certificate(cert_id, req)


@certificates_router.post(
    "/{cert_id}/revoke",
    response_model=TrainingCertificateOut,
    summary="Revoke a certificate",
)
async def revoke_certificate(
    cert_id: uuid.UUID,
    req: RevokeCertificate,
    session: AsyncSession = Depends(get_session),
) -> TrainingCertificateOut:
    return await TrainingCertificateService(session).revoke_certificate(cert_id, req)


# ── Feedback endpoints ─────────────────────────────────────────────────────────

@feedback_router.post(
    "/",
    response_model=TrainingFeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback for an attendance record",
)
async def create_feedback(
    req: TrainingFeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> TrainingFeedbackOut:
    return await TrainingFeedbackService(session).create_feedback(req)


@feedback_router.get(
    "/",
    response_model=TrainingFeedbackListOut,
    summary="List feedback records (cursor-paginated)",
)
async def list_feedback(
    workspace_id: uuid.UUID = Query(...),
    session_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    trainer_id: uuid.UUID | None = Query(default=None),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TrainingFeedbackListOut:
    filters = TrainingFeedbackFilters(
        workspace_id=workspace_id,
        session_id=session_id,
        customer_id=customer_id,
        trainer_id=trainer_id,
        min_rating=min_rating,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    return await TrainingFeedbackService(session).list_feedback(filters)


@feedback_router.get(
    "/{feedback_id}",
    response_model=TrainingFeedbackOut,
    summary="Get a feedback record by ID",
)
async def get_feedback(
    feedback_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TrainingFeedbackOut:
    return await TrainingFeedbackService(session).get_feedback(feedback_id)


@feedback_router.patch(
    "/{feedback_id}",
    response_model=TrainingFeedbackOut,
    summary="Update a feedback record",
)
async def update_feedback(
    feedback_id: uuid.UUID,
    req: TrainingFeedbackUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainingFeedbackOut:
    return await TrainingFeedbackService(session).update_feedback(feedback_id, req)


# Session-scoped feedback (added to sessions_router)
@sessions_router.get(
    "/{session_id}/feedback",
    response_model=list[TrainingFeedbackOut],
    summary="List all feedback for a training session",
)
async def list_session_feedback(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[TrainingFeedbackOut]:
    return await TrainingFeedbackService(session).list_by_session(session_id)


# Customer-scoped feedback (mounted at /api/v1/customers)
@customers_feedback_router.get(
    "/{customer_id}/feedback",
    response_model=list[TrainingFeedbackOut],
    summary="List all training feedback for a customer",
)
async def list_customer_feedback(
    customer_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[TrainingFeedbackOut]:
    return await TrainingFeedbackService(session).list_by_customer(workspace_id, customer_id)


# Trainer-scoped feedback (mounted at /api/v1/trainers)
@trainers_feedback_router.get(
    "/{trainer_id}/feedback",
    response_model=list[TrainingFeedbackOut],
    summary="List all training feedback for a trainer",
)
async def list_trainer_feedback(
    trainer_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[TrainingFeedbackOut]:
    return await TrainingFeedbackService(session).list_by_trainer(workspace_id, trainer_id)
