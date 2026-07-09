"""Reporting & Export Center REST API — Sprint 56."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.reporting.schemas import (
    GenerateReportRequest,
    ReportExportListOut,
    ReportExportOut,
)
from corpmind.modules.reporting.service import ReportingService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> ReportingService:
    return ReportingService(session)


@router.post(
    "/generate",
    response_model=ReportExportOut,
    status_code=201,
    summary="Generate a report synchronously — returns metadata with status",
)
async def generate_report(
    body: GenerateReportRequest,
    svc: ReportingService = Depends(_svc),
) -> ReportExportOut:
    return await svc.generate_report(body)


@router.get(
    "",
    response_model=ReportExportListOut,
    summary="List reports for a workspace",
)
async def list_reports(
    workspace_id: uuid.UUID = Query(...),
    report_type: str | None = Query(None),
    svc: ReportingService = Depends(_svc),
) -> ReportExportListOut:
    return await svc.list_reports(workspace_id, report_type=report_type)


@router.get(
    "/{report_id}",
    response_model=ReportExportOut,
    summary="Get a single report's metadata",
)
async def get_report(
    report_id: uuid.UUID,
    svc: ReportingService = Depends(_svc),
) -> ReportExportOut:
    return await svc.get_report(report_id)


@router.delete(
    "/{report_id}",
    status_code=204,
    summary="Delete a report record",
)
async def delete_report(
    report_id: uuid.UUID,
    svc: ReportingService = Depends(_svc),
) -> None:
    await svc.delete_report(report_id)
