"""Trainer intelligence module REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.trainer_intel.schemas import (
    ExtractFromTextRequest,
    TrainerProfileOut,
    TrainerProfileUpdate,
    UploadEnqueuedResponse,
    UploadRequest,
    UploadStatusResponse,
)
from corpmind.modules.trainer_intel.service import TrainerIntelService

router = APIRouter()


@router.post("/extract", response_model=TrainerProfileOut, status_code=status.HTTP_201_CREATED)
async def extract_profile(
    req: ExtractFromTextRequest,
    session: AsyncSession = Depends(get_session),
) -> TrainerProfileOut:
    svc = TrainerIntelService(session)
    return await svc.extract_from_text(req.content)


@router.get("/profile", response_model=TrainerProfileOut)
async def get_profile(
    session: AsyncSession = Depends(get_session),
) -> TrainerProfileOut:
    svc = TrainerIntelService(session)
    return await svc.get_profile()


@router.patch("/profile", response_model=TrainerProfileOut)
async def update_profile(
    update: TrainerProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> TrainerProfileOut:
    svc = TrainerIntelService(session)
    return await svc.update_profile(update)


@router.post("/profile/lock", response_model=TrainerProfileOut)
async def lock_profile(
    session: AsyncSession = Depends(get_session),
) -> TrainerProfileOut:
    svc = TrainerIntelService(session)
    return await svc.lock_profile()


@router.post("/upload", response_model=UploadEnqueuedResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(req: UploadRequest) -> UploadEnqueuedResponse:
    """Enqueue async extraction from an uploaded Cloudinary file.

    Returns immediately with a task_id. Poll GET /upload/{task_id} for status.
    The file is downloaded, text-extracted (PDF/image/video), then fed through
    EuriClient with task="trainer_extraction" to populate the workspace profile.
    """
    from corpmind.core.tenancy import get_tenant_context
    from corpmind.workers.tasks.ingestion import ingest_trainer_upload

    ctx = get_tenant_context()
    task = ingest_trainer_upload.apply_async(
        kwargs={
            "file_url": req.cloudinary_url,
            "file_type": req.file_type,
            "workspace_id": str(ctx.workspace_id),
            "tenant_id": str(ctx.org_id),
            "user_id": str(ctx.user_id),
            "request_id": ctx.request_id,
        }
    )
    return UploadEnqueuedResponse(task_id=task.id)


@router.get("/upload/{task_id}", response_model=UploadStatusResponse)
async def upload_status(task_id: str) -> UploadStatusResponse:
    """Poll the status of an async upload/extraction task."""
    from celery.result import AsyncResult

    from corpmind.workers.celery_app import app as celery_app

    result: AsyncResult = celery_app.AsyncResult(task_id)
    payload = result.result if result.ready() else None
    return UploadStatusResponse(
        task_id=task_id,
        status=result.state.lower(),
        result=payload if isinstance(payload, dict) else None,
    )
