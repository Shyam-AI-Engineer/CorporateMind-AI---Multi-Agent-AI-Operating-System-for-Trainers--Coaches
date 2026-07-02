"""CRM module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.core.exceptions import ValidationError
from corpmind.modules.crm.approval import FollowUpApprovalService
from corpmind.modules.crm.schemas import (
    ActivityListOut,
    FollowupApproveResponse,
    FollowupDraftView,
    FollowupEditRequest,
    FollowupRejectRequest,
    FollowupReviewOut,
    FollowUpTaskListOut,
    FollowUpTaskOut,
    LeadCreate,
    LeadListOut,
    LeadNoteUpdate,
    LeadOut,
    LeadScoreUpdate,
    LeadStageUpdate,
    MeetingScheduleRequest,
    PipelineStats,
    StageAdvanceResponse,
)
from corpmind.modules.crm.service import CRMService

router = APIRouter()


@router.post(
    "/",
    response_model=LeadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead for a contact",
)
async def create_lead(
    req: LeadCreate,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).create_lead(req)


@router.get(
    "/stats",
    response_model=PipelineStats,
    summary="Pipeline funnel counts per stage",
)
async def pipeline_stats(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> PipelineStats:
    return await CRMService(session).get_pipeline_stats(workspace_id)


@router.get(
    "/",
    response_model=LeadListOut,
    summary="List leads in the pipeline",
)
async def list_pipeline(
    workspace_id: uuid.UUID = Query(...),
    stage: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> LeadListOut:
    return await CRMService(session).list_pipeline(
        workspace_id, stage=stage, limit=limit, offset=offset
    )


@router.get(
    "/activities",
    response_model=ActivityListOut,
    summary="List CRM activities (paginated, tenant-scoped)",
)
async def list_activities(
    workspace_id: uuid.UUID | None = Query(default=None),
    lead_id: uuid.UUID | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ActivityListOut:
    """Activity timeline rows for a workspace, lead, or contact.

    At least one of `workspace_id`, `lead_id`, or `contact_id` must be set —
    the route refuses an unscoped query so the UI cannot accidentally pull
    every activity in the tenant.
    """
    if workspace_id is None and lead_id is None and contact_id is None:
        raise ValidationError(
            "At least one of workspace_id, lead_id, or contact_id is required"
        )
    return await CRMService(session).list_activities(
        workspace_id=workspace_id,
        lead_id=lead_id,
        contact_id=contact_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/follow-ups",
    response_model=FollowUpTaskListOut,
    summary="List follow-up tasks (paginated, workspace-scoped)",
)
async def list_follow_ups(
    workspace_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> FollowUpTaskListOut:
    """Pending or scheduled follow-up tasks for a workspace.

    Default sort: NULL scheduled_for first ("do asap"), then chronological.
    Filter by status (pending / done / cancelled) to drive the queue view.
    """
    return await CRMService(session).list_follow_up_tasks(
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        offset=offset,
    )


# ── Follow-up HITL approval (Sprint 8C) ───────────────────────────────────────

@router.get(
    "/follow-ups/{task_id}/review",
    response_model=FollowupReviewOut,
    summary="Review payload for an awaiting_approval follow-up (reply + draft + context)",
)
async def review_follow_up(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> FollowupReviewOut:
    return await FollowUpApprovalService(session).get_review(task_id)


@router.patch(
    "/follow-ups/{task_id}/draft",
    response_model=FollowupDraftView,
    summary="Edit the draft of an awaiting_approval follow-up before sending",
)
async def edit_follow_up_draft(
    task_id: uuid.UUID,
    req: FollowupEditRequest,
    session: AsyncSession = Depends(get_session),
) -> FollowupDraftView:
    return await FollowUpApprovalService(session).edit_draft(
        task_id, subject=req.subject, body=req.body
    )


@router.post(
    "/follow-ups/{task_id}/approve",
    response_model=FollowupApproveResponse,
    summary="Approve and send a follow-up draft (runs full ComplianceGuard)",
)
async def approve_follow_up(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> FollowupApproveResponse:
    return await FollowUpApprovalService(session).approve(task_id)


@router.post(
    "/follow-ups/{task_id}/reject",
    response_model=FollowUpTaskOut,
    summary="Reject a follow-up draft (cancels the task; nothing is sent)",
)
async def reject_follow_up(
    task_id: uuid.UUID,
    req: FollowupRejectRequest = FollowupRejectRequest(),
    session: AsyncSession = Depends(get_session),
) -> FollowUpTaskOut:
    return await FollowUpApprovalService(session).reject(task_id, reason=req.reason)


@router.get(
    "/{lead_id}",
    response_model=LeadOut,
    summary="Get a lead",
)
async def get_lead(
    lead_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).get_lead(lead_id)


# ── State transitions ─────────────────────────────────────────────────────────

@router.post(
    "/{lead_id}/advance",
    response_model=StageAdvanceResponse,
    summary="Advance lead to the next pipeline stage",
)
async def advance_lead_stage(
    lead_id: uuid.UUID,
    req: LeadStageUpdate,
    session: AsyncSession = Depends(get_session),
) -> StageAdvanceResponse:
    return await CRMService(session).advance_stage(lead_id, notes=req.notes)


@router.post(
    "/{lead_id}/lost",
    response_model=LeadOut,
    summary="Mark a lead as lost",
)
async def mark_lead_lost(
    lead_id: uuid.UUID,
    req: LeadStageUpdate,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).mark_lost(lead_id, notes=req.notes)


# ── Metadata updates ──────────────────────────────────────────────────────────

@router.patch(
    "/{lead_id}/score",
    response_model=LeadOut,
    summary="Update lead score (0–100)",
)
async def update_lead_score(
    lead_id: uuid.UUID,
    req: LeadScoreUpdate,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).update_score(lead_id, req.score)


@router.patch(
    "/{lead_id}/notes",
    response_model=LeadOut,
    summary="Replace lead notes",
)
async def update_lead_notes(
    lead_id: uuid.UUID,
    req: LeadNoteUpdate,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).add_note(lead_id, req.notes)


@router.patch(
    "/{lead_id}/meeting",
    response_model=LeadOut,
    summary="Set scheduled meeting datetime (lead must be in 'meeting_scheduled')",
)
async def set_meeting_time(
    lead_id: uuid.UUID,
    req: MeetingScheduleRequest,
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    return await CRMService(session).schedule_meeting(lead_id, req.meeting_at)


# ── Lead Pipeline Analytics router — Sprint 40 ────────────────────────────────

from corpmind.modules.crm.schemas import (  # noqa: E402
    IndustryAnalysisOut,
    LeadConversionOut,
    LeadPipelineSummaryOut,
    SourceAnalysisOut,
    StageAnalysisOut,
)
from corpmind.modules.crm.service import LeadPipelineAnalyticsService  # noqa: E402

lead_pipeline_router = APIRouter()


@lead_pipeline_router.get(
    "/summary",
    response_model=LeadPipelineSummaryOut,
    summary="Lead pipeline health summary",
)
async def lead_pipeline_summary(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> LeadPipelineSummaryOut:
    return await LeadPipelineAnalyticsService(session).get_summary(workspace_id)


@lead_pipeline_router.get(
    "/stages",
    response_model=StageAnalysisOut,
    summary="Stage-by-stage funnel analysis",
)
async def lead_pipeline_stages(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> StageAnalysisOut:
    return await LeadPipelineAnalyticsService(session).get_stage_analysis(workspace_id)


@lead_pipeline_router.get(
    "/sources",
    response_model=SourceAnalysisOut,
    summary="Lead source performance breakdown",
)
async def lead_pipeline_sources(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> SourceAnalysisOut:
    return await LeadPipelineAnalyticsService(session).get_source_analysis(workspace_id)


@lead_pipeline_router.get(
    "/industries",
    response_model=IndustryAnalysisOut,
    summary="Industry-level pipeline analysis",
)
async def lead_pipeline_industries(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> IndustryAnalysisOut:
    return await LeadPipelineAnalyticsService(session).get_industry_analysis(workspace_id)


@lead_pipeline_router.get(
    "/conversion",
    response_model=LeadConversionOut,
    summary="Conversion funnel metrics",
)
async def lead_pipeline_conversion(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> LeadConversionOut:
    return await LeadPipelineAnalyticsService(session).get_conversion(workspace_id)
