"""CRM module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.crm.schemas import (
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
